import sys
import serial
import itertools
import subprocess
import os
import time
import random
import json
import csv
import shutil
import logging
import collections
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer

from main_ui import SmartSorterUI, PresetDialog, CalibrationDialog, ScaleCheckDialog

# 모든 파일 경로와 git 명령의 기준점. 실행 위치(CWD)에 의존하지 않게 하기 위함.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
BACKUP_FILE = os.path.join(BASE_DIR, "settings.backup.json")
LOG_FILE = os.path.join(BASE_DIR, "sorter.log")
PRODUCTION_FILE = os.path.join(BASE_DIR, "production.csv")
FIRMWARE_DIR = os.path.join(BASE_DIR, "arduino_firmware")

LOADCELL_COUNT = 12
DEFAULT_TOLERANCE = 50   # 목표무게 초과 허용치(g)
TOLERANCE_MAX = 500
SLOT_NAMES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
DEFAULT_REF_WEIGHT = 430          # 현장 분동 무게(g)
CAL_RATIO_MIN, CAL_RATIO_MAX = 0.5, 2.0   # 허용 배율 범위. 벗어나면 분동/저울을 잘못 짚은 것
TARE_DRIFT_WARN = 100             # 지난 영점 대비 이만큼(g) 이상 차이 나면 접시 위 이물 의심

# 가짜 무게를 만드는 시뮬레이션은 개발용이다. 현장 기기(라즈베리파이)에서
# 가짜 데이터가 화면에 뜨면 조작자가 정상으로 오인하므로 원천 차단한다.
ALLOW_SIMULATION = sys.platform == 'win32'

# 키오스크 모드에서는 콘솔이 X 화면에 가려져 print() 출력을 볼 수 없다.
# 현장 사후 분석을 위해 파일로 남긴다.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("sorter")


def git(*args, **kwargs):
    """항상 소스 디렉토리를 대상으로 git 실행."""
    kwargs.setdefault("cwd", BASE_DIR)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(["git", *args], **kwargs)


def firmware_expected_version():
    """아두이노 펌웨어에 기대되는 버전 = arduino_firmware/ 를 마지막으로 건드린 커밋 해시.

    HEAD를 쓰면 파이썬 코드만 고쳐도 '펌웨어 불일치' 오탐이 난다.
    """
    try:
        out = git("log", "-1", "--format=%h", "--", "arduino_firmware", timeout=5)
        return out.stdout.strip() or None
    except Exception as e:
        log.warning("펌웨어 기대 버전 확인 실패: %s", e)
        return None


ComboResult = collections.namedtuple("ComboResult", "combo total near_total")


def best_combination(items, target, min_c, max_c, tolerance, excluded=()):
    """목표무게를 넘되 초과분이 tolerance 이내인 조합 중 가장 근접한 것.

    items:    [(1-based 저울번호, 무게), ...]
    excluded: 제외할 저울번호 집합들. 조작자가 거절한 조합을 다시 내놓지 않기 위함.
    반환:     ComboResult(조합 튜플|None, 합계, 목표 미달 최대 합계|None)

    near_total 은 조합 실패 시 "얼마나 모자란지" 화면에 알려주기 위한 참고값이며
    출하 후보가 아니다. 목표 미달 조합은 절대 선택하지 않는다.

    동점이면 저울을 더 많이 쓰는 조합을 택한다(작은 송이부터 소진).
    12개 전체 부분집합이 4095가지뿐이라 완전 탐색으로 충분하다.
    """
    best_combo, best_sum = None, 0
    best_diff = float('inf')
    near_total = None
    for r in range(max(1, min_c), min(max_c, len(items)) + 1):
        for combo in itertools.combinations(items, r):
            combo_sum = sum(w for _, w in combo)
            diff = combo_sum - target
            if diff < 0:
                if near_total is None or combo_sum > near_total:
                    near_total = combo_sum
                continue
            if diff > tolerance:
                continue
            if frozenset(i for i, _ in combo) in excluded:
                continue
            if diff < best_diff or (diff == best_diff and len(combo) > len(best_combo)):
                best_diff, best_combo, best_sum = diff, combo, combo_sum
    return ComboResult(best_combo, best_sum, near_total)


class OTAThread(QThread):
    update_available = pyqtSignal()

    def run(self):
        try:
            git("fetch", timeout=20, check=True)
            status = git("status", "-uno", timeout=10)
            if "Your branch is behind" in status.stdout:
                self.update_available.emit()
        except Exception as e:
            log.info("업데이트 확인 생략 (네트워크 또는 권한 문제): %s", e)


FALLBACK_PORTS = ['/dev/ttyACM0', '/dev/ttyACM1', '/dev/ttyUSB0', '/dev/ttyUSB1',
                  'COM3', 'COM4', 'COM5']


def candidate_ports():
    """실제로 존재하는 직렬 포트를 우선 시도하고, 못 찾으면 알려진 경로로 폴백."""
    found = []
    try:
        from serial.tools import list_ports
        found = [p.device for p in list_ports.comports()]
    except Exception as e:
        log.warning("직렬 포트 목록 조회 실패: %s", e)
    return found + [p for p in FALLBACK_PORTS if p not in found]


