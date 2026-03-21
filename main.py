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


class OTAThread(QThread):
    """
    프로그램이 켜질 때 화면을 멈추지 않게 뒤에서 몰래 깃허브(서버) 상태를 묻고 오는 스파이 스레드입니다.
    """
    update_available = pyqtSignal()

    def run(self):
        try:
            subprocess.run(["git", "fetch"], timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            status = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True)
            if "Your branch is behind" in status.stdout:
                self.update_available.emit() # 업데이트가 있으면 메인 화면에 신호 발사!
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
                fake_weights = []
                for _ in range(12):
                    chance = random.random()
                    if chance > 0.01: 
                        fake_weights.append(random.randint(500, 1000))
                    elif chance > 0.005: 
                        fake_weights.append(0)
                    else: 
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
        if sys.platform == 'win32':
            self.showNormal() 
        else:
            self.showFullScreen() 
        
        self.weights = [0] * 12 
        
        self.settings_data = self.load_settings()
        last_state = self.settings_data.get("last_state", {})
        
        self.target_weight = last_state.get("target_weight", 2050)
        self.min_comb = last_state.get("min_comb", 3)
        self.max_comb = last_state.get("max_comb", 4)
        self.is_dark_mode = last_state.get("is_dark_mode", True)
        self.current_preset_index = last_state.get("current_preset_index", None)
        self.is_topup_mode = last_state.get("is_topup_mode", False)
        
        self.memo_min_comb = self.min_comb 
        
        self.setup_logic()
        
        self.tray_cards[0].doubleClicked.connect(QApplication.instance().quit)
        self.tray_cards[6].doubleClicked.connect(self.restart_program) 
        self.tray_cards[11].doubleClicked.connect(self.shutdown_system) 
        
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(self.update_sim_mode_display)
        self.serial_thread.start()
        
        # 화면이 뜨자마자 백그라운드에서 업데이트 확인 시작
        self.start_ota_check()

    def start_ota_check(self):
        self.ota_thread = OTAThread()
        self.ota_thread.update_available.connect(self.prompt_ota_update)
        self.ota_thread.start()

    # ✨ 핵심 업데이트: 파이썬 & 아두이노 메가 2560 펌웨어 동시 업데이트 로직 탑재
    def prompt_ota_update(self):
        """백그라운드에서 업데이트를 발견하면 팝업창을 띄워 결재를 받습니다."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("시스템 업데이트 알림")
        msg_box.setText("새로운 시스템(및 아두이노 펌웨어) 업데이트가 발견되었습니다.\n적용하시겠습니까?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        
        if msg_box.exec() == QMessageBox.Yes:
            # 1단계: 깃허브 최신 코드 강제 적용
            subprocess.run(["git", "reset", "--hard"], check=True)
            subprocess.run(["git", "pull"], check=True)
            
            # 2단계: 아두이노가 연결되어 있다면 포트를 해제하여 업로드 충돌 방지
            arduino_port = None
            if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
                arduino_port = self.serial_thread.serial_port.port
            self.serial_thread.stop()
            time.sleep(1.5) 
            
            # 3단계: 아두이노 메가 2560 펌웨어 자동 업로드
            firmware_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arduino_firmware")
            if arduino_port and os.path.exists(firmware_dir):
                print(f"[OTA] 아두이노 펌웨어 자동 업데이트 시작 (포트: {arduino_port})")
                try:
                    # 테스트로 검증 완료된 명령어 적용!
                    fqbn = "arduino:avr:mega:cpu=atmega2560"
                    compile_cmd = ["arduino-cli", "compile", "--fqbn", fqbn, firmware_dir]
                    upload_cmd = ["arduino-cli", "upload", "-p", arduino_port, "--fqbn", fqbn, firmware_dir]
                    
                    subprocess.run(compile_cmd, check=True)
                    subprocess.run(upload_cmd, check=True)
                    print("[OTA] 아두이노 메가 2560 펌웨어 업데이트 완벽 성공!")
                except Exception as e:
                    print(f"[OTA] 펌웨어 업로드 실패 (명령어 누락 또는 보드 타입 오류): {e}")
            
            # 4단계: 시스템 재시작 (모든 업데이트 반영 완료)
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def load_settings(self):
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
        self.save_settings()
        self.serial_thread.stop()
        super().closeEvent(event)

    def restart_program(self):
        self.save_settings()
        self.serial_thread.stop()
        os.execv(sys.executable, [sys.executable] + sys.argv) 

    def shutdown_system(self):
        self.save_settings()
        self.serial_thread.stop()
        os.system("sudo shutdown now")

    def update_sim_mode_display(self, is_sim):
        if is_sim and not self.is_topup_mode:
            self.lbl_sum_title.setText("합계(시뮬모드)")
            self.lbl_sum_title.setStyleSheet("color: #F87171;")
        else:
            self.lbl_sum_title.setText("합계" if not self.is_topup_mode else "박스무게(1,2,7,8)")

    def setup_logic(self):
        self.update_setting_ui()
        self.update_topup_ui()
        self.apply_theme() 
        
        self.btn_tare.clicked.connect(self.send_tare_command)
        self.btn_register.clicked.connect(self.show_preset_dialog) 
        self.btn_topup.clicked.connect(self.toggle_topup_mode)

        self.setting_target.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('target', -10 * mult))
        self.setting_target.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('target', 10 * mult))
        self.setting_min.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('min', -1))
        self.setting_min.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('min', 1))
        self.setting_max.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('max', -1))
        self.setting_max.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('max', 1))
        
        self.setting_product.btn_minus.stepTriggered.connect(lambda mult: self.cycle_preset(-1) if mult == 1 else None)
        self.setting_product.btn_plus.stepTriggered.connect(lambda mult: self.cycle_preset(1) if mult == 1 else None)
        
        original_toggle_theme = self.toggle_theme
        def new_toggle_theme():
            original_toggle_theme()
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=(self.combo_val.text() != "조합실패")))
            self.update_topup_ui()
            self.on_data_received(self.weights)
            
        self.btn_theme_toggle.clicked.disconnect() 
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

    def toggle_topup_mode(self):
        self.is_topup_mode = not self.is_topup_mode
        if self.is_topup_mode:
            self.memo_min_comb = self.min_comb
            self.min_comb = 1 
        else:
            self.min_comb = self.memo_min_comb
            
        self.update_topup_ui()
        self.update_setting_ui()
        self.on_data_received(self.weights)

    def update_topup_ui(self):
        if self.is_topup_mode:
            self.btn_topup.setStyleSheet("QPushButton { background-color: #2563EB; color: white; border: 2px solid #1E40AF; font-weight: bold; }")
        else:
            self.btn_topup.setStyleSheet("") 

    def cycle_preset(self, direction):
        presets = self.settings_data.get("presets", [])
        if not any(presets): return 
            
        idx = self.current_preset_index if self.current_preset_index is not None else 0
        for _ in range(8): 
            idx = (idx + direction) % 8
            if presets[idx] is not None:
                self.load_preset(idx, dialog=None) 
                break

    def show_preset_dialog(self):
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
        reply = QMessageBox.warning(dialog, "초기화 경고", "전체 제품 슬롯을 비우시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.settings_data["presets"] = [None] * 8
            self.current_preset_index = None
            self.save_settings()
            self.update_setting_ui()
            
            slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            for i, btn in enumerate(dialog.preset_buttons):
                btn.setText(f"슬롯 {slot_names[i]}\n(비어있음)")
                btn.setStyleSheet("")

    def load_preset(self, index, dialog=None):
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
        if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
            self.serial_thread.serial_port.write(b"<TARE>\n")
        else:
            print("[시뮬-TARE] 영점 조절 명령 시뮬레이션")

    def change_setting(self, kind, delta):
        if kind == 'target':
            self.target_weight = max(100, self.target_weight + delta) 
        elif kind == 'min':
            self.min_comb = max(1, min(12, self.min_comb + delta))
            if self.min_comb > self.max_comb: self.max_comb = self.min_comb
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb
        elif kind == 'max':
            self.max_comb = max(1, min(12, self.max_comb + delta))
            if self.max_comb < self.min_comb: self.min_comb = self.max_comb
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb
            
        self.current_preset_index = None 
        self.update_setting_ui()

    def update_setting_ui(self):
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
        self.weights = weights
        total = 0
        topup_sum = 0
        for i, w in enumerate(self.weights):
            if w > 0:
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: white;" if self.is_dark_mode else "color: #1F2937;")
                total += w
                if self.is_topup_mode and i in [0, 1, 6, 7]: 
                    topup_sum += w
            elif w == -1: 
                self.tray_weight_labels[i].setText("에러(ERR)")
                self.tray_weight_labels[i].setStyleSheet("color: #EF4444; font-weight: bold;") 
            else: 
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: #555555;" if self.is_dark_mode else "color: #9CA3AF;")
                
        if self.is_topup_mode:
            self.lbl_sum_title.setText("박스무게(1,2,7,8)")
            self.sum_val_lbl.setText(f"{topup_sum:,} g")
        else:
            self.sum_val_lbl.setText(f"{total:,} g")
            
        self.find_best_combination()

    def find_best_combination(self):
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
                    valid_items.append((i+1, w)) 
        
        current_target = target - topup_sum if self.is_topup_mode else target
            
        best_combo = None
        best_diff = float('inf')
        best_sum = 0
        
        for r in range(min_c, max_c + 1):
            for combo in itertools.combinations(valid_items, r):
                combo_sum = sum(item[1] for item in combo)
                diff = combo_sum - current_target
                
                if 0 <= diff <= 100:
                    if diff < best_diff: 
                        best_diff = diff
                        best_combo = combo
                        best_sum = combo_sum
                    elif diff == best_diff: 
                        if best_combo is None or len(combo) > len(best_combo):
                            best_combo = combo
                            best_sum = combo_sum

        for i in range(12):
            is_topup_tray = self.is_topup_mode and i in [0, 1, 6, 7]
            is_combo_tray = best_combo is not None and (i+1) in [item[0] for item in best_combo]
            
            if is_topup_tray: 
                style = "QFrame#Card { background-color: #1E3A8A; border-radius: 16px; border: 2px solid #3B82F6; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #DBEAFE; border-radius: 16px; border: 2px solid #2563EB; margin: 0px; padding: 0px; }"
            elif is_combo_tray: 
                style = "QFrame#Card { background-color: #064E3B; border-radius: 16px; border: 2px solid #059669; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #ECFDF5; border-radius: 16px; border: 2px solid #10B981; margin: 0px; padding: 0px; }"
            else: 
                style = "QFrame#Card { background-color: #1E1E1E; border-radius: 16px; border: 2px solid #333333; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #FFFFFF; border-radius: 16px; border: 2px solid #E5E7EB; margin: 0px; padding: 0px; }"
            self.tray_cards[i].setStyleSheet(style)
        
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
    import main_ui 
    from PyQt5.QtGui import QFont, QFontDatabase
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                main_ui.UI_FONT_FAMILY = families[0] 
    
    default_font = app.font()
    default_font.setFamily(main_ui.UI_FONT_FAMILY)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)

    window = MainApp()
    window.show()
    sys.exit(app.exec_())