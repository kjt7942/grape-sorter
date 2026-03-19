import sys
import serial
import itertools
import subprocess
import os
import time
import random
import json

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from main_ui import SmartSorterUI, PresetDialog

# 프로그램의 목표무게, 프리셋 정보를 저장할 파일 경로
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def check_ota_update():
    """
    프로그램 기동 시 서버(Git)로부터 최신 코드가 있는지 확인하고 
    업데이트가 발견되면 사용자 승인을 얻어 자동 업데이트 및 재시작합니다.
    """
    try:
        subprocess.run(["git", "fetch"], timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        status = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True)
        if "Your branch is behind" in status.stdout:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("업데이트 알림")
            msg_box.setText("새로운 시스템 업데이트가 발견되었습니다.\n적용하시겠습니까?")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
            
            if msg_box.exec() == QMessageBox.Yes:
                subprocess.run(["git", "reset", "--hard"], check=True)
                subprocess.run(["git", "pull"], check=True)
                # 현재 프로세스를 최신 코드로 교체 실행
                os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        print("업데이트 확인 생략 (네트워크 또는 권한 문제):", e)


class SerialThread(QThread):
    """
    아두이노 로드셀 데이터 수신 및 LED 제어를 담당하는 백그라운드 스레드.
    메인 UI가 멈추지 않도록 비동기적으로 시리얼 통신을 처리합니다.
    """
    data_received = pyqtSignal(list) # 12개 채널의 무게값 리스트를 전달
    is_simulation = pyqtSignal(bool) # 아두이노 장치 유무 상태 전달

    def __init__(self, ports=['/dev/ttyACM0', '/dev/ttyUSB0', 'COM3', 'COM4', 'COM5'], baudrate=115200):
        super().__init__()
        self.ports = ports
        self.baudrate = baudrate
        self.serial_port = None
        self.running = True

    def run(self):
        """스레드 실행 루프: 포트 검색 및 데이터 수집"""
        # 연결 가능한 시리얼 포트 검색
        for p in self.ports:
            try:
                self.serial_port = serial.Serial(p, self.baudrate, timeout=1)
                print(f"[{p}] 아두이노 하드웨어 연결 성공")
                break
            except Exception:
                pass
                
        if not self.serial_port:
            print("아두이노 장치 없음: 시뮬레이션 모드 활성화")
            self.is_simulation.emit(True)
        else:
            self.is_simulation.emit(False)
        
        buffer = ""
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # 아두이노에서 들어오는 원시 데이터를 읽어 처리
                    data = self.serial_port.read(max(1, self.serial_port.in_waiting)).decode('utf-8', errors='ignore')
                    if data:
                        buffer += data
                        # 패킷 시작(<)과 끝(>)이 모두 포함된 경우만 파싱
                        while '<' in buffer and '>' in buffer:
                            start = buffer.find('<')
                            end = buffer.find('>', start)
                            if end != -1:
                                packet = buffer[start+1:end]
                                buffer = buffer[end+1:]
                                self.parse_packet(packet)
                            else:
                                break
                except Exception as e:
                    print(f"시리얼 통신 오류 발생: {e}")
                    time.sleep(1)
            else:
                # 시뮬레이션 모드: 대장님의 지시대로 무거운 포도 99% 밸런스 유지!
                fake_weights = []
                for _ in range(12):
                    chance = random.random()
                    if chance > 0.01: # 99% 확률로 500~1000g 사이의 포도 포착
                        fake_weights.append(random.randint(500, 1000))
                    elif chance > 0.005: # 약 0.5% 확률로 가벼운 빈 트레이(0g)
                        fake_weights.append(0)
                    else: # 약 0.5% 확률로 센서 에러 상태
                        fake_weights.append(-1)
                        
                self.data_received.emit(fake_weights)
                time.sleep(1) 

    def parse_packet(self, packet):
        """<725,670,...> 형태의 시리얼 문자열을 숫자 리스트로 변환합니다."""
        parts = packet.split(',')
        if len(parts) == 12:
            weights = []
            for p in parts:
                p = p.strip()
                if p == "ERR":
                    weights.append(-1) 
                else:
                    try:
                        weights.append(int(p))
                    except ValueError:
                        weights.append(0) 
            self.data_received.emit(weights)

    def send_signal(self, indices):
        """조합에 성공한 트레이의 번호들을 아두이노로 보내 LED를 켭니다."""
        if self.serial_port and self.serial_port.is_open:
            msg = f"<{','.join(map(str, indices))}>\n"
            try:
                self.serial_port.write(msg.encode('utf-8'))
            except Exception as e:
                print(f"아두이노 명령 전송 실패: {e}")
        else:
            if indices:
                print(f"[시뮬-LED] 점등 대상 트레이 번호: {indices}")

    def stop(self):
        """프로그램 종료 시 시리얼 연결을 안전하게 해제합니다."""
        self.running = False
        self.wait()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()


