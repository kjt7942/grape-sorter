import sys
import serial
import itertools
import subprocess
import os
import time
import random
import json

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer

from main_ui import SmartSorterUI, PresetDialog, CalibrationDialog

# 프로그램의 목표무게, 프리셋 정보를 저장할 파일 경로
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


class OTAThread(QThread):
    update_available = pyqtSignal()

    def run(self):
        try:
            subprocess.run(["git", "fetch"], timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            status = subprocess.run(["git", "status", "-uno"], capture_output=True, text=True)
            if "Your branch is behind" in status.stdout:
                self.update_available.emit() 
        except Exception as e:
            print("업데이트 확인 생략 (네트워크 또는 권한 문제):", e)


class SerialThread(QThread):
    data_received = pyqtSignal(list) 
    is_simulation = pyqtSignal(bool) 
    system_message = pyqtSignal(str) 

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
                    data = self.serial_port.read(max(1, self.serial_port.in_waiting)).decode('utf-8', errors='ignore')
                    if data:
                        buffer += data
                        if "[SYSTEM] 영점 조절 완료" in buffer:
                            self.system_message.emit("TARE_DONE")
                            buffer = buffer.replace("[SYSTEM] 영점 조절 완료! 정상 가동 재개.", "")
                            buffer = buffer.replace("[SYSTEM] 영점 조절 완료", "")

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
                print(f"아두이노 명령 전송 실패: {e}")

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
        
        self.raw_weights = [0] * 12 
        self.weights = [0] * 12     
        
        self.settings_data = self.load_settings()
        last_state = self.settings_data.get("last_state", {})
        
        self.target_weight = last_state.get("target_weight", 2050)
        self.min_comb = last_state.get("min_comb", 3)
        self.max_comb = last_state.get("max_comb", 4)
        self.is_dark_mode = last_state.get("is_dark_mode", True)
        self.current_preset_index = last_state.get("current_preset_index", None)
        self.is_topup_mode = last_state.get("is_topup_mode", False)
        
        self.cal_multipliers = self.settings_data.get("cal_multipliers", [1.0] * 12)
        self.cal_ref_weight = self.settings_data.get("cal_ref_weight", 1000)
        
        self.memo_min_comb = self.min_comb 
        self.cal_dialog = None
        self.cal_target_idx = 0
        
        self.setup_logic()
        
        self.tray_cards[0].doubleClicked.connect(QApplication.instance().quit)
        self.tray_cards[5].doubleClicked.connect(self.show_calibration_dialog) 
        self.tray_cards[6].doubleClicked.connect(self.restart_program) 
        self.tray_cards[11].doubleClicked.connect(self.shutdown_system) 
        
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(self.update_sim_mode_display)
        self.serial_thread.system_message.connect(self.on_system_message)
        self.serial_thread.start()
        
        self.start_ota_check()

    def start_ota_check(self):
        self.ota_thread = OTAThread()
        self.ota_thread.update_available.connect(self.prompt_ota_update)
        self.ota_thread.start()

    def prompt_ota_update(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("시스템 업데이트 알림")
        msg_box.setText("새로운 시스템(및 아두이노 펌웨어) 업데이트가 발견되었습니다.\n적용하시겠습니까?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        
        if msg_box.exec() == QMessageBox.Yes:
            subprocess.run(["git", "reset", "--hard"], check=True)
            subprocess.run(["git", "pull"], check=True)
            
            arduino_port = None
            if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
                arduino_port = self.serial_thread.serial_port.port
            self.serial_thread.stop()
            time.sleep(1.5) 
            
            firmware_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arduino_firmware")
            if arduino_port and os.path.exists(firmware_dir):
                print(f"[OTA] 아두이노 펌웨어 자동 업데이트 시작 (포트: {arduino_port})")
                try:
                    fqbn = "arduino:avr:mega:cpu=atmega2560"
                    compile_cmd = ["arduino-cli", "compile", "--fqbn", fqbn, firmware_dir]
                    upload_cmd = ["arduino-cli", "upload", "-p", arduino_port, "--fqbn", fqbn, firmware_dir]
                    
                    subprocess.run(compile_cmd, check=True)
                    subprocess.run(upload_cmd, check=True)
                    print("[OTA] 아두이노 메가 2560 펌웨어 업데이트 완벽 성공!")
                except Exception as e:
                    print(f"[OTA] 펌웨어 업로드 실패: {e}")
            
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
                    if "cal_multipliers" not in data or len(data["cal_multipliers"]) < 12:
                        data["cal_multipliers"] = [1.0] * 12
                    if "cal_ref_weight" not in data:
                        data["cal_ref_weight"] = 1000
                    return data
            except Exception as e:
                print(f"설정 불러오기 실패: {e}")
        return {"last_state": {}, "presets": [None] * 8, "cal_multipliers": [1.0] * 12, "cal_ref_weight": 1000}

    def save_settings(self):
        self.settings_data["last_state"] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb,
            "is_dark_mode": self.is_dark_mode,
            "current_preset_index": self.current_preset_index,
            "is_topup_mode": self.is_topup_mode 
        }
        self.settings_data["cal_multipliers"] = self.cal_multipliers
        self.settings_data["cal_ref_weight"] = self.cal_ref_weight
        
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
            self.on_data_received(self.raw_weights)
            
        self.btn_theme_toggle.clicked.disconnect() 
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

    # ✨ 저울 보정 다이얼로그 호출 및 쾌속 조절 엔진 ✨
    def show_calibration_dialog(self):
        self.cal_dialog = CalibrationDialog(self, is_dark_mode=self.is_dark_mode, ref_weight=self.cal_ref_weight)
        self.cal_target_idx = 0
        
        # 🌟 수술 포인트: 클릭 시 1g, 꾹 누르면(mult=5) 10g씩 빠르게 조절!
        self.cal_dialog.btn_minus.stepTriggered.connect(lambda mult: self.modify_ref_weight(-1 if mult == 1 else -10))
        self.cal_dialog.btn_plus.stepTriggered.connect(lambda mult: self.modify_ref_weight(1 if mult == 1 else 10))
        
        self.cal_dialog.btn_apply.clicked.connect(self.apply_current_calibration)
        self.cal_dialog.btn_skip.clicked.connect(self.advance_cal_target)
        self.cal_dialog.btn_close.clicked.connect(self.cal_dialog.accept)
        
        self.cal_dialog.exec_()
        self.cal_dialog = None
        self.save_settings()

    def modify_ref_weight(self, delta):
        self.cal_ref_weight = max(10, self.cal_ref_weight + delta) # 최소 10g 방어
        if self.cal_dialog:
            self.cal_dialog.lbl_ref_weight.setText(f"무게추: {self.cal_ref_weight:,} g")

    def apply_current_calibration(self):
        idx = self.cal_target_idx
        if idx >= 12: return
        
        raw_w = self.raw_weights[idx]
        if raw_w <= 0:
            self.show_message("저울에 무게가 감지되지 않았습니다.\n분동을 올려주세요.")
            QTimer.singleShot(1500, self.hide_message)
            return
            
        current_disp = raw_w * self.cal_multipliers[idx]
        if current_disp > 0:
            ratio = self.cal_ref_weight / current_disp
            self.cal_multipliers[idx] *= ratio
            
        self.advance_cal_target()
        self.save_settings() 

    def advance_cal_target(self):
        self.cal_target_idx += 1
        self.update_cal_dialog_ui()

    def update_cal_dialog_ui(self):
        if not self.cal_dialog or not self.cal_dialog.isVisible(): return
        
        # 🚨 에러(ERR) 카드 자동 패스 로직
        while self.cal_target_idx < 12 and self.raw_weights[self.cal_target_idx] == -1:
            self.cal_target_idx += 1
            
        if self.cal_target_idx >= 12:
            self.show_message("모든 저울 보정이 완료되었습니다.")
            QTimer.singleShot(2000, self.hide_message)
            self.cal_dialog.accept()
            return

        for i in range(12):
            w = self.raw_weights[i]
            card = self.cal_dialog.cal_cards[i]
            lbl = self.cal_dialog.cal_labels[i]
            
            if w == -1:
                lbl.setText("ERR")
                lbl.setStyleSheet("color: #EF4444;")
                card.setStyleSheet("QFrame { background-color: #451A1A; border: 2px solid #7F1D1D; border-radius: 12px; }") if self.is_dark_mode else card.setStyleSheet("QFrame { background-color: #FEE2E2; border: 2px solid #FCA5A5; border-radius: 12px; }")
            else:
                disp_w = int(w * self.cal_multipliers[i])
                lbl.setText(f"{disp_w:,} g")
                lbl.setStyleSheet("color: white;" if self.is_dark_mode else "color: #1F2937;")
                
                if i == self.cal_target_idx:
                    card.setStyleSheet("QFrame { background-color: #2563EB; border: 3px solid #60A5FA; border-radius: 12px; }")
                    lbl.setStyleSheet("color: white; font-weight: bold;")
                else:
                    card.setStyleSheet("QFrame { background-color: #2D2D2D; border: 2px solid #404040; border-radius: 12px; }") if self.is_dark_mode else card.setStyleSheet("QFrame { background-color: #F3F4F6; border: 2px solid #D1D5DB; border-radius: 12px; }")


    def toggle_topup_mode(self):
        self.is_topup_mode = not self.is_topup_mode
        if self.is_topup_mode:
            self.memo_min_comb = self.min_comb
            self.min_comb = 1 
        else:
            self.min_comb = self.memo_min_comb
            
        self.update_topup_ui()
        self.update_setting_ui()
        self.on_data_received(self.raw_weights)

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
        self.show_message("영점 조정 중입니다.\n저울에서 손을 떼세요.")
        if self.serial_thread.serial_port and self.serial_thread.serial_port.is_open:
            self.serial_thread.serial_port.write(b"<TARE>\n")
        else:
            print("[시뮬-TARE] 영점 조절 명령 시뮬레이션")
            QTimer.singleShot(2000, lambda: self.on_system_message("TARE_DONE"))

    def on_system_message(self, msg):
        if msg == "TARE_DONE":
            self.show_message("영점 조정이 완료되었습니다.")
            QTimer.singleShot(2000, self.hide_message) 

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
                
    def on_data_received(self, raw_weights):
        self.raw_weights = raw_weights
        
        calibrated_weights = []
        for i, w in enumerate(raw_weights):
            if w > 0:
                calibrated_weights.append(int(w * self.cal_multipliers[i]))
            else:
                calibrated_weights.append(w)
                
        self.weights = calibrated_weights
        
        if self.cal_dialog and self.cal_dialog.isVisible():
            self.update_cal_dialog_ui()
        
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