class SerialThread(QThread):
    data_received = pyqtSignal(list)
    # True = 아두이노 데이터 없음. 두 번째 값은 '한 번 연결됐다가 끊긴 것'인지 여부.
    is_simulation = pyqtSignal(bool, bool)
    system_message = pyqtSignal(str)
    firmware_version_received = pyqtSignal(str)
    tare_offsets_received = pyqtSignal(list)

    RECONNECT_INTERVAL = 2.0

    def __init__(self, baudrate=115200):
        super().__init__()
        self.baudrate = baudrate
        self.serial_port = None
        self.running = True
        self.sim_weights = [0] * LOADCELL_COUNT
        self.had_connection = False   # 한 번이라도 실제 장치에 붙었는지
        self._buffer = ""
        self._last_connect_try = 0.0
        self._sim_seeded = False
        self._silent_reads = 0

    # --- 연결 관리 -------------------------------------------------------
    def _try_connect(self):
        """포트 하나씩 열어본다. 성공하면 True."""
        now = time.time()
        if now - self._last_connect_try < self.RECONNECT_INTERVAL:
            time.sleep(0.2)
            return False
        self._last_connect_try = now

        for p in candidate_ports():
            try:
                self.serial_port = serial.Serial(p, self.baudrate, timeout=1)
            except Exception:
                continue
            self._buffer = ""
            log.info("[%s] 아두이노 하드웨어 연결 성공", p)
            self.had_connection = True
            self.is_simulation.emit(False, False)
            return True
        return False

    def _drop_connection(self, reason):
        """USB가 빠지거나 통신이 깨졌을 때 포트를 닫고 재연결 대기 상태로 되돌린다."""
        log.error("시리얼 연결 해제 (%s)", reason)
        try:
            if self.serial_port:
                self.serial_port.close()
        except Exception:
            pass
        self.serial_port = None
        self._buffer = ""
        self.is_simulation.emit(True, self.had_connection)

    # --- 수신 처리 -------------------------------------------------------
    def _pump(self):
        try:
            chunk = self.serial_port.read(max(1, self.serial_port.in_waiting))
        except Exception as e:
            self._drop_connection(f"읽기 오류: {e}")
            return
        if not chunk:
            # timeout=1초. 포트를 열면 메가가 리셋되어 부팅+영점에 3초쯤 걸리므로
            # 그보다 넉넉히 기다린 뒤에 죽은 것으로 판정한다.
            self._silent_reads += 1
            if self._silent_reads >= 8:
                self._silent_reads = 0
                self._drop_connection("8초간 데이터 없음")
            return
        self._silent_reads = 0

        self._buffer += chunk.decode('utf-8', errors='ignore')
        self._consume_buffer()

        # 잘린 쓰레기 데이터가 무한히 쌓이지 않도록 상한을 둔다.
        if len(self._buffer) > 4096:
            log.warning("수신 버퍼 과다 누적, 버림")
            self._buffer = ""

    @staticmethod
    def _take_tagged_line(buffer, tag):
        """buffer 에서 '<tag> ...\\n' 한 줄을 떼어낸다. (내용, 남은 버퍼) 또는 (None, 버퍼)."""
        if tag not in buffer:
            return None, buffer
        after = buffer.split(tag, 1)[1]
        line_end = after.find("\n")
        if line_end == -1:
            return None, buffer
        return after[:line_end].strip(), buffer.split(tag, 1)[0] + after[line_end + 1:]

    def _consume_buffer(self):
        buffer = self._buffer

        # [TARE] 를 TARE_DONE 보다 먼저 처리해야 화면이 오프셋을 손에 쥔 상태로
        # 완료 통보를 받는다. 신호 발신 순서가 곧 수신 순서다.
        while True:
            line, buffer = self._take_tagged_line(buffer, "[TARE]")
            if line is None:
                break
            try:
                offsets = [int(x) for x in line.split(",")]
            except ValueError:
                log.warning("[TARE] 파싱 실패: %r", line)
                continue
            if len(offsets) == LOADCELL_COUNT:
                self.tare_offsets_received.emit(offsets)

        if "[SYSTEM] 영점 조절 완료" in buffer:
            self.system_message.emit("TARE_DONE")
            buffer = buffer.replace("[SYSTEM] 영점 조절 완료! 정상 가동 재개.", "")
            buffer = buffer.replace("[SYSTEM] 영점 조절 완료", "")

        while True:
            version, buffer = self._take_tagged_line(buffer, "[VER]")
            if version is None:
                break
            self.firmware_version_received.emit(version)

        while '<' in buffer and '>' in buffer:
            start = buffer.find('<')
            end = buffer.find('>', start)
            if end == -1:
                break
            packet = buffer[start + 1:end]
            buffer = buffer[end + 1:]
            self.parse_packet(packet)

        self._buffer = buffer

    def _simulate(self):
        if self.had_connection or not ALLOW_SIMULATION:
            # 장치가 빠졌거나(연결 끊김) 아직 안 켜진 상태(부팅 순서). 어느 쪽이든
            # 가짜 무게를 뿌리면 조작자가 정상으로 오인하므로 전 채널 에러로 표시한다.
            if not self._sim_seeded:
                self._sim_seeded = True
                self.is_simulation.emit(True, self.had_connection)
            self.data_received.emit([-1] * LOADCELL_COUNT)
            time.sleep(1)
            return

        if not self._sim_seeded:
            self._sim_seeded = True
            log.info("아두이노 장치 없음: 시뮬레이션 모드 활성화")
            for i in range(LOADCELL_COUNT):
                if random.random() > 0.1:
                    self.sim_weights[i] = random.randint(500, 1000)
            self.is_simulation.emit(True, False)

        for i in range(LOADCELL_COUNT):
            if self.sim_weights[i] == 0 and random.random() < 0.05:
                self.sim_weights[i] = random.randint(500, 1000)
        self.data_received.emit(list(self.sim_weights))
        time.sleep(1)

    def run(self):
        # ponytail: 포트 객체에 락을 걸지 않았다. GUI 스레드의 send_signal 이 쓰기
        # 오류로 포트를 닫는 순간 이 루프가 읽는 중일 수 있으나, 양쪽 모두 예외를
        # 잡아 재연결로 흘러가므로 최악의 경우 재연결 한 번이 더 돈다.
        # 재연결이 눈에 띄게 잦아지면 threading.Lock 을 도입할 것.
        while self.running:
            if self.serial_port is None:
                if not self._try_connect():
                    self._simulate()
                continue
            self._pump()

    def parse_packet(self, packet):
        parts = packet.split(',')
        if len(parts) == LOADCELL_COUNT:
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

    # --- 송신 ------------------------------------------------------------
    def _write(self, payload, what):
        port = self.serial_port
        if not (port and port.is_open):
            return False
        try:
            port.write(payload)
            return True
        except Exception as e:
            log.error("%s 실패: %s", what, e)
            self._drop_connection(f"쓰기 오류: {e}")
            return False

    def send_signal(self, indices):
        return self._write(f"<{','.join(map(str, indices))}>\n".encode('utf-8'), "아두이노 명령 전송")

    def send_tare(self):
        return self._write(b"<TARE>\n", "영점 명령 전송")

    def request_firmware_version(self):
        return self._write(b"<VER>\n", "펌웨어 버전 요청")

    def is_connected(self):
        return bool(self.serial_port and self.serial_port.is_open)

    def stop(self):
        self.running = False
        self.wait(3000)
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
        except Exception:
            pass
        self.serial_port = None