class MainApp(SmartSorterUI):
    """
    UI와 데이터를 연결하고 전체적인 선별기 비즈니스 로직을 총괄하는 메인 엔진 클래스.
    """
    def __init__(self):
        super().__init__()
        # 하드웨어 플랫폼에 따라 화면 표시 모드 선택
        if sys.platform == 'win32':
            self.showNormal() # PC에서는 창 모드
        else:
            self.showFullScreen() # 라즈베리파이 등 임베디드 장치에서는 전체화면
        
        self.weights = [0] * 12 # 실시간 무게값을 담는 메모리
        
        # 이전 작업 상태(목표무게, 모드 등) 복원
        self.settings_data = self.load_settings()
        last_state = self.settings_data.get("last_state", {})
        
        self.target_weight = last_state.get("target_weight", 2050)
        self.min_comb = last_state.get("min_comb", 3)
        self.max_comb = last_state.get("max_comb", 4)
        self.is_dark_mode = last_state.get("is_dark_mode", True)
        self.current_preset_index = last_state.get("current_preset_index", None)
        self.is_topup_mode = last_state.get("is_topup_mode", False)
        
        self.memo_min_comb = self.min_comb # 보태기 모드 해제 시 개수 복원용
        
        self.setup_logic()
        
        # 특수 트레이(좌상단, 좌중단, 우하단) 더블클릭 시 시스템 제어 연결
        self.tray_cards[0].doubleClicked.connect(QApplication.instance().quit)
        self.tray_cards[6].doubleClicked.connect(self.restart_program) 
        self.tray_cards[11].doubleClicked.connect(self.shutdown_system) 
        
        # 아두이노 통신 스레드 시작
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(self.update_sim_mode_display)
        self.serial_thread.start()

    def load_settings(self):
        """settings.json에서 마지막 설정과 프리셋 데이터를 읽어옵니다."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "presets" not in data or len(data["presets"]) < 8:
                        presets = data.get("presets", [])
                        presets.extend([None] * (8 - len(presets)))
                        data["presets"] = presets
                    return data
            except Exception as e:
                print(f"설정 불러오기 실패: {e}")
        return {"last_state": {}, "presets": [None] * 8}

    def save_settings(self):
        """현재 화면의 모든 설정을 settings.json에 영구 저장합니다."""
        self.settings_data["last_state"] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb,
            "is_dark_mode": self.is_dark_mode,
            "current_preset_index": self.current_preset_index,
            "is_topup_mode": self.is_topup_mode 
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"설정 저장 실패: {e}")

    def closeEvent(self, event):
        """프로그램 창이 닫힐 때 하드웨어와 자원을 정리합니다."""
        self.save_settings()
        self.serial_thread.stop()
        super().closeEvent(event)

    def restart_program(self):
        """프로그램을 즉시 재기동합니다."""
        self.save_settings()
        self.serial_thread.stop()
        os.execv(sys.executable, ['python'] + sys.argv)

    def shutdown_system(self):
        """라즈베리파이 시스템 전체 전원을 종료합니다."""
        self.save_settings()
        self.serial_thread.stop()
        os.system("sudo shutdown now")

    def update_sim_mode_display(self, is_sim):
        """아두이노 연결 상태에 따라 UI에 시뮬레이션 경고를 띄웁니다."""
        if is_sim and not self.is_topup_mode:
            self.lbl_sum_title.setText("합계(시뮬모드)")
            self.lbl_sum_title.setStyleSheet("color: #F87171;")
        else:
            self.lbl_sum_title.setText("합계" if not self.is_topup_mode else "박스무게(1,2,7,8)")

    def setup_logic(self):
        """버튼 클릭, 값 설정 이벤트 등 UI 시그널을 비즈니스 로직에 연결합니다."""
        self.update_setting_ui()
        self.update_topup_ui()
        self.apply_theme() 
        
        self.btn_tare.clicked.connect(self.send_tare_command)
        self.btn_register.clicked.connect(self.show_preset_dialog) 
        self.btn_topup.clicked.connect(self.toggle_topup_mode)

        # 수동 설정 값 변경 이벤트 연결 (delta 수치로 증가/감소)
        self.setting_target.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('target', -10 * mult))
        self.setting_target.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('target', 10 * mult))
        self.setting_min.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('min', -1))
        self.setting_min.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('min', 1))
        self.setting_max.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('max', -1))
        self.setting_max.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('max', 1))
        
        # 제품명 버튼 클릭 시 프리셋 리스트 순환
        self.setting_product.btn_minus.stepTriggered.connect(lambda mult: self.cycle_preset(-1) if mult == 1 else None)
        self.setting_product.btn_plus.stepTriggered.connect(lambda mult: self.cycle_preset(1) if mult == 1 else None)
        
        # 테마 변경 시 동적 텍스트와 보류중인 UI 요소 재정렬
        original_toggle_theme = self.toggle_theme
        def new_toggle_theme():
            original_toggle_theme()
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=(self.combo_val.text() != "조합실패")))
            self.update_topup_ui()
            self.on_data_received(self.weights)
            
        self.btn_theme_toggle.clicked.disconnect() 
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

    def toggle_topup_mode(self):
        """'보태기 모드'(이미 포도가 담긴 박스에 최적의 한 개를 더하는 모드)를 켜거나 끕니다."""
        self.is_topup_mode = not self.is_topup_mode
        if self.is_topup_mode:
            self.memo_min_comb = self.min_comb
            self.min_comb = 1 # 보태기 모드에서는 한 개부터 조합 시작
        else:
            self.min_comb = self.memo_min_comb
            
        self.update_topup_ui()
        self.update_setting_ui()
        self.on_data_received(self.weights)

    def update_topup_ui(self):
        """보태기 모드 활성화 여부를 버튼 배경색으로 시각화합니다."""
        if self.is_topup_mode:
            self.btn_topup.setStyleSheet("QPushButton { background-color: #2563EB; color: white; border: 2px solid #1E40AF; font-weight: bold; }")
        else:
            self.btn_topup.setStyleSheet("") # 기본 테마 테두리로 복구

    def cycle_preset(self, direction):
        """프리셋 리스트(A~H) 중 비어있지 않은 다음 제품 설정으로 전환합니다."""
        presets = self.settings_data.get("presets", [])
        if not any(presets): return 
            
        idx = self.current_preset_index if self.current_preset_index is not None else 0
        for _ in range(8): 
            idx = (idx + direction) % 8
            if presets[idx] is not None:
                self.load_preset(idx, dialog=None) 
                break

    def show_preset_dialog(self):
        """제품 프리셋 선택/저장용 팝업 다이얼로그를 표시합니다."""
        dialog = PresetDialog(self, is_dark_mode=self.is_dark_mode)
        presets = self.settings_data.get("presets", [None]*8)
            
        dialog.btn_clear.clicked.connect(lambda: self.clear_all_presets(dialog))
        
        slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for i, btn in enumerate(dialog.preset_buttons):
            if presets[i]:
                p = presets[i]
                btn.setText(f"슬롯 {slot_names[i]}\n{p['target_weight']}g\n({p['min_comb']}~{p['max_comb']}개)")
            else:
                btn.setText(f"슬롯 {slot_names[i]}\n(비어있음)")
                
            btn.shortClicked.connect(lambda idx=i, d=dialog: self.load_preset(idx, d))
            btn.longPressed.connect(lambda idx=i, b=btn, s=slot_names[i]: self.save_preset(idx, b, s))
        dialog.exec_()

    def clear_all_presets(self, dialog):
        """모든 프리셋 정보를 초기화합니다."""
        reply = QMessageBox.warning(dialog, "초기화 경고", "전체 제품 슬롯을 비우시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.settings_data["presets"] = [None] * 8
            self.current_preset_index = None
            self.save_settings()
            self.update_setting_ui()
            
            # ✨ 버그 3 해결: 팝업창을 튕겨 끄지 않고 8개 버튼을 '비어있음'으로 실시간 갱신!
            slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            for i, btn in enumerate(dialog.preset_buttons):
                btn.setText(f"슬롯 {slot_names[i]}\n(비어있음)")
                btn.setStyleSheet("")

    def load_preset(self, index, dialog=None):
        """선택한 번호의 프리셋 정보를 현재 작업 데이터로 불러옵니다."""
        presets = self.settings_data.get("presets", [None] * 8)
        if presets[index]:
            p = presets[index]
            self.target_weight = p['target_weight']
            self.min_comb = p['min_comb']
            self.max_comb = p['max_comb']
            self.current_preset_index = index 
            self.update_setting_ui()
            if dialog: dialog.accept() 

    def save_preset(self, index, button_widget, slot_name):
        """현재 화면의 설정을 선택한 프리셋 슬롯에 영구 저장합니다."""
        presets = self.settings_data.get("presets", [None] * 8)
        presets[index] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb
        }
        self.settings_data["presets"] = presets
        self.save_settings() 
        button_widget.setText(f"슬롯 {slot_name}\n저장됨!")
        button_widget.setStyleSheet("background-color: #059669; color: white;") 
        self.current_preset_index = index 
        self.update_setting_ui()

    def send_tare_command(self):
        """아두이노 하드웨어에 '영점 조절' 명령 패킷을 보냅니다."""
        if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
            self.serial_thread.serial_port.write(b"<TARE>\n")
        else:
            print("[시뮬-TARE] 영점 조절 명령 시뮬레이션")

    def change_setting(self, kind, delta):
        """사용자가 버튼을 눌러 목표무게나 개수 범위를 수동 변경할 때 실행됩니다."""
        if kind == 'target':
            self.target_weight = max(100, self.target_weight + delta) 
        elif kind == 'min':
            self.min_comb = max(1, min(12, self.min_comb + delta))
            if self.min_comb > self.max_comb: self.max_comb = self.min_comb
            # ✨ 버그 4 해결: 보태기 모드 중에 수동으로 개수를 조작하면, 나중에 롤백될 메모리 값도 같이 업데이트!
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb
        elif kind == 'max':
            self.max_comb = max(1, min(12, self.max_comb + delta))
            if self.max_comb < self.min_comb: self.min_comb = self.max_comb
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb
            
        self.current_preset_index = None # 수동 조작 시 프리셋 이름은 표시 안 함
        self.update_setting_ui()

    def update_setting_ui(self):
        """현재 메모리에 저장된 설정값들을 화면의 텍스트 레이블로 최신화합니다."""
        preset_text = f"{self.target_weight:,}g({self.min_comb}~{self.max_comb}개)"
        if self.current_preset_index is not None:
            slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            display_text = f"슬롯 {slot_names[self.current_preset_index]} : {preset_text}"
        else:
            display_text = f"수동설정 : {preset_text}"
            
        self.setting_product.lbl_center.setText(display_text)
        self.setting_target.lbl_center.setText(f"목표무게 : {self.target_weight:,} g")
        self.setting_min.lbl_center.setText(f"최소조합 : {self.min_comb} 개")
        self.setting_max.lbl_center.setText(f"최대조합 : {self.max_comb} 개")

    def get_combo_card_style(self, highlight=True):
        """조합 성공/실패 여부에 따라 결과 카드의 테두리와 배경색 스타일을 반환합니다."""
        if self.is_dark_mode:
            if highlight:
                return "QFrame#ComboCard { border: 3px solid #059669; background-color: #064E3B; border-radius: 20px; margin: 0px; padding: 0px; }"
            else:
                return "QFrame#ComboCard { border: 3px solid #333333; background-color: #1E1E1E; border-radius: 20px; margin: 0px; padding: 0px; }"
        else:
            if highlight:
                return "QFrame#ComboCard { border: 3px solid #10B981; background-color: #ECFDF5; border-radius: 20px; margin: 0px; padding: 0px; }"
            else:
                return "QFrame#ComboCard { border: 3px solid #E5E7EB; background-color: #FFFFFF; border-radius: 20px; margin: 0px; padding: 0px; }"
                
    def on_data_received(self, weights):
        """시리얼 통신 스레드로부터 새 무게 리스트를 받았을 때 실행되는 콜백 함수."""
        self.weights = weights
        total = 0
        topup_sum = 0
        for i, w in enumerate(self.weights):
            if w > 0:
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: white;" if self.is_dark_mode else "color: #1F2937;")
                total += w
                if self.is_topup_mode and i in [0, 1, 6, 7]: # 보태기 모드 시 특정 트레이(박스 위치) 합산
                    topup_sum += w
            elif w == -1: 
                self.tray_weight_labels[i].setText("에러(ERR)")
                self.tray_weight_labels[i].setStyleSheet("color: #EF4444; font-weight: bold;") 
            else: 
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: #555555;" if self.is_dark_mode else "color: #9CA3AF;")
                
        # 하단 합계 요약 UI 업데이트
        if self.is_topup_mode:
            self.lbl_sum_title.setText("박스무게(1,2,7,8)")
            self.sum_val_lbl.setText(f"{topup_sum:,} g")
        else:
            self.sum_val_lbl.setText(f"{total:,} g")
            
        self.find_best_combination()

    def find_best_combination(self):
        """현재 올라온 포도 무게들 중 목표무게에 가장 근접하고 
        오차 범위(0~100g) 내에 있는 최적의 조합을 연산 알고리즘(Combinations)으로 찾습니다.
        """
        target = self.target_weight
        min_c = self.min_comb
        max_c = self.max_comb
        
        valid_items = []
        topup_sum = 0
        
        for i, w in enumerate(self.weights):
            if w > 0:
                if self.is_topup_mode and i in [0, 1, 6, 7]: 
                    topup_sum += w
                else:
                    valid_items.append((i+1, w)) # 유효한 트레이 번호와 무게 저장
        
        current_target = target - topup_sum if self.is_topup_mode else target
            
        best_combo = None
        best_diff = float('inf')
        best_sum = 0
        
        # 조합 연산 시작
        for r in range(min_c, max_c + 1):
            for combo in itertools.combinations(valid_items, r):
                combo_sum = sum(item[1] for item in combo)
                diff = combo_sum - current_target
                
                # 조건: 목표무게 미달은 안 됨, 초과는 최대 100g까지만 허용
                if 0 <= diff <= 100:
                    if diff < best_diff: # 더 정밀한 오차를 찾은 경우
                        best_diff = diff
                        best_combo = combo
                        best_sum = combo_sum
                    elif diff == best_diff: # 오차가 같다면 더 많은 개수를 선호
                        if best_combo is None or len(combo) > len(best_combo):
                            best_combo = combo
                            best_sum = combo_sum

        # 연산 결과에 따라 개별 트레이 카드의 하이라이트(색상) 처리
        # 흔들림 방지를 위해 margin: 0px; padding: 0px; 속성 포함
        for i in range(12):
            is_topup_tray = self.is_topup_mode and i in [0, 1, 6, 7]
            is_combo_tray = best_combo is not None and (i+1) in [item[0] for item in best_combo]
            
            if is_topup_tray: # 보태기 모드 대상 트레이 (파란색)
                style = "QFrame#Card { background-color: #1E3A8A; border-radius: 16px; border: 2px solid #3B82F6; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #DBEAFE; border-radius: 16px; border: 2px solid #2563EB; margin: 0px; padding: 0px; }"
            elif is_combo_tray: # 최적 조합 트레이 (초록색)
                style = "QFrame#Card { background-color: #064E3B; border-radius: 16px; border: 2px solid #059669; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #ECFDF5; border-radius: 16px; border: 2px solid #10B981; margin: 0px; padding: 0px; }"
            else: # 일반 대기 상태 (테마 기본)
                style = "QFrame#Card { background-color: #1E1E1E; border-radius: 16px; border: 2px solid #333333; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #FFFFFF; border-radius: 16px; border: 2px solid #E5E7EB; margin: 0px; padding: 0px; }"
            self.tray_cards[i].setStyleSheet(style)
        
        # 최종 결과 요약 업데이트 및 아두이노 LED 제어 명령 전송
        if best_combo is not None:
            final_sum = best_sum + (topup_sum if self.is_topup_mode else 0)
            self.combo_val.setText(f"{final_sum:,} g")
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=True))
            self.serial_thread.send_signal([item[0] for item in best_combo]) 
        else:
            self.combo_val.setText("조합실패")
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=False))
            self.serial_thread.send_signal([])

if __name__ == "__main__":
    import main_ui # 모듈 레벨 변수 접근용
    from PyQt5.QtGui import QFont, QFontDatabase
    
    check_ota_update() # 기동 시 업데이트 체크
    
    # 터치패널/고주사율 대응 고해상도 옵션
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # 폰트 로드 및 전역 적용
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                main_ui.UI_FONT_FAMILY = families[0] # main_ui 모듈의 전역 폰트 이름 업데이트
    
    default_font = app.font()
    default_font.setFamily(main_ui.UI_FONT_FAMILY)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)

    window = MainApp()
    window.show()
    sys.exit(app.exec_())