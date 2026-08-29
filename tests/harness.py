"""테스트 공용 준비 코드.

각 테스트는 별도 프로세스에서 돈다. QApplication 과 main 모듈 전역 상태를
공유하면 서로 간섭하기 때문이다. run_all.py 가 프로세스를 나눠 실행한다.

모든 테스트는 화면 없이(offscreen) 돌기 때문에 라즈베리파이나 아두이노 없이
개발 PC에서 그대로 실행할 수 있다.
"""
import logging
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_screens")

# 실제 저울 배치와 같은 순서. 인덱스는 0부터, 저울 번호는 1부터.
ERR = -1
BOARD1 = [0, 1, 6, 7]      # 허브보드 1장에 물린 채널 = 저울 1,2,7,8


def boot():
    """offscreen Qt 앱을 띄우고 main 모듈을 임시 경로로 돌려놓은 채 돌려준다.

    반환: (app, main, main_ui)
    """
    sys.argv = ["main.py"]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if REPO not in sys.path:
        sys.path.insert(0, REPO)

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QFontDatabase

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(sys.argv)

    import main_ui
    font_path = os.path.join(REPO, "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            main_ui.UI_FONT_FAMILY = families[0]
    font = app.font()
    font.setFamily(main_ui.UI_FONT_FAMILY)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    import main

    # 테스트가 네트워크를 건드리지 않도록.
    main.OTAThread.run = lambda self: None

    # 설정/실적/백업을 임시 폴더로 돌려 저장소를 더럽히지 않는다.
    tmp = tempfile.mkdtemp(prefix="grape-test-")
    main.SETTINGS_FILE = os.path.join(tmp, "settings.json")
    main.BACKUP_FILE = os.path.join(tmp, "settings.backup.json")
    main.PRODUCTION_FILE = os.path.join(tmp, "production.csv")

    # 로그는 콘솔로만. 저장소의 sorter.log 에 테스트 기록이 섞이지 않게 한다.
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            handler.close()

    return app, main, main_ui


def new_app(main, connected=True):
    """MainApp 을 띄우고, 실기처럼 보이도록 가짜 시리얼 포트를 물린다.

    반환: (window, sent) - sent 는 아두이노로 나간 문자열이 쌓이는 리스트.
    """
    window = main.MainApp()
    window.show()
    window.serial_thread.stop()          # 실제 포트 탐색 스레드는 멈춘다

    sent = []

    class FakePort:
        is_open = True
        port = "COM-FAKE"

        def write(self, payload):
            sent.append(payload.decode().strip())
            return len(payload)

        def close(self):
            pass

    if connected:
        window.serial_thread.serial_port = FakePort()
        window.serial_thread.had_connection = True
    return window, sent


def teardown(window):
    window.serial_thread.serial_port = None
    window.serial_thread.stop()


def wait(ms):
    """이벤트 루프를 ms 만큼 돌린다. QTimer 로 진행되는 절차를 기다릴 때 쓴다."""
    from PyQt5.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def shot(widget, name):
    """위젯을 PNG 로 저장한다. 화면 확인용이며 실패 판정에는 쓰지 않는다."""
    from PyQt5.QtWidgets import QApplication
    QApplication.processEvents()
    os.makedirs(SCREEN_DIR, exist_ok=True)
    path = os.path.join(SCREEN_DIR, name)
    widget.grab().save(path)
    return path


def weights(**channels):
    """저울 번호(1~12)로 무게를 지정하고 나머지는 ERR 로 채운다.

    weights(**{'1': 500}) 는 못 쓰므로 ch1=500 형태를 받는다.
    """
    row = [ERR] * 12
    for key, value in channels.items():
        row[int(key[2:]) - 1] = value
    return row


def ok(name):
    print(f"  [OK] {name}")
