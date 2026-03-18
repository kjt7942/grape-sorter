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

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

def check_ota_update():
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
                os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        print("OTA 업데이트 확인 스킵:", e)


class SerialThread(QThread):
    data_received = pyqtSignal(list)
    is_simulation = pyqtSignal(bool)

    def __init__(self, ports=['/dev/ttyACM0', '/dev/ttyUSB0', 'COM3', 'COM4', 'COM5'], baudrate=115200):
        super().__init__()
        self.ports = ports
        self.baudrate = baudrate
        self.serial_port = None
        self.running = True

    def run(self):
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
                fake_weights = []
                for _ in range(12):
                    chance = random.random()
                    if chance > 0.10: 
                        fake_weights.append(random.randint(450, 1100))
                    elif chance > 0.02: 
                        fake_weights.append(0)
                    else: 
                        fake_weights.append(-1)
                        
                self.data_received.emit(fake_weights)
                time.sleep(1) 

    def parse_packet(self, packet):
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
        if self.serial_port and self.serial_port.is_open:
            msg = f"<{','.join(map(str, indices))}>\n"
            try:
                self.serial_port.write(msg.encode('utf-8'))
            except Exception as e:
                print(f"시리얼 데이터 송신 오류: {e}")
        else:
            print(f"[시뮬레이션] LED 점등 대상 트레이: <{','.join(map(str, indices))}>")

    def stop(self):
        self.running = False
        self.wait()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()


