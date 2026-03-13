import sys
import serial
import itertools
import subprocess
import os
import time
import random

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# 사용자 정의 레이아웃/UI 모듈명 임포트
from main_ui import SmartSorterUI

def check_ota_update():
    """최초 실행 시 Github OTA 업데이트 수행 로직"""
    try:
        subprocess.run(["git", "fetch"], timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        status = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True)
        if "Your branch is behind" in status.stdout:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("업데이트 알림")
            msg_box.setText("새로운 시스템 업데이트가 발견되었습니다.\n적용하시겠습니까?")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            
            # 최상단 표시 옵션 적용
            msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
            
            if msg_box.exec() == QMessageBox.Yes:
                subprocess.run(["git", "reset", "--hard"], check=True)
                subprocess.run(["git", "pull"], check=True)
                os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        print("OTA 업데이트 확인 스킵:", e)


class SerialThread(QThread):
    # 시리얼로 수신한 12개 무게 배열 전달하는 PyQt 시그널
    data_received = pyqtSignal(list)
    # 시뮬레이션 모드 여부 전달 시그널
    is_simulation = pyqtSignal(bool)

    def __init__(self, ports=['/dev/ttyACM0', '/dev/ttyUSB0', 'COM3', 'COM4', 'COM5'], baudrate=115200):
        super().__init__()
        self.ports = ports
        self.baudrate = baudrate
        self.serial_port = None
        self.running = True

    def run(self):
        # 포트 연결 시도
        for p in self.ports:
            try:
                self.serial_port = serial.Serial(p, self.baudrate, timeout=1)
                print(f"[{p}] 아두이노 USB 연결 성공")
                break
            except Exception:
                pass
                
        if not self.serial_port:
            print("경고: 아두이노 장치를 찾을 수 없습니다. 시뮬레이션 모드로 동작합니다.")
            self.is_simulation.emit(True)
        else:
            self.is_simulation.emit(False)
        
        buffer = ""
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
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
                    print(f"시리얼 수신 스트림 오류: {e}")
                    time.sleep(1)
            else:
                # 시뮬레이션 모드: 1초마다 랜덤 포도 무게 데이터 생성
                fake_weights = []
                for _ in range(12):
                    if random.random() > 0.05: # 95% 확률로 포도가 트레이에 존재 (5% 빈 트레이)
                        fake_weights.append(random.randint(450, 1100))
                    else:
                        fake_weights.append(0)
                        
                self.data_received.emit(fake_weights)
                time.sleep(1) # 눈으로 확인하기 용이하도록 1초 간격 갱신

    def parse_packet(self, packet):
        try:
            parts = packet.split(',')
            if len(parts) == 12:
                weights = [int(p) for p in parts]
                self.data_received.emit(weights)
        except ValueError:
            pass

    def send_signal(self, indices):
        """조합이 맞는 경우 해당 트레이 인덱스를 아두이노로 송신하여 LED 점등 요구"""
        if self.serial_port and self.serial_port.is_open:
            # 포맷: [1,4,7]
            msg = f"[{','.join(map(str, indices))}]\n"
            try:
                self.serial_port.write(msg.encode('utf-8'))
            except Exception as e:
                print(f"시리얼 데이터 송신 오류: {e}")
        else:
            print(f"[시뮬레이션] LED 점등 대상 트레이: {indices}")

    def stop(self):
        self.running = False
        self.wait()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()