class MainApp(SmartSorterUI):
    def __init__(self):
        super().__init__()
        if sys.platform == 'win32':
            self.showNormal() 
        else:
            self.showFullScreen() 
        
        self.raw_weights = [0] * LOADCELL_COUNT
        self.weights = [0] * LOADCELL_COUNT
        # 보정 시 순간값 대신 평균을 쓰기 위한 최근 원시값 이력
        self.raw_history = deque(maxlen=8)

        self.settings_data = self.load_settings()
        last_state = self.settings_data.get("last_state", {})

        self.target_weight = last_state.get("target_weight", 2050)
        self.min_comb = last_state.get("min_comb", 3)
        self.max_comb = last_state.get("max_comb", 4)
        self.tolerance = last_state.get("tolerance", DEFAULT_TOLERANCE)
        self.is_dark_mode = last_state.get("is_dark_mode", True)
        self.current_preset_index = last_state.get("current_preset_index", None)
        self.is_topup_mode = last_state.get("is_topup_mode", False)

        self.cal_multipliers = self.settings_data.get("cal_multipliers", [1.0] * LOADCELL_COUNT)
        self.cal_ref_weight = self.settings_data.get("cal_ref_weight", DEFAULT_REF_WEIGHT)

        self.memo_min_comb = self.min_comb
        self.cal_dialog = None
        self.cal_target_idx = 0
        self.scale_check_dialog = None
        self.cal_waiting_tare = False
        self.expected_firmware_version = None
        self.disconnected = False
        self._last_led = None      # 마지막으로 아두이노에 보낸 LED 인덱스 집합

        self.locked_combo = None
        self.locked_sum = 0
        self.locked_target = self.target_weight
        self.original_locked_indices = []
        # 조작자가 조합무게 카드를 눌러 거절한 조합들. 저울 구성이 바뀌면 비운다.
        self.rejected_combos = set()
        self._occupancy = None

        # 시작 준비 절차 상태
        self.startup_active = False
        self.startup_queue = []
        self.pending_tare_offsets = None
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self._play_startup_frame)
        self.startup_timeout = QTimer(self)
        self.startup_timeout.setSingleShot(True)
        self.startup_timeout.timeout.connect(
            lambda: self.finish_startup("아두이노가 영점 완료를 알리지 않음"))

        self.setup_logic()

        # 🌟 수술: 각 카드별 워터마크 기능 완벽 매칭
        self.tray_cards[0].doubleClicked.connect(QApplication.instance().quit)
        self.tray_cards[5].doubleClicked.connect(self.show_calibration_dialog)
        self.tray_cards[6].doubleClicked.connect(self.restart_program)
        self.tray_cards[10].doubleClicked.connect(self.reboot_system) # 11번 카드: 리눅스 재부팅
        self.tray_cards[11].doubleClicked.connect(self.shutdown_system)

        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.is_simulation.connect(self.update_sim_mode_display)
        self.serial_thread.system_message.connect(self.on_system_message)
        self.serial_thread.firmware_version_received.connect(self.on_firmware_version_received)
        self.serial_thread.tare_offsets_received.connect(self.on_tare_offsets)
        self.serial_thread.start()

        self.start_ota_check()

    # ------------------------------------------------------------------
    # 시작 준비 절차: LED 안내 → 영점 → 사용 가능
    # ------------------------------------------------------------------
    ALL_LEDS = list(range(1, LOADCELL_COUNT + 1))

    def startup_frames(self):
        """LED 안내 화면. (켤 저울 목록, 유지 시간 ms) 순서대로 재생한다.

        아두이노는 영점을 잡는 ~2초 동안 loop() 가 멈춰 명령을 못 받는다.
        그래서 순차 훑기를 영점 '전에' 끝내고, 영점 중에는 LED를 정지시킨다.
        """
        frames = []
        for _ in range(2):                                   # 전체 깜빡 ×2
            frames.append((self.ALL_LEDS, 160))
            frames.append(([], 160))
        for i in self.ALL_LEDS:                              # 순차 1→12
            frames.append(([i], 110))
        frames.append(([], 150))
        return frames

    def begin_startup(self, reason):
        if self.startup_active:
            return
        if not self.serial_thread.is_connected():
            return
        log.info("시작 준비 절차 시작 (%s)", reason)
        self.startup_active = True
        self.startup_queue = list(self.startup_frames())
        self.locked_combo = None
        self.locked_sum = 0
        self.original_locked_indices = []
        self.rejected_combos.clear()
        self.show_message("저울 준비중\n접시를 비우고 손을 떼세요")
        self._play_startup_frame()

    def _play_startup_frame(self):
        if not self.startup_active:
            return
        if not self.startup_queue:
            self._startup_tare()
            return
        leds, hold_ms = self.startup_queue.pop(0)
        self.serial_thread.send_signal(leds)
        self.startup_timer.start(hold_ms)

    def _startup_tare(self):
        self.serial_thread.send_signal([])
        self.show_message("저울 영점 잡는 중\n손을 떼세요")
        self.pending_tare_offsets = None
        if not self.serial_thread.send_tare():
            self.finish_startup("영점 명령 전송 실패")
            return
        # 아두이노가 응답하지 않아도 화면이 잠기지 않도록 시한을 둔다.
        self.startup_timeout.start(12000)

    def on_startup_tare_done(self):
        """아두이노가 영점을 마쳤다. 마무리 깜빡임 후 사용 가능 상태로."""
        self.startup_timeout.stop()
        self.startup_queue = []
        for _ in range(3):
            self.startup_queue.append((self.ALL_LEDS, 130))
            self.startup_queue.append(([], 130))
        self.show_message("저울 준비 완료")
        self._play_finish_frame()

    def _play_finish_frame(self):
        if self.startup_queue:
            leds, hold_ms = self.startup_queue.pop(0)
            self.serial_thread.send_signal(leds)
            QTimer.singleShot(hold_ms, self._play_finish_frame)
            return
        self.finish_startup(None)

    def finish_startup(self, error):
        self.startup_timer.stop()
        self.startup_timeout.stop()
        self.startup_active = False
        self.startup_queue = []
        self._last_led = None            # 준비 중 쏜 LED와 무관하게 다시 보내도록
        self.serial_thread.send_signal([])

        warning = self.check_tare_offsets(self.pending_tare_offsets)
        self.pending_tare_offsets = None

        if error:
            log.error("시작 준비 절차 실패: %s", error)
            self.show_message(f"저울 준비 실패\n{error}", 5000)
        elif warning:
            self.show_message(warning, 7000)
        else:
            self.hide_message()

        self.on_data_received(self.raw_weights)

    def on_tare_offsets(self, offsets):
        """아두이노가 방금 0으로 만든 무게(g). 준비 절차 밖에서도 기록해 둔다."""
        self.pending_tare_offsets = offsets
        if not self.startup_active:
            warning = self.check_tare_offsets(offsets)
            if warning:
                self.show_message(warning, 7000)
            self.pending_tare_offsets = None

    def check_tare_offsets(self, offsets):
        """지난 영점과 크게 달라진 채널을 찾아 경고 문구를 만들고, 기준값을 갱신한다."""
        if not offsets:
            return None

        previous = self.settings_data.get("tare_offsets")
        suspects = []
        if isinstance(previous, list) and len(previous) == len(offsets):
            for i, (now, before) in enumerate(zip(offsets, previous)):
                # 연결되지 않은 채널은 아두이노가 오프셋을 갱신하지 못해 0으로 보고한다.
                # 배선이 늘거나 줄면 0 <-> 접시무게로 튀는데, 이건 접시 위 이물이
                # 아니라 하드웨어 구성 변경이므로 경고 대상이 아니다.
                if now == 0 or before == 0:
                    continue
                if abs(now - before) >= TARE_DRIFT_WARN:
                    suspects.append((i + 1, now - before))

        self.settings_data["tare_offsets"] = offsets
        self.save_settings()

        if not suspects:
            return None

        log.warning("영점 기준이 크게 변한 채널: %s",
                    ", ".join(f"{n}번 {d:+d}g" for n, d in suspects))
        names = ", ".join(f"{n}번" for n, _ in suspects)
        return (f"주의: {names} 접시에 물건이\n올려진 채 영점을 잡았을 수 있습니다.\n"
                f"접시를 비우고 영점을 다시 잡으세요.")

    def set_cached_style(self, widget, style_str):
        if getattr(widget, '_cached_style', None) != style_str:
            widget.setStyleSheet(style_str)
            widget._cached_style = style_str

    def start_ota_check(self):
        self.ota_thread = OTAThread()
        self.ota_thread.update_available.connect(self.prompt_ota_update)
        self.ota_thread.start()

    def prompt_ota_update(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("시스템 업데이트 알림")
        msg_box.setText("새로운 시스템 업데이트가 발견되었습니다.\n지금 바로 적용하시겠습니까?")
        
        msg_box.setStyleSheet("""
            QMessageBox { background-color: #2D2D2D; }
            QLabel { color: #FFFFFF; font-size: 18px; font-weight: bold; }
            QPushButton { 
                background-color: #2563EB; color: white; 
                font-size: 16px; font-weight: bold; 
                padding: 10px 20px; border-radius: 8px; min-width: 100px; 
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText("예 (적용하기)")
        msg_box.button(QMessageBox.No).setText("아니오 (나중에)")
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        
        if msg_box.exec() != QMessageBox.Yes:
            return

        self.show_message("🚀 시스템 업데이트 진행 중...\n절대 전원을 끄지 마세요! (약 15초 소요)")
        QApplication.processEvents()

        # 여기서 예외가 새어나가면 전체화면 오버레이가 걸린 채 앱이 멈춘다.
        # 터치 전용 키오스크라 조작자가 빠져나올 방법이 없으므로 반드시 잡는다.
        try:
            self.run_ota_update()
        except Exception as e:
            log.exception("OTA 업데이트 실패")
            self.show_message(f"업데이트 실패\n{e}\n\n기존 버전으로 계속 사용합니다.", 6000)
            return

        os.execv(sys.executable, [sys.executable] + sys.argv)

    def run_ota_update(self):
        # 되돌아갈 지점을 먼저 확보한다. 깨진 코드를 받으면 현장에서 SSH 없이는
        # 복구가 불가능하므로, 자동 검증에 실패하면 이 커밋으로 되돌린다.
        previous = git("rev-parse", "HEAD", check=True, timeout=10).stdout.strip()

        git("reset", "--hard", check=True, timeout=60)
        git("pull", check=True, timeout=300)
        log.info("[OTA] 소스 코드 내려받음 (이전 커밋 %s)", previous[:8])

        check = subprocess.run([sys.executable, "test_sorter.py"],
                               cwd=BASE_DIR, capture_output=True, text=True, timeout=120)
        if check.returncode != 0:
            log.error("[OTA] 새 코드 자체 점검 실패, 되돌립니다:\n%s",
                      (check.stderr or check.stdout)[-2000:])
            git("reset", "--hard", previous, check=True, timeout=60)
            raise RuntimeError("새 버전 자체 점검 실패. 이전 버전으로 되돌렸습니다.")

        log.info("[OTA] 소스 코드 업데이트 완료")

        arduino_port = self.serial_thread.serial_port.port if self.serial_thread.is_connected() else None
        self.serial_thread.stop()
        time.sleep(1.5)

        if not (arduino_port and os.path.isdir(FIRMWARE_DIR)):
            return

        # 펌웨어 업로드가 실패해도 파이썬 쪽 업데이트는 이미 끝났으므로
        # 재시작은 진행한다. 실패는 로그와 저울점검 화면으로 드러난다.
        log.info("[OTA] 아두이노 펌웨어 자동 업데이트 시작 (포트: %s)", arduino_port)
        try:
            expected_version = firmware_expected_version()
            if not expected_version:
                log.warning("[OTA] 펌웨어 버전을 특정할 수 없어 업로드를 건너뜁니다.")
                return

            with open(os.path.join(FIRMWARE_DIR, "firmware_version.h"), 'w', encoding='utf-8') as f:
                f.write(f'#define FIRMWARE_VERSION "{expected_version}"\n')

            fqbn = "arduino:avr:mega:cpu=atmega2560"
            subprocess.run(["arduino-cli", "compile", "--fqbn", fqbn, FIRMWARE_DIR],
                           check=True, timeout=600)
            subprocess.run(["arduino-cli", "upload", "-p", arduino_port, "--fqbn", fqbn, FIRMWARE_DIR],
                           check=True, timeout=300)

            if self.check_firmware_version(arduino_port, expected_version):
                log.info("[OTA] 펌웨어 업데이트 성공 (버전: %s)", expected_version)
            else:
                log.warning("[OTA] 업로드는 됐으나 버전(%s) 확인 실패", expected_version)
        except Exception as e:
            log.error("[OTA] 펌웨어 업로드 실패: %s", e)

    def check_firmware_version(self, port, expected_version, timeout_sec=12):
        # 포트를 열면 메가가 리셋된다. 부팅 지연(1초) + performTare(최대 2초) 이후에야
        # [VER] 줄이 나오므로 넉넉히 기다린다.
        try:
            with serial.Serial(port, 115200, timeout=1) as ser:
                start = time.time()
                buffer = ""
                while time.time() - start < timeout_sec:
                    data = ser.read(max(1, ser.in_waiting)).decode('utf-8', errors='ignore')
                    if data:
                        buffer += data
                        if "[VER]" in buffer and "\n" in buffer.split("[VER]", 1)[1]:
                            line = buffer.split("[VER]", 1)[1].splitlines()[0].strip()
                            return line == expected_version
            return False
        except Exception as e:
            log.error("[OTA] 펌웨어 버전 확인 중 오류: %s", e)
            return False

    @staticmethod
    def read_settings_file(path):
        with open(path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("최상위가 객체가 아님")
        return loaded

    @staticmethod
    def backup_settings():
        """정상 로드에 성공한 설정만 백업본으로 남긴다."""
        try:
            shutil.copyfile(SETTINGS_FILE, BACKUP_FILE)
        except Exception as e:
            log.warning("설정 백업 실패: %s", e)

    def default_settings(self):
        return {
            "last_state": {},
            "presets": [None] * 8,
            "cal_multipliers": [1.0] * LOADCELL_COUNT,
            "cal_ref_weight": DEFAULT_REF_WEIGHT,
        }

    def load_settings(self):
        data = self.default_settings()
        loaded = None
        from_primary = False

        if os.path.exists(SETTINGS_FILE):
            try:
                loaded = self.read_settings_file(SETTINGS_FILE)
                from_primary = True
            except Exception as e:
                # 전원 강제 차단 등으로 파일이 깨진 경우. 원본을 남겨 사후 분석 가능하게 한다.
                log.error("설정 불러오기 실패: %s", e)
                try:
                    os.replace(SETTINGS_FILE, SETTINGS_FILE + ".corrupt")
                    log.error("깨진 설정을 settings.json.corrupt 로 옮김")
                except Exception:
                    pass

        if loaded is None and os.path.exists(BACKUP_FILE):
            # 프리셋 8개와 저울 12개 보정값은 재입력이 고통스럽다. 백업에서 되살린다.
            try:
                loaded = self.read_settings_file(BACKUP_FILE)
                log.warning("백업(settings.backup.json)에서 설정을 복구했습니다.")
            except Exception as e:
                log.error("백업 복구도 실패: %s", e)

        if loaded is None:
            log.warning("기본 설정으로 시작합니다.")
            return self.default_settings()

        data.update(loaded)
        # 백업에서 되살린 직후에는 원본이 없다. 이때 백업을 다시 뜨려 하면
        # 실패 경고만 남으므로, 원본을 정상적으로 읽었을 때만 갱신한다.
        if from_primary:
            self.backup_settings()

        presets = data.get("presets") or []
        if not isinstance(presets, list):
            presets = []
        presets = presets[:8] + [None] * max(0, 8 - len(presets))
        data["presets"] = presets

        mults = data.get("cal_multipliers")
        if not isinstance(mults, list) or len(mults) != LOADCELL_COUNT:
            data["cal_multipliers"] = [1.0] * LOADCELL_COUNT
        if not isinstance(data.get("cal_ref_weight"), int):
            data["cal_ref_weight"] = DEFAULT_REF_WEIGHT
        if not isinstance(data.get("last_state"), dict):
            data["last_state"] = {}
        return data

    def save_settings(self):
        self.settings_data["last_state"] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb,
            "tolerance": self.tolerance,
            "is_dark_mode": self.is_dark_mode,
            "current_preset_index": self.current_preset_index,
            "is_topup_mode": self.is_topup_mode
        }
        self.settings_data["cal_multipliers"] = self.cal_multipliers
        self.settings_data["cal_ref_weight"] = self.cal_ref_weight

        # 키오스크는 전원 스위치로 꺼진다. 쓰는 도중 전원이 끊겨도 기존 파일이
        # 남도록 임시 파일에 쓰고 원자적으로 교체한다.
        tmp = SETTINGS_FILE + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.settings_data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, SETTINGS_FILE)
        except Exception as e:
            log.error("설정 저장 실패: %s", e)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def closeEvent(self, event):
        self.save_settings()
        self.serial_thread.stop()
        super().closeEvent(event)

    def restart_program(self):
        self.save_settings()
        self.serial_thread.stop()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _power_command(self, args, label):
        """재부팅/전원끄기. sudo 권한이 없으면 조용히 실패하므로 화면에 알린다."""
        self.save_settings()
        try:
            subprocess.run(args, check=True, timeout=15,
                           capture_output=True, text=True)
        except Exception as e:
            log.error("%s 실패: %s", label, e)
            self.show_message(
                f"{label} 실패\nsudo 권한이 없습니다.\nsetup_kiosk.sh 를 다시 실행하세요.", 5000)
            return
        self.serial_thread.stop()

    # 🌟 추가된 기계(OS) 전체 재부팅 기능
    def reboot_system(self):
        self._power_command(["sudo", "-n", "reboot"], "재부팅")

    def shutdown_system(self):
        self._power_command(["sudo", "-n", "shutdown", "now"], "전원 끄기")

    def update_sim_mode_display(self, is_sim, was_connected=False):
        self.disconnected = bool(is_sim and was_connected)
        # 재연결 시 아두이노는 리셋되어 LED가 모두 꺼진 상태다.
        # 중복 송신 억제 캐시를 비워 다음 계산 결과가 반드시 전달되게 한다.
        self._last_led = None

        if is_sim:
            # 연결이 끊기면 진행 중이던 준비 절차는 의미가 없다.
            if self.startup_active:
                self.finish_startup("연결 끊김")
        else:
            # 파이가 포트를 열면 메가가 리셋된다. 부팅(1초)과 자체 영점(~2초)이
            # 끝나기를 기다렸다가 준비 절차를 시작한다.
            QTimer.singleShot(4000, lambda: self.begin_startup("아두이노 연결"))
        # 라벨이 길면 옆의 무게 값과 겹친다. 짧게 유지할 것.
        base = "박스무게" if self.is_topup_mode else "합계"

        if self.disconnected:
            # 케이블이 빠진 상태. 시뮬레이션과 구분해서 강하게 알린다.
            self.lbl_sum_title.setText("저울 연결끊김")
            self.set_cached_style(self.lbl_sum_title, "color: #F87171; font-weight: bold;")
        elif is_sim:
            self.lbl_sum_title.setText(f"{base}(시뮬)")
            self.set_cached_style(self.lbl_sum_title, "color: #F87171;")
        else:
            self.lbl_sum_title.setText(base)
            self.set_cached_style(self.lbl_sum_title, "")

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
        self.setting_tol.btn_minus.stepTriggered.connect(lambda mult: self.change_setting('tol', -5 * mult))
        self.setting_tol.btn_plus.stepTriggered.connect(lambda mult: self.change_setting('tol', 5 * mult))

        self.setting_product.btn_minus.stepTriggered.connect(lambda mult: self.cycle_preset(-1) if mult == 1 else None)
        self.setting_product.btn_plus.stepTriggered.connect(lambda mult: self.cycle_preset(1) if mult == 1 else None)
        
        original_toggle_theme = self.toggle_theme
        def new_toggle_theme():
            original_toggle_theme()
            self.set_cached_style(self.combo_card, self.get_combo_card_style(highlight=(self.combo_val.text() != "조합실패")))
            self.update_topup_ui()
            self.on_data_received(self.raw_weights)
            
        self.btn_theme_toggle.clicked.disconnect() 
        self.btn_theme_toggle.clicked.connect(new_toggle_theme)

        self.combo_card.clicked.connect(self.force_unlock)
        for i in range(LOADCELL_COUNT):
            self.tray_cards[i].clicked.connect(lambda idx=i: self.on_tray_clicked(idx))

    def in_simulation(self):
        """개발용 시뮬레이션 모드인지. 장치가 빠진 상태는 시뮬이 아니다."""
        return not self.serial_thread.is_connected() and not self.serial_thread.had_connection

    def force_unlock(self):
        """조합무게 카드 터치 = 이 조합 거절, 다른 조합 요청.

        저울 무게가 그대로면 탐색은 결정적이라 같은 답이 다시 나온다.
        방금 보여준 조합을 거절 목록에 넣어야 실제로 차선이 나온다.
        """
        rejected = frozenset(self.original_locked_indices)

        self.locked_combo = None
        self.locked_sum = 0
        self.original_locked_indices = []

        if self.in_simulation():
            # 시뮬레이션에서는 저울을 새로 채워 다양한 상황을 만들어 본다.
            self.rejected_combos.clear()
            for i in range(LOADCELL_COUNT):
                self.serial_thread.sim_weights[i] = random.randint(500, 1000)
            self.serial_thread.data_received.emit(list(self.serial_thread.sim_weights))
            self.show_message("모든 저울의 무게가 무작위로 변경되었습니다.", 1000)
            return

        if rejected:
            self.rejected_combos.add(rejected)
            self.show_message("다른 조합을 찾습니다.", 900)
        else:
            self.show_message("조합 연산 잠금이 해제되었습니다.", 900)

        self.on_data_received(self.raw_weights)

    def on_tray_clicked(self, idx):
        if self.in_simulation():
            if self.serial_thread.sim_weights[idx] > 0:
                self.serial_thread.sim_weights[idx] = 0
            else:
                self.serial_thread.sim_weights[idx] = random.randint(500, 1000)
            self.serial_thread.data_received.emit(list(self.serial_thread.sim_weights))

    def show_calibration_dialog(self):
        self.cal_dialog = CalibrationDialog(self, is_dark_mode=self.is_dark_mode, ref_weight=self.cal_ref_weight)
        self.cal_target_idx = 0
        self.cal_waiting_tare = False

        self.cal_dialog.btn_minus.stepTriggered.connect(lambda mult: self.modify_ref_weight(-10 if mult == 1 else -100))
        self.cal_dialog.btn_plus.stepTriggered.connect(lambda mult: self.modify_ref_weight(10 if mult == 1 else 100))

        self.cal_dialog.btn_apply.clicked.connect(self.apply_current_calibration)
        self.cal_dialog.btn_skip.clicked.connect(self.advance_cal_target)
        self.cal_dialog.btn_reset.clicked.connect(self.reset_current_calibration)
        self.cal_dialog.btn_close.clicked.connect(self.cal_dialog.accept)

        # 영점이 안 잡힌 상태로 보정하면 접시 무게가 배율에 흡수되어 값이 틀어진다.
        # 조작자가 순서를 지키도록 기대하는 대신, 들어올 때 항상 먼저 잡는다.
        self.begin_calibration_tare()

        self.cal_dialog.exec_()
        self.cal_dialog = None
        self.cal_waiting_tare = False
        self.save_settings()

    def begin_calibration_tare(self):
        if not self.serial_thread.is_connected():
            # 아두이노가 없으면 영점을 잡을 수 없다. 화면 확인 용도로만 열어 준다.
            self.cal_dialog.set_ready()
            self.cal_dialog.lbl_guide.setText("아두이노 미연결 - 보정을 저장해도 실제 측정에 쓰이지 않습니다.")
            self.update_cal_dialog_ui()
            return

        self.cal_waiting_tare = True
        self.cal_dialog.set_busy("저울 영점을 잡는 중입니다.\n접시를 비우고 손을 떼세요.")
        if not self.serial_thread.send_tare():
            self.on_calibration_tare_done(failed=True)
            return
        # 응답이 안 와도 화면이 잠기지 않도록 시한을 둔다.
        QTimer.singleShot(12000, lambda: self.on_calibration_tare_done(timeout=True))

    def on_calibration_tare_done(self, failed=False, timeout=False):
        if not (self.cal_waiting_tare and self.cal_dialog):
            return
        self.cal_waiting_tare = False
        self.cal_dialog.set_ready()
        if failed or timeout:
            log.warning("보정 전 영점 실패 (timeout=%s)", timeout)
            self.cal_dialog.lbl_guide.setText(
                "영점을 잡지 못했습니다. 먼저 저울 연결을 확인하세요.")
        self.update_cal_dialog_ui()

    def modify_ref_weight(self, delta):
        self.cal_ref_weight = max(10, min(20000, self.cal_ref_weight + delta))
        if self.cal_dialog:
            self.cal_dialog.lbl_ref_weight.setText(f"무게추: {self.cal_ref_weight:,} g")

    def reset_current_calibration(self):
        """잘못 적용한 보정을 되돌린다. 배율을 1.0 으로."""
        idx = self.cal_target_idx
        if idx >= LOADCELL_COUNT:
            return
        self.cal_multipliers[idx] = 1.0
        log.info("저울 %d 보정 초기화 (배율 1.0)", idx + 1)
        self.cal_dialog.lbl_guide.setText(f"{idx + 1}번 저울 보정을 초기화했습니다. (배율 1.00)")
        self.save_settings()
        self.update_cal_dialog_ui()

    def averaged_raw(self, idx):
        """해당 채널의 최근 유효 원시값 평균. 로드셀 노이즈가 배율에 박히는 것을 막는다."""
        samples = [r[idx] for r in self.raw_history
                   if len(r) > idx and r[idx] > 0]
        if not samples:
            return self.raw_weights[idx] if self.raw_weights[idx] > 0 else 0
        return sum(samples) / len(samples)

    def apply_current_calibration(self):
        idx = self.cal_target_idx
        if idx >= LOADCELL_COUNT or self.cal_waiting_tare:
            return

        raw_w = self.averaged_raw(idx)
        if raw_w <= 0:
            self.cal_dialog.lbl_guide.setText(
                f"{idx + 1}번 저울에 무게가 없습니다. 파란색 저울에 분동을 올려주세요.")
            return

        current_disp = raw_w * self.cal_multipliers[idx]
        if current_disp <= 0:
            return

        new_multiplier = self.cal_multipliers[idx] * (self.cal_ref_weight / current_disp)

        # 정상적인 로드셀 개체차는 이 범위 안에 들어온다. 벗어났다는 것은
        # 분동을 안 올렸거나, 다른 저울에 올렸거나, 분동 무게를 잘못 입력한 것이다.
        if not (CAL_RATIO_MIN <= new_multiplier <= CAL_RATIO_MAX):
            log.warning("저울 %d 보정 거부: 배율 %.3f (측정 %.0fg, 분동 %dg)",
                        idx + 1, new_multiplier, current_disp, self.cal_ref_weight)
            self.cal_dialog.lbl_guide.setText(
                f"보정을 적용하지 않았습니다. 배율 {new_multiplier:.2f}배는 비정상입니다.\n"
                f"{idx + 1}번(파란색) 저울에 {self.cal_ref_weight:,}g 분동이 올려져 있는지 확인하세요. "
                f"(현재 측정 {current_disp:,.0f}g)")
            return

        self.cal_multipliers[idx] = new_multiplier
        log.info("저울 %d 보정 적용: 배율 %.4f (평균 원시값 %.1f, 분동 %dg)",
                 idx + 1, new_multiplier, raw_w, self.cal_ref_weight)
        self.save_settings()

        self.advance_cal_target()
        if self.cal_dialog and self.cal_dialog.isVisible():
            self.cal_dialog.lbl_guide.setText(
                f"{idx + 1}번 저울 보정 완료 (배율 {new_multiplier:.2f}). "
                f"다음 저울에 분동을 옮겨 올리세요.")

    def advance_cal_target(self):
        self.cal_target_idx += 1
        self.update_cal_dialog_ui()

    def update_cal_dialog_ui(self):
        if not self.cal_dialog or not self.cal_dialog.isVisible(): return
        
        while self.cal_target_idx < LOADCELL_COUNT and self.raw_weights[self.cal_target_idx] == -1:
            self.cal_target_idx += 1

        if self.cal_target_idx >= LOADCELL_COUNT:
            self.show_message("모든 저울 보정이 완료되었습니다.", 2000)
            self.cal_dialog.accept()
            return

        self.cal_dialog.lbl_progress.setText(f"{self.cal_target_idx + 1} / {LOADCELL_COUNT} 번째")

        for i in range(LOADCELL_COUNT):
            w = self.raw_weights[i]
            card = self.cal_dialog.cal_cards[i]
            lbl = self.cal_dialog.cal_labels[i]

            # 배율이 정확히 1.0 이면 아직 한 번도 보정하지 않은 저울이다.
            state = self.cal_dialog.cal_states[i]
            if abs(self.cal_multipliers[i] - 1.0) < 1e-9:
                state.setText("미보정")
            else:
                state.setText(f"배율 {self.cal_multipliers[i]:.2f}")

            if w == -1:
                lbl.setText("ERR")
                self.set_cached_style(lbl, "color: #EF4444;")
                card_style = "QFrame { background-color: #451A1A; border: 2px solid #7F1D1D; border-radius: 12px; }" if self.is_dark_mode else "QFrame { background-color: #FEE2E2; border: 2px solid #FCA5A5; border-radius: 12px; }"
                self.set_cached_style(card, card_style)
            else:
                disp_w = int(w * self.cal_multipliers[i])
                lbl.setText(f"{disp_w:,} g")
                self.set_cached_style(lbl, "color: white;" if self.is_dark_mode else "color: #1F2937;")
                
                if i == self.cal_target_idx:
                    card_style = "QFrame { background-color: #2563EB; border: 3px solid #60A5FA; border-radius: 12px; }"
                    self.set_cached_style(lbl, "color: white; font-weight: bold;")
                    # 파란 배경 위에서는 기본 회색 글자가 안 읽힌다.
                    self.set_cached_style(state, "color: #DBEAFE;")
                else:
                    self.set_cached_style(state, "")
                    card_style = "QFrame { background-color: #2D2D2D; border: 2px solid #404040; border-radius: 12px; }" if self.is_dark_mode else "QFrame { background-color: #F3F4F6; border: 2px solid #D1D5DB; border-radius: 12px; }"
                self.set_cached_style(card, card_style)

    def show_scale_check_dialog(self):
        self.scale_check_dialog = ScaleCheckDialog(self, is_dark_mode=self.is_dark_mode)

        for i, btn in enumerate(self.scale_check_dialog.led_buttons):
            btn.toggled.connect(lambda checked, idx=i: self.toggle_scale_check_led(idx, checked))

        self.scale_check_dialog.btn_calibrate.clicked.connect(self.open_calibration_from_check)
        self.scale_check_dialog.btn_close.clicked.connect(self.scale_check_dialog.accept)

        self.expected_firmware_version = firmware_expected_version()

        self.update_scale_check_dialog_ui()
        if self.serial_thread.is_connected():
            self.serial_thread.request_firmware_version()
        else:
            self.scale_check_dialog.lbl_version.setText("펌웨어 버전: 아두이노 미연결")

        self.scale_check_dialog.exec_()

        # 다이얼로그를 닫으면 LED 제어권을 조합 연산에 돌려준다.
        self.scale_check_dialog = None
        self._last_led = None
        self.serial_thread.send_signal([])

    def open_calibration_from_check(self):
        # 점검 창을 먼저 닫는다. singleShot(0) 으로 exec_ 가 풀린 뒤에 보정 창을 연다.
        if self.scale_check_dialog:
            self.scale_check_dialog.accept()
        QTimer.singleShot(0, self.show_calibration_dialog)

    def toggle_scale_check_led(self, idx, checked):
        if not self.scale_check_dialog:
            return
        if checked:
            for j, btn in enumerate(self.scale_check_dialog.led_buttons):
                if j != idx and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            self.serial_thread.send_signal([idx + 1])
        else:
            self.serial_thread.send_signal([])

    def on_firmware_version_received(self, version):
        if not (self.scale_check_dialog and self.scale_check_dialog.isVisible()):
            # [VER] 은 아두이노 setup() 과 <VER> 요청에서만 나온다. 점검 창도 안 열었는데
            # 도착했다면 아두이노가 재부팅된 것 = 영점이 새로 잡혔다(접시에 물건이
            # 있었을 수도 있다). 준비 절차를 다시 돌려 확인한다.
            if not self.startup_active:
                log.warning("아두이노 재시작 감지 (펌웨어 %s)", version)
                self.begin_startup("아두이노 재시작")
            return
        lbl = self.scale_check_dialog.lbl_version
        if self.expected_firmware_version and version == self.expected_firmware_version:
            lbl.setText(f"펌웨어 버전: {version} (최신과 일치)")
            self.set_cached_style(lbl, "color: #10B981; font-weight: bold;")
        elif self.expected_firmware_version:
            lbl.setText(f"펌웨어 버전: {version} (최신 {self.expected_firmware_version} 과 다름! 업데이트 필요)")
            self.set_cached_style(lbl, "color: #EF4444; font-weight: bold;")
        else:
            lbl.setText(f"펌웨어 버전: {version}")
            self.set_cached_style(lbl, "")

    def update_scale_check_dialog_ui(self):
        if not self.scale_check_dialog or not self.scale_check_dialog.isVisible():
            return

        ok_count = 0
        for i in range(LOADCELL_COUNT):
            w = self.raw_weights[i]
            card = self.scale_check_dialog.channel_cards[i]
            lbl = self.scale_check_dialog.channel_labels[i]

            if w == -1:
                lbl.setText("연결안됨 (ERR)")
                self.set_cached_style(lbl, "color: #EF4444; font-weight: bold;")
                card_style = "QFrame { background-color: #451A1A; border: 2px solid #7F1D1D; border-radius: 12px; }" if self.is_dark_mode else "QFrame { background-color: #FEE2E2; border: 2px solid #FCA5A5; border-radius: 12px; }"
            else:
                ok_count += 1
                lbl.setText(f"정상 ({w:,})")
                self.set_cached_style(lbl, "color: #10B981; font-weight: bold;")
                card_style = "QFrame { background-color: #064E3B; border: 2px solid #059669; border-radius: 12px; }" if self.is_dark_mode else "QFrame { background-color: #ECFDF5; border: 2px solid #10B981; border-radius: 12px; }"
            self.set_cached_style(card, card_style)

        self.scale_check_dialog.lbl_summary.setText(f"정상 {ok_count} / {LOADCELL_COUNT}")

    def toggle_topup_mode(self):
        self.is_topup_mode = not self.is_topup_mode
        self.locked_combo = None
        self.locked_sum = 0
        self.original_locked_indices = []
        if self.is_topup_mode:
            self.memo_min_comb = self.min_comb
            self.min_comb = 1 
        else:
            self.min_comb = self.memo_min_comb
            
        self.update_topup_ui()
        self.update_setting_ui()

        self.update_sim_mode_display(not self.serial_thread.is_connected(),
                                     self.serial_thread.had_connection)
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
        dialog.btn_scale_check.clicked.connect(self.show_scale_check_dialog)

        for i, btn in enumerate(dialog.preset_buttons):
            self.refresh_preset_button(btn, i)
            btn.shortClicked.connect(lambda idx=i, d=dialog: self.load_preset(idx, d))
            btn.longPressed.connect(lambda idx=i, b=btn: self.save_preset(idx, b))
        dialog.exec_()

    def preset_button_text(self, index):
        p = (self.settings_data.get("presets") or [None] * 8)[index]
        if not p:
            return f"슬롯 {SLOT_NAMES[index]}\n(비어있음)"
        tol = p.get('tolerance', DEFAULT_TOLERANCE)
        return (f"슬롯 {SLOT_NAMES[index]}\n"
                f"{p['target_weight']:,}g +{tol}\n"
                f"({p['min_comb']}~{p['max_comb']}개)")

    def refresh_preset_button(self, button_widget, index):
        button_widget.setText(self.preset_button_text(index))
        button_widget.setStyleSheet("")

    def clear_all_presets(self, dialog):
        reply = QMessageBox.warning(dialog, "초기화 경고", "전체 제품 슬롯을 비우시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.settings_data["presets"] = [None] * 8
            self.current_preset_index = None
            self.save_settings()
            self.update_setting_ui()

            for i, btn in enumerate(dialog.preset_buttons):
                self.refresh_preset_button(btn, i)

    def load_preset(self, index, dialog=None):
        presets = self.settings_data.get("presets", [None] * 8)
        if presets[index]:
            p = presets[index]
            self.target_weight = p['target_weight']
            self.min_comb = p['min_comb']
            self.max_comb = p['max_comb']
            # 구버전 설정 파일에는 tolerance 항목이 없다.
            self.tolerance = p.get('tolerance', DEFAULT_TOLERANCE)
            self.current_preset_index = index
            self.locked_combo = None
            self.locked_sum = 0
            self.original_locked_indices = []
            self.update_setting_ui()
            if dialog: dialog.accept()

    def save_preset(self, index, button_widget):
        presets = self.settings_data.get("presets", [None] * 8)
        presets[index] = {
            "target_weight": self.target_weight,
            "min_comb": self.min_comb,
            "max_comb": self.max_comb,
            "tolerance": self.tolerance
        }
        self.settings_data["presets"] = presets
        self.save_settings()
        self.current_preset_index = index
        self.update_setting_ui()

        button_widget.setText(f"슬롯 {SLOT_NAMES[index]}\n저장됨!")
        button_widget.setStyleSheet("background-color: #059669; color: white;")

        # 잠깐 확인시켜준 뒤 방금 저장된 내용을 그 자리에 바로 보여준다.
        # 타이머를 버튼에 붙여 두면 창이 먼저 닫혀도 함께 사라져 콜백이 안전하다.
        timer = QTimer(button_widget)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.refresh_preset_button(button_widget, index))
        timer.start(900)

    def send_tare_command(self):
        self.locked_combo = None
        self.locked_sum = 0
        self.original_locked_indices = []
        # 아두이노가 TARE_DONE 을 안 보내도(케이블 불량 등) 오버레이가 영구히
        # 남지 않도록 타임아웃을 건다. 터치 전용이라 갇히면 복구 수단이 없다.
        self.show_message("영점 조정 중입니다.\n저울에서 손을 떼세요.", 10000)
        if self.serial_thread.is_connected():
            self.serial_thread.send_tare()
        else:
            log.info("[시뮬-TARE] 영점 조절 명령 시뮬레이션")
            QTimer.singleShot(2000, lambda: self.on_system_message("TARE_DONE"))

    def on_system_message(self, msg):
        if msg != "TARE_DONE":
            return
        if self.startup_active:
            self.on_startup_tare_done()
        elif self.cal_waiting_tare:
            self.on_calibration_tare_done()
        else:
            self.show_message("영점 조정이 완료되었습니다.", 2000)

    def change_setting(self, kind, delta):
        self.locked_combo = None
        self.locked_sum = 0
        self.original_locked_indices = []
        if kind == 'target':
            self.target_weight = max(100, self.target_weight + delta)
        elif kind == 'tol':
            self.tolerance = max(0, min(TOLERANCE_MAX, self.tolerance + delta))
        elif kind == 'min':
            self.min_comb = max(1, min(LOADCELL_COUNT, self.min_comb + delta))
            if self.min_comb > self.max_comb: self.max_comb = self.min_comb
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb
        elif kind == 'max':
            self.max_comb = max(1, min(LOADCELL_COUNT, self.max_comb + delta))
            if self.max_comb < self.min_comb: self.min_comb = self.max_comb
            if self.is_topup_mode:
                self.memo_min_comb = self.min_comb

        self.current_preset_index = None
        self.update_setting_ui()

    def update_setting_ui(self):
        # 한 줄에 다 넣으면 60px 폭 버튼 사이에서 잘린다. 슬롯명 + 무게 + 개수만.
        preset_text = f"{self.target_weight:,}g ({self.min_comb}~{self.max_comb}개)"
        if self.current_preset_index is not None:
            display_text = f"슬롯 {SLOT_NAMES[self.current_preset_index]} : {preset_text}"
        else:
            display_text = f"수동설정 : {preset_text}"

        self.setting_product.lbl_center.setText(display_text)
        self.setting_target.lbl_center.setText(f"목표무게 : {self.target_weight:,} g")
        self.setting_tol.lbl_center.setText(f"허용오차 : +{self.tolerance} g")
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
        self.raw_history.append(list(raw_weights))

        calibrated_weights = []
        for i, w in enumerate(raw_weights):
            if w > 0:
                calibrated_weights.append(int(w * self.cal_multipliers[i]))
            else:
                calibrated_weights.append(w)
                
        self.weights = calibrated_weights

        # 저울 구성(어디에 뭐가 올라가 있는지)이 바뀌면 거절 이력은 의미가 없다.
        # 무게 자체는 노이즈로 계속 흔들리므로 '올려져 있는지'만 본다.
        occupancy = tuple(w > 0 for w in self.weights)
        if occupancy != self._occupancy:
            self._occupancy = occupancy
            self.rejected_combos.clear()

        if self.cal_dialog and self.cal_dialog.isVisible():
            self.update_cal_dialog_ui()

        if self.scale_check_dialog and self.scale_check_dialog.isVisible():
            self.update_scale_check_dialog_ui()

        total = 0
        topup_sum = 0
        for i, w in enumerate(self.weights):
            lbl = self.tray_weight_labels[i]
            if w > 0:
                lbl.setText(f"{w:,} g")
                self.set_cached_style(lbl, "color: white;" if self.is_dark_mode else "color: #1F2937;")
                total += w
                if self.is_topup_mode and i in [0, 1, 6, 7]: 
                    topup_sum += w
            elif w == -1: 
                lbl.setText("에러(ERR)")
                self.set_cached_style(lbl, "color: #EF4444; font-weight: bold;") 
            else: 
                lbl.setText(f"{w:,} g")
                self.set_cached_style(lbl, "color: #555555;" if self.is_dark_mode else "color: #9CA3AF;")
                
        if self.is_topup_mode:
            self.sum_val_lbl.setText(f"{topup_sum:,} g")
        else:
            self.sum_val_lbl.setText(f"{total:,} g")

        # 준비 절차 중에는 무게가 요동치고 LED도 안내용으로 쓰이는 중이다.
        # 조합 연산과 LED 송신을 멈춘다.
        if self.startup_active:
            return

        self.find_best_combination()

    def find_best_combination(self):
        target = self.target_weight
        min_c = self.min_comb
        max_c = self.max_comb
        
        topup_sum = 0
        if self.is_topup_mode:
            for i in [0, 1, 6, 7]:
                if self.weights[i] > 0:
                    topup_sum += self.weights[i]

        if self.locked_combo is not None:
            still_locked = []
            for item in self.locked_combo:
                idx = item[0] - 1
                if self.weights[idx] > 0:
                    still_locked.append((item[0], self.weights[idx]))
            
            if not still_locked:
                # 잠긴 저울이 전부 0 이면 박스를 담아 간 것. -1(ERR)은 통신 두절이므로
                # 실적으로 세지 않는다.
                if all(self.weights[i - 1] == 0 for i in self.original_locked_indices):
                    self.record_box()

                if self.in_simulation():
                    for idx_1based in self.original_locked_indices:
                        idx = idx_1based - 1
                        self.serial_thread.sim_weights[idx] = random.randint(500, 1000)
                    QTimer.singleShot(100, lambda: self.serial_thread.data_received.emit(list(self.serial_thread.sim_weights)))

                self.locked_combo = None
                self.locked_sum = 0
                self.original_locked_indices = []
            else:
                self.locked_combo = still_locked
                self.render_combo_result(self.locked_combo, self.locked_sum, topup_sum)
                return

        valid_items = []
        for i, w in enumerate(self.weights):
            if w > 0:
                if not (self.is_topup_mode and i in [0, 1, 6, 7]):
                    valid_items.append((i+1, w))

        current_target = target - topup_sum if self.is_topup_mode else target

        result = best_combination(valid_items, current_target, min_c, max_c,
                                  self.tolerance, self.rejected_combos)

        # 거절 이력 때문에 후보가 하나도 안 남으면 이력을 비우고 처음부터 순환한다.
        if result.combo is None and self.rejected_combos:
            self.rejected_combos.clear()
            result = best_combination(valid_items, current_target, min_c, max_c,
                                      self.tolerance)

        if result.combo is not None:
            self.locked_combo = result.combo
            self.locked_sum = result.total
            self.locked_target = current_target
            self.original_locked_indices = [item[0] for item in result.combo]

        self.render_combo_result(result.combo, result.total, topup_sum,
                                 near_total=result.near_total,
                                 target=current_target)

    def record_box(self):
        """박스 하나가 완성됐다. 생산 실적을 CSV 로 남긴다."""
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            SLOT_NAMES[self.current_preset_index] if self.current_preset_index is not None else "수동",
            self.locked_target,
            self.locked_sum,
            self.locked_sum - self.locked_target,
            len(self.original_locked_indices),
            " ".join(str(i) for i in sorted(self.original_locked_indices)),
        ]
        try:
            new_file = not os.path.exists(PRODUCTION_FILE)
            with open(PRODUCTION_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["시각", "슬롯", "목표무게", "실제무게", "초과", "저울수", "사용저울"])
                w.writerow(row)
        except Exception as e:
            log.error("생산 실적 기록 실패: %s", e)

    def emit_led(self, indices):
        """조합 LED 송신. 저울점검·시작 준비 중에는 그쪽 LED 제어를 덮어쓰지 않는다."""
        if self.startup_active:
            return
        if self.scale_check_dialog and self.scale_check_dialog.isVisible():
            return
        key = tuple(sorted(indices))
        if key == self._last_led:
            return   # 바뀐 게 없으면 보내지 않는다 (초당 10회 불필요한 write 제거)
        self._last_led = key
        self.serial_thread.send_signal(indices)

    def render_combo_result(self, best_combo, best_sum, topup_sum,
                            near_total=None, target=None):
        for i in range(LOADCELL_COUNT):
            is_topup_tray = self.is_topup_mode and i in [0, 1, 6, 7]
            is_combo_tray = best_combo is not None and (i+1) in [item[0] for item in best_combo]
            
            if is_topup_tray: 
                style = "QFrame#Card { background-color: #1E3A8A; border-radius: 16px; border: 2px solid #3B82F6; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #DBEAFE; border-radius: 16px; border: 2px solid #2563EB; margin: 0px; padding: 0px; }"
            elif is_combo_tray: 
                style = "QFrame#Card { background-color: #064E3B; border-radius: 16px; border: 2px solid #059669; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #ECFDF5; border-radius: 16px; border: 2px solid #10B981; margin: 0px; padding: 0px; }"
            else: 
                style = "QFrame#Card { background-color: #1E1E1E; border-radius: 16px; border: 2px solid #333333; margin: 0px; padding: 0px; }" if self.is_dark_mode else "QFrame#Card { background-color: #FFFFFF; border-radius: 16px; border: 2px solid #E5E7EB; margin: 0px; padding: 0px; }"
            
            self.set_cached_style(self.tray_cards[i], style)
        
        if best_combo is not None:
            final_sum = best_sum + (topup_sum if self.is_topup_mode else 0)
            self.combo_val.setText(f"{final_sum:,} g")
            if self.locked_combo is not None:
                self.lbl_combo_title.setText("조합잠금")
            else:
                self.lbl_combo_title.setText("조합무게")
            self.set_cached_style(self.combo_card, self.get_combo_card_style(highlight=True))
            self.emit_led([item[0] for item in best_combo])
        else:
            self.combo_val.setText("조합실패")
            # 얼마나 모자란지 알려주면 송이를 더 얹을지 설정을 고칠지 바로 판단된다.
            if near_total is not None and target is not None:
                self.lbl_combo_title.setText(f"{target - near_total:,}g 부족")
            else:
                self.lbl_combo_title.setText("조합무게")
            self.set_cached_style(self.combo_card, self.get_combo_card_style(highlight=False))
            self.emit_led([])

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