class MainApp(SmartSorterUI):
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
        
        self.setup_logic()
        
        self.tray_cards[0].doubleClicked.connect(QApplication.instance().quit)
        self.tray_cards[6].doubleClicked.connect(self.restart_program) 
        self.tray_cards[11].doubleClicked.connect(self.shutdown_system) 
        
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(self.update_sim_mode_display)
        self.serial_thread.start()

    # ✨ 핵심: 기존 4개짜리 DB 데이터를 불러와도 에러나지 않고 8개로 자동 연장(호환성 패치)
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
                print(f"설정 파일 읽기 오류: {e}")
        return {
            "last_state": {},
            "presets": [None] * 8 
        }

    def save_settings(self):
        self.settings_data["last_state"] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb,
            "is_dark_mode": self.is_dark_mode,
            "current_preset_index": self.current_preset_index 
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"설정 파일 저장 오류: {e}")

    def closeEvent(self, event):
        print("프로그램 종료 전 마지막 상태를 저장합니다...")
        self.save_settings()
        self.serial_thread.stop()
        super().closeEvent(event)

    def restart_program(self):
        print("프로그램 재시작을 수행합니다...")
        self.save_settings()
        self.serial_thread.stop()
        os.execv(sys.executable, ['python'] + sys.argv)

    def shutdown_system(self):
        print("라즈베리파이 시스템을 종료합니다...")
        self.save_settings()
        self.serial_thread.stop()
        os.system("sudo shutdown now")

    def update_sim_mode_display(self, is_sim):
        if is_sim:
            self.lbl_sum_title.setText("합계(시뮬모드)")
            self.lbl_sum_title.setStyleSheet("color: #EF4444;" if not self.is_dark_mode else "color: #F87171;")
        else:
            self.lbl_sum_title.setText("합계")
            self.lbl_sum_title.setStyleSheet("")

    def setup_logic(self):
        self.update_setting_ui()
        self.apply_theme() 
        
        self.btn_tare.clicked.connect(self.send_tare_command)
        self.btn_register.clicked.connect(self.show_preset_dialog) 
        
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
        self.btn_theme_toggle.clicked.disconnect() 
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

    # ✨ 업데이트: 8구역 순환 로직 적용
    def cycle_preset(self, direction):
        presets = self.settings_data.get("presets", [])
        if len(presets) < 8:
            presets.extend([None] * (8 - len(presets)))
            
        if not any(presets):
            return 
            
        idx = self.current_preset_index if self.current_preset_index is not None else 0
        
        for _ in range(8): 
            idx = (idx + direction) % 8
            if presets[idx] is not None:
                self.load_preset(idx, dialog=None) 
                break

    def show_preset_dialog(self):
        dialog = PresetDialog(self, is_dark_mode=self.is_dark_mode)
        presets = self.settings_data.get("presets", [])
        if len(presets) < 8:
            presets.extend([None] * (8 - len(presets)))
            self.settings_data["presets"] = presets
            
        # ✨ 핵심: 비우기 버튼 클릭 시 경고창 호출 로직 연결
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

    # ✨ 신규: 8개 슬롯 모두 초기화 및 경고창
    def clear_all_presets(self, dialog):
        reply = QMessageBox.warning(
            dialog, 
            "초기화 경고", 
            "정말로 등록된 8개의 제품 슬롯을 모두 비우시겠습니까?\n이 작업은 되돌릴 수 없습니다.", 
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.settings_data["presets"] = [None] * 8
            self.current_preset_index = None
            self.save_settings()
            self.update_setting_ui()
            
            # 팝업창 UI 즉시 갱신 (비어있음으로 되돌리기)
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
            if dialog:
                dialog.accept() 
        else:
            if dialog:
                QMessageBox.warning(dialog, "알림", "해당 슬롯은 비어있습니다. 길게 눌러 현재 설정을 저장하세요.")

    def save_preset(self, index, button_widget, slot_name):
        presets = self.settings_data.get("presets", [None] * 8)
        presets[index] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb
        }
        self.settings_data["presets"] = presets
        self.save_settings() 
        
        p = presets[index]
        button_widget.setText(f"슬롯 {slot_name}\n{p['target_weight']}g\n({p['min_comb']}~{p['max_comb']}개)\n[저장됨!]")
        button_widget.setStyleSheet("background-color: #059669; color: white;") 
        
        self.current_preset_index = index 
        self.update_setting_ui()

    def send_tare_command(self):
        if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
            try:
                self.serial_thread.serial_port.write(b"<TARE>\n")
                print("[시리얼 송신] 영점 조절 명령 전송: <TARE>")
            except Exception as e:
                print(f"시리얼 데이터 송신 오류: {e}")
        else:
            print("[시뮬레이션] 영점 조절 명령 전송: <TARE>")

    def keyPressEvent(self, event):
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
            self.target_weight = max(100, self.target_weight + delta) 
        elif kind == 'min':
            self.min_comb = max(1, min(12, self.min_comb + delta))
            if self.min_comb > self.max_comb: self.max_comb = self.min_comb
        elif kind == 'max':
            self.max_comb = max(1, min(12, self.max_comb + delta))
            if self.max_comb < self.min_comb: self.min_comb = self.max_comb
            
        self.current_preset_index = None 
        self.update_setting_ui()

    def update_setting_ui(self):
        preset_text = f"{self.target_weight:,}g({self.min_comb}~{self.max_comb}개)"
        
        if self.current_preset_index is not None:
            # ✨ 업데이트: 메인 화면 표시용 슬롯 이름도 8개로 확장
            slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
            display_text = f"슬롯 {slot_names[self.current_preset_index]} : {preset_text}"
        else:
            display_text = f"수동설정 : {preset_text}"
            
        self.setting_product.lbl_center.setText(display_text)
        self.setting_target.lbl_center.setText(f"목표무게 : {self.target_weight:,} g")
        self.setting_min.lbl_center.setText(f"최소조합 : {self.min_comb} 개")
        self.setting_max.lbl_center.setText(f"최대조합 : {self.max_comb} 개")

    def dummy_register(self):
        pass 

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
                total += w
            elif w == -1: 
                self.tray_weight_labels[i].setText("에러(ERR)")
                self.tray_weight_labels[i].setStyleSheet("color: #EF4444; font-weight: bold;") 
            else: 
                self.tray_weight_labels[i].setText(f"{w:,} g")
                self.tray_weight_labels[i].setStyleSheet("color: #555555;" if self.is_dark_mode else "color: #9CA3AF;")
            
            if self.is_dark_mode:
                self.tray_cards[i].setStyleSheet("QFrame#Card { background-color: #1E1E1E; border-radius: 16px; border: 1px solid #333333; }")
            else:
                self.tray_cards[i].setStyleSheet("QFrame#Card { background-color: #FFFFFF; border-radius: 16px; border: 1px solid #E5E7EB; }")
                
        self.sum_val_lbl.setText(f"{total:,} g")
        
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
                
                if 0 <= diff <= 100:
                    if diff < best_diff:
                        best_diff = diff
                        best_combo = combo
                        best_sum = combo_sum
                        
        if best_combo:
            self.combo_val.setText(f"{best_sum:,} g")
            self.combo_card.setStyleSheet(self.get_combo_card_style(highlight=True))
            
            indices = [item[0] for item in best_combo]
            
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
            self.serial_thread.send_signal([])

    def closeEvent(self, event):
        print("프로그램 종료 전 마지막 상태를 저장합니다...")
        self.save_settings()
        self.serial_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFontDatabase, QFont
    from PyQt5.QtCore import Qt
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
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

    check_ota_update()

    window = MainApp()
    window.show()
    sys.exit(app.exec_())