class MainApp(SmartSorterUI):
    def __init__(self):
        super().__init__()
        # PC(Windows) 환경에서는 최대화 창, 라즈베리파이(Linux)는 풀스크린 적용
        if sys.platform == 'win32':
            self.showMaximized()
        else:
            self.showFullScreen()
        
        # 내부 알고리즘 설정 상태 초기화
        self.weights = [0] * 12
        self.target_weight = 2050
        self.min_comb = 3
        self.max_comb = 4
        self.is_running = True
        self.product_name = "포도 2KG"
        
        self.setup_logic()
        
        # 아두이노 시리얼 통신 백그라운드 스레드 시작
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(lambda is_sim: self.lbl_sim_mode.setVisible(is_sim))
        self.serial_thread.start()

    def setup_logic(self):
        # UI 업데이트용 초기 텍스트 설정
        self.update_setting_ui()
        
        # --- 이벤트 바인딩 ---
        
        # 1. 동작 제어 버튼
        self.btn_pause.clicked.connect(self.pause_operation)
        self.btn_run.clicked.connect(self.start_operation)
        self.btn_register.clicked.connect(self.dummy_register)
        
        # 시작 시 동작 중이므로 '동작' 버튼은 숨기고 '일시정지'만 표시
        self.btn_run.hide()

        # 2. 설정 값 증감 버튼 바인딩 (main_ui.py에서 할당해준 인스턴스 반영)
        
        # 목표 무게 (±10g 단위)
        self.setting_target.btn_minus.clicked.connect(lambda: self.change_setting('target', -10))
        self.setting_target.btn_plus.clicked.connect(lambda: self.change_setting('target', 10))
        
        # 최소 조합 개수 (±1 단위)
        self.setting_min.btn_minus.clicked.connect(lambda: self.change_setting('min', -1))
        self.setting_min.btn_plus.clicked.connect(lambda: self.change_setting('min', 1))
        
        # 최대 조합 개수 (±1 단위)
        self.setting_max.btn_minus.clicked.connect(lambda: self.change_setting('max', -1))
        self.setting_max.btn_plus.clicked.connect(lambda: self.change_setting('max', 1))
        
        # 제품명 버튼은 증감없이 고정 (Hide)
        self.setting_product.btn_minus.hide()
        self.setting_product.btn_plus.hide()
        
        # 테마 토글 시 콤보박스 색상을 재적용하기 위해 기존 테마 토글 함수를 확장 적용
        original_toggle_theme = self.toggle_theme
        def new_toggle_theme():
            original_toggle_theme()
            # 테마 토글 시 콤보 카드도 테마에 맞게 색상 갱신
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=(self.combo_val.text() != "조합실패" and self.is_running)))
        self.btn_theme_toggle.clicked.disconnect() # 기존 바인딩 해제
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

    def keyPressEvent(self, event):
        # 풀스크린 토글 단축키 (F11, Esc 처리)
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key_Escape:
            self.showNormal()
        super().keyPressEvent(event)

    def change_setting(self, kind, delta):
        if kind == 'target':
            self.target_weight = max(100, self.target_weight + delta) # 최소 100g 이상
        elif kind == 'min':
            self.min_comb = max(1, min(12, self.min_comb + delta))
            if self.min_comb > self.max_comb: self.max_comb = self.min_comb
        elif kind == 'max':
            self.max_comb = max(1, min(12, self.max_comb + delta))
            if self.max_comb < self.min_comb: self.min_comb = self.max_comb
            
        self.update_setting_ui()

    def update_setting_ui(self):
        self.setting_product.lbl_center.setText(f"제품명 : {self.product_name}")
        self.setting_target.lbl_center.setText(f"목표무게 : {self.target_weight:,} g")
        self.setting_min.lbl_center.setText(f"최소조합 : {self.min_comb} 개")
        self.setting_max.lbl_center.setText(f"최대조합 : {self.max_comb} 개")

    def dummy_register(self):
        QMessageBox.information(self, "제품 등록", "포도 품종 및 목표 무게 저장 시스템 연동 시에 지원됩니다.")

    def start_operation(self):
        self.is_running = True
        self.combo_val.setText("동작재개")
        self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=False))
        # 토글 표시
        self.btn_run.hide()
        self.btn_pause.show()
        
    def pause_operation(self):
        self.is_running = False
        self.combo_val.setText("일시정지")
        # 정지 시의 경고성 노란색 렌더링
        if self.is_dark_mode:
            self.combo_card.setStyleSheet("QFrame#ComboCard { border: 2px solid #D97706; background-color: #78350F; border-radius: 20px; }")
        else:
            self.combo_card.setStyleSheet("QFrame#ComboCard { border: 2px solid #F59E0B; background-color: #FEF3C7; border-radius: 20px; }")
        # 토글 표시
        self.btn_pause.hide()
        self.btn_run.show()

    def get_combo_card_style(self, highlight=True):
        if self.is_dark_mode:
            if highlight:
                return "QFrame#ComboCard { border: 2px solid #059669; background-color: #064E3B; border-radius: 20px; }"
            else:
                return "QFrame#ComboCard { border: 2px solid #333333; background-color: #1E1E1E; border-radius: 20px; }"
        else:
            if highlight:
                return "QFrame#ComboCard { border: 3px solid #10B981; background-color: #ECFDF5; border-radius: 20px; }"
            else:
                return "QFrame#ComboCard { border: 2px solid #E5E7EB; background-color: #FFFFFF; border-radius: 20px; }"
                
    def on_data_received(self, weights):
        self.weights = weights
        
        total = 0
        for i, w in enumerate(self.weights):
            if w > 0:
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: white;" if self.is_dark_mode else "color: #1F2937;")
            else:
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: #555555;" if self.is_dark_mode else "color: #9CA3AF;")
            
            # 카드 배경 기본화 (다크/라이트 모드 분기)
            if self.is_dark_mode:
                self.tray_cards[i].setStyleSheet("QFrame#Card { background-color: #1E1E1E; border-radius: 16px; border: 1px solid #333333; }")
            else:
                self.tray_cards[i].setStyleSheet("QFrame#Card { background-color: #FFFFFF; border-radius: 16px; border: 1px solid #E5E7EB; }")
                
            total += w
            
        self.sum_val_lbl.setText(f"{total:,} g")
        
        # 동작 중일 때만 조합 탐색
        if self.is_running:
            self.find_best_combination()

    def find_best_combination(self):
        target = self.target_weight
        min_c = self.min_comb
        max_c = self.max_comb
        
        valid_items = [(i+1, w) for i, w in enumerate(self.weights) if w > 0]
        
        best_combo = None
        best_diff = float('inf')
        best_sum = 0
        
        for r in range(min_c, max_c + 1):
            for combo in itertools.combinations(valid_items, r):
                combo_sum = sum(item[1] for item in combo)
                diff = combo_sum - target
                
                # 조건: 조합 무게는 목표 무게 '이상'이어야 함 (0g 미만 오차 제외)
                # 그 중 목표 무게에 가장 가까운 최저값(Upper bound 에러 한도: 100g)
                if 0 <= diff <= 100:
                    if diff < best_diff:
                        best_diff = diff
                        best_combo = combo
                        best_sum = combo_sum
                        
        if best_combo:
            self.combo_val.setText(f"{best_sum:,} g")
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=True))
            
            indices = [item[0] for item in best_combo]
            
            # 하이라이트할 카드 UI 색상 업데이트
            for idx in indices:
                card_index = idx - 1
                if self.is_dark_mode:
                    self.tray_cards[card_index].setStyleSheet("QFrame#Card { background-color: #064E3B; border-radius: 16px; border: 2px solid #059669; }")
                else:
                    self.tray_cards[card_index].setStyleSheet("QFrame#Card { background-color: #ECFDF5; border-radius: 16px; border: 2px solid #10B981; }")
            
            self.serial_thread.send_signal(indices)
        else:
            self.combo_val.setText("조합실패")
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=False))

    def closeEvent(self, event):
        self.serial_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFontDatabase, QFont
    from PyQt5.QtCore import Qt
    
    # GUI 속성은 QApplication 생성 전에 설정해야 함
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # 폰트 등 설정 (main_ui의 셋업을 일부 차용하여 안티앨리어싱 유지)
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                ui_font_family = families[0]
                default_font = app.font()
                default_font.setFamily(ui_font_family)
                default_font.setStyleStrategy(QFont.PreferAntialias)
                app.setFont(default_font)


    
    # Github OTA 점검
    check_ota_update()

    window = MainApp()
    window.show()
    sys.exit(app.exec_())
