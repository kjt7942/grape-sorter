import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QFontDatabase
import os

UI_FONT_FAMILY = "NanumBarunGothic"

class HoldButton(QPushButton):
    stepTriggered = pyqtSignal(int)

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timeout)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.timer.start(400) 
            self.stepTriggered.emit(1) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.timer.stop() 
        super().mouseReleaseEvent(event)

    def on_timeout(self):
        self.timer.setInterval(100) 
        self.stepTriggered.emit(5) 


class LongPressButton(QPushButton):
    shortClicked = pyqtSignal()
    longPressed = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_long_press)
        self.is_long_pressed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_long_pressed = False
            self.timer.start(2000) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.timer.stop()
            if not self.is_long_pressed:
                self.shortClicked.emit()
        super().mouseReleaseEvent(event)

    def on_long_press(self):
        self.is_long_pressed = True
        self.longPressed.emit()


class PresetDialog(QDialog):
    def __init__(self, parent=None, is_dark_mode=True):
        super().__init__(parent)
        self.setWindowTitle("제품 등록 (프리셋)")
        self.setFixedSize(800, 480) 
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint) 
        
        self.is_dark_mode = is_dark_mode
        self.preset_buttons = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        
        title_layout = QHBoxLayout()
        title_layout.addStretch(1)
        
        title = QLabel("제품 등록 및 불러오기")
        title.setFont(QFont(UI_FONT_FAMILY, 22, QFont.Bold))
        title_layout.addWidget(title)
        
        title_layout.addStretch(1)
        
        self.btn_scale_check = QPushButton("저울점검")
        self.btn_scale_check.setObjectName("ScaleCheckBtn")
        self.btn_scale_check.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_scale_check.setFixedSize(110, 45)
        title_layout.addWidget(self.btn_scale_check)

        self.btn_clear = QPushButton("비우기")
        self.btn_clear.setObjectName("ClearBtn")
        self.btn_clear.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_clear.setFixedSize(100, 45)
        title_layout.addWidget(self.btn_clear)

        layout.addLayout(title_layout)
        
        desc = QLabel("버튼을 짧게 터치하면 불러오기, 2초간 길게 누르면 현재 설정이 저장됩니다.")
        desc.setFont(QFont(UI_FONT_FAMILY, 14))
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        grid_layout = QGridLayout()
        grid_layout.setSpacing(15) 
        slot_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for i, name in enumerate(slot_names):
            btn = LongPressButton(f"슬롯 {name}\n(비어있음)")
            btn.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            grid_layout.addWidget(btn, i // 4, i % 4)
            self.preset_buttons.append(btn)
            
        layout.addLayout(grid_layout)
        
        btn_close = QPushButton("닫기")
        btn_close.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
        btn_close.setFixedHeight(60)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #1E1E1E; border: 2px solid #333333; border-radius: 15px; }
                QLabel { color: #E0E0E0; }
                QPushButton { background-color: #2D2D2D; border: 2px solid #404040; border-radius: 10px; color: #E0E0E0; }
                QPushButton:hover { background-color: #383838; }
                QPushButton:pressed { background-color: #4D4D4D; }
                QPushButton#ClearBtn { background-color: #EF4444; color: white; border: none; }
                QPushButton#ClearBtn:hover { background-color: #DC2626; }
                QPushButton#ClearBtn:pressed { background-color: #B91C1C; }
                QPushButton#ScaleCheckBtn { background-color: #2563EB; color: white; border: none; }
                QPushButton#ScaleCheckBtn:hover { background-color: #1D4ED8; }
                QPushButton#ScaleCheckBtn:pressed { background-color: #1E40AF; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #FFFFFF; border: 2px solid #E5E7EB; border-radius: 15px; }
                QLabel { color: #1F2937; }
                QPushButton { background-color: #F3F4F6; border: 2px solid #D1D5DB; border-radius: 10px; color: #1F2937; }
                QPushButton:hover { background-color: #E5E7EB; }
                QPushButton:pressed { background-color: #D1D5DB; }
                QPushButton#ClearBtn { background-color: #EF4444; color: white; border: none; }
                QPushButton#ClearBtn:hover { background-color: #DC2626; }
                QPushButton#ClearBtn:pressed { background-color: #B91C1C; }
                QPushButton#ScaleCheckBtn { background-color: #2563EB; color: white; border: none; }
                QPushButton#ScaleCheckBtn:hover { background-color: #1D4ED8; }
                QPushButton#ScaleCheckBtn:pressed { background-color: #1E40AF; }
            """)


class CalibrationDialog(QDialog):
    def __init__(self, parent=None, is_dark_mode=True, ref_weight=430):
        super().__init__(parent)
        self.setWindowTitle("저울 보정")
        self.setFixedSize(800, 480)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.is_dark_mode = is_dark_mode
        self.ref_weight = ref_weight
        self.cal_cards = []
        self.cal_labels = []
        self.cal_states = []
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        top_layout = QHBoxLayout()
        title = QLabel("저울 정밀 보정")
        title.setFont(QFont(UI_FONT_FAMILY, 19, QFont.Bold))
        top_layout.addWidget(title)

        self.lbl_progress = QLabel("1 / 12 번째")
        self.lbl_progress.setObjectName("Progress")
        self.lbl_progress.setFont(QFont(UI_FONT_FAMILY, 15, QFont.Bold))
        top_layout.addWidget(self.lbl_progress)
        top_layout.addStretch(1)

        self.btn_minus = HoldButton("-")
        self.btn_minus.setFixedSize(56, 44)
        self.btn_minus.setFont(QFont(UI_FONT_FAMILY, 22, QFont.Bold))
        self.btn_minus.setStyleSheet("background-color: #4B5563; color: white; border-radius: 10px; padding: 0px;")

        self.lbl_ref_weight = QLabel(f"무게추: {self.ref_weight:,} g")
        self.lbl_ref_weight.setFont(QFont(UI_FONT_FAMILY, 18, QFont.Bold))
        self.lbl_ref_weight.setAlignment(Qt.AlignCenter)
        self.lbl_ref_weight.setMinimumWidth(190)

        self.btn_plus = HoldButton("+")
        self.btn_plus.setFixedSize(56, 44)
        self.btn_plus.setFont(QFont(UI_FONT_FAMILY, 22, QFont.Bold))
        self.btn_plus.setStyleSheet("background-color: #4B5563; color: white; border-radius: 10px; padding: 0px;")

        top_layout.addWidget(self.btn_minus)
        top_layout.addWidget(self.lbl_ref_weight)
        top_layout.addWidget(self.btn_plus)
        layout.addLayout(top_layout)

        # 처음 쓰는 사람도 순서를 알 수 있도록 화면에 절차를 적어 둔다.
        self.lbl_guide = QLabel()
        self.lbl_guide.setObjectName("Guide")
        self.lbl_guide.setFont(QFont(UI_FONT_FAMILY, 12))
        self.lbl_guide.setAlignment(Qt.AlignCenter)
        self.lbl_guide.setWordWrap(True)
        layout.addWidget(self.lbl_guide)

        grid = QGridLayout()
        grid.setSpacing(8)
        label_numbers = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '⑪', '⑫']

        for i in range(12):
            card = QFrame()
            card.setMinimumHeight(95)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 5, 5, 5)
            card_layout.setSpacing(2)

            lbl_num = QLabel(label_numbers[i])
            lbl_num.setFont(QFont(UI_FONT_FAMILY, 12))

            lbl_val = QLabel("0 g")
            lbl_val.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
            lbl_val.setAlignment(Qt.AlignCenter)

            # 아직 한 번도 보정하지 않은 저울을 눈에 띄게 해서 빠뜨리지 않도록 한다.
            lbl_state = QLabel("미보정")
            lbl_state.setObjectName("CalState")
            lbl_state.setFont(QFont(UI_FONT_FAMILY, 10))
            lbl_state.setAlignment(Qt.AlignCenter)

            card_layout.addWidget(lbl_num)
            card_layout.addWidget(lbl_val, 1)
            card_layout.addWidget(lbl_state)

            self.cal_cards.append(card)
            self.cal_labels.append(lbl_val)
            self.cal_states.append(lbl_state)

            # 실물 배치와 동일하게 1~6번은 아랫줄, 7~12번은 윗줄
            row = 1 - (i // 6)
            col = i % 6
            grid.addWidget(card, row, col)

        layout.addLayout(grid)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.btn_apply = QPushButton("보정 적용")
        self.btn_apply.setFont(QFont(UI_FONT_FAMILY, 17, QFont.Bold))
        self.btn_apply.setFixedHeight(56)
        self.btn_apply.setStyleSheet("background-color: #2563EB; color: white; border-radius: 12px; border: none;")

        self.btn_skip = QPushButton("건너뛰기\n(기존값 유지)")
        self.btn_skip.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
        self.btn_skip.setFixedHeight(56)
        self.btn_skip.setStyleSheet("background-color: #6B7280; color: white; border-radius: 12px; border: none; padding: 0px;")

        self.btn_reset = QPushButton("초기화\n(배율 1.0)")
        self.btn_reset.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
        self.btn_reset.setFixedHeight(56)
        self.btn_reset.setStyleSheet("background-color: #B45309; color: white; border-radius: 12px; border: none; padding: 0px;")

        self.btn_close = QPushButton("완료")
        self.btn_close.setFont(QFont(UI_FONT_FAMILY, 15, QFont.Bold))
        self.btn_close.setFixedHeight(56)
        self.btn_close.setStyleSheet("background-color: #EF4444; color: white; border-radius: 12px; border: none;")

        bottom_layout.addWidget(self.btn_apply, 3)
        bottom_layout.addWidget(self.btn_skip, 2)
        bottom_layout.addWidget(self.btn_reset, 2)
        bottom_layout.addWidget(self.btn_close, 2)

        layout.addLayout(bottom_layout)
        self.set_busy("저울 영점을 잡는 중입니다. 손을 떼고 기다리세요.")
        self.apply_theme()

    def set_busy(self, text):
        """자동 영점처럼 조작하면 안 되는 구간. 버튼을 잠그고 이유를 보여준다."""
        self.lbl_guide.setText(text)
        for b in (self.btn_apply, self.btn_skip, self.btn_reset,
                  self.btn_minus, self.btn_plus):
            b.setEnabled(False)

    def set_ready(self):
        for b in (self.btn_apply, self.btn_skip, self.btn_reset,
                  self.btn_minus, self.btn_plus):
            b.setEnabled(True)
        self.lbl_guide.setText(
            "① 분동 무게를 위에서 맞추세요    "
            "② 파란색 저울에 분동을 올리세요    "
            "③ 값이 멈추면 [보정 적용]")

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #121212; border: 2px solid #333333; }
                QLabel { color: #E0E0E0; }
                QLabel#Guide { color: #93C5FD; }
                QLabel#Progress { color: #FBBF24; }
                QLabel#CalState { color: #6B7280; }
                QPushButton:disabled { background-color: #374151; color: #6B7280; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #FFFFFF; border: 2px solid #E5E7EB; }
                QLabel { color: #1F2937; }
                QLabel#Guide { color: #1D4ED8; }
                QLabel#Progress { color: #B45309; }
                QLabel#CalState { color: #9CA3AF; }
                QPushButton:disabled { background-color: #E5E7EB; color: #9CA3AF; }
            """)


class ScaleCheckDialog(QDialog):
    def __init__(self, parent=None, is_dark_mode=True):
        super().__init__(parent)
        self.setWindowTitle("저울 점검")
        self.setFixedSize(800, 480)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.is_dark_mode = is_dark_mode
        self.channel_cards = []
        self.channel_labels = []
        self.led_buttons = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        title = QLabel("저울(로드셀) 점검")
        title.setFont(QFont(UI_FONT_FAMILY, 20, QFont.Bold))
        top_layout.addWidget(title)
        top_layout.addStretch(1)

        self.lbl_summary = QLabel("정상 0 / 12")
        self.lbl_summary.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
        top_layout.addWidget(self.lbl_summary)

        self.lbl_version = QLabel("펌웨어 버전: 확인 중...")
        self.lbl_version.setFont(QFont(UI_FONT_FAMILY, 14))
        top_layout.addWidget(self.lbl_version)

        layout.addLayout(top_layout)

        desc = QLabel("'LED 확인'을 누르면 해당 로드셀 LED가 켜집니다. "
                      "LED가 깜빡이는 채널은 격리 상태이며, 배선 수리 후 영점(TARE)을 누르면 복구됩니다.")
        desc.setFont(QFont(UI_FONT_FAMILY, 11))
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        grid = QGridLayout()
        grid.setSpacing(10)
        label_numbers = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '⑪', '⑫']

        for i in range(12):
            card = QFrame()
            card.setMinimumHeight(110)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 5, 5, 5)
            card_layout.setSpacing(4)

            lbl_num = QLabel(label_numbers[i])
            lbl_num.setFont(QFont(UI_FONT_FAMILY, 12))
            lbl_num.setAlignment(Qt.AlignCenter)

            lbl_val = QLabel("확인 중...")
            lbl_val.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
            lbl_val.setAlignment(Qt.AlignCenter)

            btn_led = QPushButton("LED 확인")
            btn_led.setCheckable(True)
            btn_led.setFont(QFont(UI_FONT_FAMILY, 11, QFont.Bold))
            btn_led.setFixedHeight(34)

            card_layout.addWidget(lbl_num)
            card_layout.addWidget(lbl_val, 1)
            card_layout.addWidget(btn_led)

            self.channel_cards.append(card)
            self.channel_labels.append(lbl_val)
            self.led_buttons.append(btn_led)

            # 1~6번(i=0~5)은 1행(아래), 7~12번(i=6~11)은 0행(위)으로 배치 (실물 배치와 동일)
            row = 1 - (i // 6)
            col = i % 6
            grid.addWidget(card, row, col)

        layout.addLayout(grid)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        # 영점은 메인화면 버튼으로도 되므로, 여기서는 보정으로 들어간다.
        # 보정 화면이 열릴 때 영점을 자동으로 먼저 잡는다.
        self.btn_calibrate = QPushButton("저울 보정")
        self.btn_calibrate.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
        self.btn_calibrate.setFixedHeight(55)
        self.btn_calibrate.setStyleSheet("background-color: #2563EB; color: white; border-radius: 12px; border: none;")

        self.btn_close = QPushButton("닫기")
        self.btn_close.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
        self.btn_close.setFixedHeight(55)
        self.btn_close.setStyleSheet("background-color: #6B7280; color: white; border-radius: 12px; border: none;")

        bottom_layout.addWidget(self.btn_calibrate, 1)
        bottom_layout.addWidget(self.btn_close, 1)
        layout.addLayout(bottom_layout)

        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #121212; border: 2px solid #333333; }
                QLabel { color: #E0E0E0; }
                /* padding 을 명시하지 않으면 부모 창의 padding: 10px 을 상속해 글자가 잘린다. */
                QPushButton { background-color: #2D2D2D; border: 2px solid #404040; border-radius: 8px; color: #E0E0E0; padding: 2px; }
                QPushButton:checked { background-color: #F59E0B; color: #1E1E1E; border: none; padding: 2px; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background-color: #FFFFFF; border: 2px solid #E5E7EB; }
                QLabel { color: #1F2937; }
                /* padding 을 명시하지 않으면 부모 창의 padding: 10px 을 상속해 글자가 잘린다. */
                QPushButton { background-color: #F3F4F6; border: 2px solid #D1D5DB; border-radius: 8px; color: #1F2937; padding: 2px; }
                QPushButton:checked { background-color: #F59E0B; color: #1E1E1E; border: none; padding: 2px; }
            """)


class ClickableFrame(QFrame):
    doubleClicked = pyqtSignal()
    clicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watermark_text = ""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
        
    def paintEvent(self, event):
        super().paintEvent(event) 
        
        if self.watermark_text:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.TextAntialiasing)
            
            font = QFont(UI_FONT_FAMILY, 10, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(128, 128, 128, 70)) 
            
            painter.drawText(self.rect(), Qt.AlignCenter, self.watermark_text)
            painter.end()


class SmartSorterUI(QMainWindow):
    LIGHT_THEME = """
        QMainWindow { background-color: #F4F6F8; }
        QLabel { color: #1F2937; }
        QLabel#GreyText { color: #9CA3AF; }
        QLabel#SumValue { color: #1F2937; }
        QLabel#ComboTitle { color: #065F46; }
        QLabel#ComboValue { color: #047857; }
        QLabel#SimMode { color: #EF4444; font-weight: bold; background-color: #FEE2E2; border-radius: 8px; padding: 5px; }
        
        QFrame#Card {
            background-color: #FFFFFF;
            border-radius: 16px;
            border: 2px solid #E5E7EB;
            margin: 0px; padding: 0px;
        }
        QFrame#ComboCard { 
            border: 3px solid #E5E7EB; 
            background-color: #FFFFFF; 
            border-radius: 20px;
            margin: 0px; padding: 0px;
        }
        
        QPushButton {
            background-color: #FFFFFF;
            border: 2px solid #E5E7EB;
            border-radius: 12px;
            color: #4B5563;
            font-family: 'NanumBarunGothic', '나눔바른고딕';
            font-weight: bold;
            padding: 10px;
        }
        QPushButton:hover { background-color: #F9FAFB; border-color: #D1D5DB; }
        QPushButton:pressed { background-color: #F3F4F6; }
        
        QPushButton#ActionBtn {
            background-color: #2563EB;
            color: white;
            border: none;
        }
        
        QPushButton#ControlBtn {
            background-color: #F3F4F6;
            border: 2px solid #E5E7EB; 
            color: #374151;
            border-radius: 12px;
            padding: 0px;
        }
        
        QPushButton#ThemeBtn {
            background-color: #FEE2E2;
            color: #991B1B;
            border: 2px solid #FCA5A5;
            font-size: 16px;
        }
    """

    DARK_THEME = """
        QMainWindow { background-color: #121212; }
        QLabel { color: #E0E0E0; }
        QLabel#GreyText { color: #858585; }
        QLabel#SumValue { color: #F87171; }
        QLabel#ComboTitle { color: #6EE7B7; }
        QLabel#ComboValue { color: #A7F3D0; }
        QLabel#SimMode { color: #F87171; font-weight: bold; background-color: #451A1A; border-radius: 8px; padding: 5px; }
        
        QFrame#Card {
            background-color: #1E1E1E;
            border-radius: 16px;
            border: 2px solid #333333;
            margin: 0px; padding: 0px;
        }
        QFrame#ComboCard { 
            border: 3px solid #333333; 
            background-color: #1E1E1E; 
            border-radius: 20px;
            margin: 0px; padding: 0px;
        }
        
        QPushButton {
            background-color: #2D2D2D;
            border: 2px solid #404040;
            border-radius: 12px;
            color: #E0E0E0;
            padding: 10px;
        }
        QPushButton#ControlBtn {
            background-color: #2D2D2D;
            border: 2px solid #404040;
            border-radius: 12px;
            padding: 0px;
        }
        QPushButton#ThemeBtn {
            background-color: #1E3A8A;
            color: #BFDBFE;
            border: 2px solid #3B82F6;
        }
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("스마트 포도 선별기")
        self.setFixedSize(800, 480) 
        self.is_dark_mode = True 
        self.combo_shadow = QGraphicsDropShadowEffect(self) 
        self.initUI()
        self.init_overlay() 
        self.apply_theme()
        
    def initUI(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QHBoxLayout(self.central_widget) 
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        weights = [0] * 12 
        label_numbers = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '⑪', '⑫']
        
        self.tray_weight_labels = []
        self.tray_cards = []
        for i in range(12):
            card = self.create_loadcell_card(label_numbers[i], f"{weights[i]:,} g")
            self.tray_weight_labels.append(card.lbl_weight)
            self.tray_cards.append(card)
            row = i % 6
            col = i // 6
            grid_layout.addWidget(card, row, col)

        left_layout.addLayout(grid_layout)

        sum_card = QFrame()
        sum_card.setObjectName("Card")
        sum_layout = QHBoxLayout(sum_card)
        sum_layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_sum_title = QLabel("합계")
        self.lbl_sum_title.setFont(QFont(UI_FONT_FAMILY, 18, QFont.Bold))
        self.sum_val_lbl = QLabel("0 g")
        self.sum_val_lbl.setObjectName("SumValue")
        self.sum_val_lbl.setFont(QFont(UI_FONT_FAMILY, 20, QFont.Bold))
        self.sum_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        sum_layout.addWidget(self.lbl_sum_title)
        sum_layout.addWidget(self.sum_val_lbl)
        left_layout.addWidget(sum_card)

        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # 설정 행이 5개라 800x480 안에 들어가도록 간격을 좁혔다.
        right_layout.setSpacing(6)

        self.setting_product = self.create_setting_row("제품명", "포도 2KG")
        self.setting_target = self.create_setting_row("목표무게", "2,050")
        self.setting_tol = self.create_setting_row("허용오차", "+50")
        self.setting_min = self.create_setting_row("최소", "3")
        self.setting_max = self.create_setting_row("최대", "4")

        right_layout.addWidget(self.setting_product)
        right_layout.addWidget(self.setting_target)
        right_layout.addWidget(self.setting_tol)
        right_layout.addWidget(self.setting_min)
        right_layout.addWidget(self.setting_max)

        right_layout.addStretch(2)

        self.combo_card = ClickableFrame()
        self.combo_card.setObjectName("ComboCard")
        self.combo_card.setMinimumHeight(100) 

        self.combo_shadow.setBlurRadius(0) 
        self.combo_shadow.setOffset(0, 0)
        self.combo_shadow.setColor(QColor(0, 0, 0, 0)) 
        self.combo_card.setGraphicsEffect(self.combo_shadow)

        combo_layout = QHBoxLayout(self.combo_card)
        combo_layout.setContentsMargins(25, 20, 25, 20) 
        
        self.lbl_combo_title = QLabel("조합무게")
        self.lbl_combo_title.setObjectName("ComboTitle")
        self.lbl_combo_title.setFont(QFont(UI_FONT_FAMILY, 18, QFont.Bold)) 
        
        self.combo_val = QLabel("0 g")
        self.combo_val.setObjectName("ComboValue")
        self.combo_val.setFont(QFont(UI_FONT_FAMILY, 36, QFont.Bold)) 
        self.combo_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        combo_layout.addWidget(self.lbl_combo_title)
        combo_layout.addWidget(self.combo_val)
        
        right_layout.addWidget(self.combo_card)
        right_layout.addStretch(1) 

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_tare = QPushButton("영점")
        self.btn_tare.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_tare.setMinimumHeight(55)
        
        self.btn_topup = QPushButton("보태기") 
        self.btn_topup.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_topup.setMinimumHeight(55)
        
        self.btn_register = QPushButton("제품등록")
        self.btn_register.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_register.setMinimumHeight(55)

        self.btn_theme_toggle = QPushButton("밤") 
        self.btn_theme_toggle.setObjectName("ThemeBtn")
        self.btn_theme_toggle.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold)) 
        self.btn_theme_toggle.setMinimumHeight(55)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)

        btn_layout.addWidget(self.btn_tare, 1)
        btn_layout.addWidget(self.btn_topup, 1)
        btn_layout.addWidget(self.btn_register, 1)
        btn_layout.addWidget(self.btn_theme_toggle, 1)
        
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(left_panel, 10) 
        main_layout.addWidget(right_panel, 8)

    def init_overlay(self):
        # 터치 전용 키오스크라 오버레이가 걸린 채 남으면 조작자가 빠져나올 수단이 없다.
        # show_message(text, timeout_ms) 로 항상 자동 해제 시각을 갖게 한다.
        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(True)
        self._msg_timer.timeout.connect(self.hide_message)

        self.overlay_label = QLabel(self.central_widget)
        self.overlay_label.setAlignment(Qt.AlignCenter)
        self.overlay_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.85);
            color: white;
            font-size: 28px;
            font-family: 'NanumBarunGothic', '나눔바른고딕';
            font-weight: bold;
            border-radius: 20px;
            padding: 30px;
        """)
        self.overlay_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'overlay_label'):
            label_width = 700
            label_height = 180
            self.overlay_label.setFixedSize(label_width, label_height)
            self.overlay_label.move(
                (self.width() - label_width) // 2,
                (self.height() - label_height) // 2
            )

    def show_message(self, text, timeout_ms=None):
        self.overlay_label.setText(text)
        self.overlay_label.show()
        self.overlay_label.raise_()
        self._msg_timer.stop()
        if timeout_ms:
            self._msg_timer.start(timeout_ms)

    def hide_message(self):
        self._msg_timer.stop()
        self.overlay_label.hide()

    def mousePressEvent(self, event):
        # 최후의 탈출구: 오버레이가 떠 있으면 화면을 눌러 닫을 수 있게 한다.
        if self.overlay_label.isVisible():
            self.hide_message()
        super().mousePressEvent(event)

    def create_loadcell_card(self, num_str, weight):
        card = ClickableFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setMinimumHeight(50)
        
        if num_str == '①':
            card.watermark_text = "더블클릭:\n프로그램 종료"
        elif num_str == '⑥':
            card.watermark_text = "더블클릭:\n저울 보정"
        elif num_str == '⑦':
            card.watermark_text = "더블클릭:\n프로그램 재시작"
        elif num_str == '⑪':
            card.watermark_text = "더블클릭:\n다시시작"
        elif num_str == '⑫':
            card.watermark_text = "더블클릭:\n시스템 종료"

        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        
        lbl_num = QLabel(num_str)
        lbl_num.setObjectName("GreyText")
        lbl_num.setFont(QFont(UI_FONT_FAMILY, 14))
        
        lbl_weight = QLabel(weight)
        lbl_weight.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        lbl_weight.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        layout.addWidget(lbl_num)
        layout.addWidget(lbl_weight)
        
        card.lbl_weight = lbl_weight
        return card

    def create_setting_row(self, label_text, value_text):
        row_widget = QFrame()
        row_widget.setObjectName("Card")
        row_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_widget.setFixedHeight(50)

        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(10)
        
        btn_minus = HoldButton("-") 
        btn_minus.setObjectName("ControlBtn")
        btn_minus.setFont(QFont(UI_FONT_FAMILY, 24, QFont.Bold))
        btn_minus.setFixedSize(40, 40)
        
        lbl_center = QLabel(f"{label_text} : {value_text}")
        lbl_center.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
        lbl_center.setAlignment(Qt.AlignCenter)
        
        btn_plus = HoldButton("+")
        btn_plus.setObjectName("ControlBtn")
        btn_plus.setFont(QFont(UI_FONT_FAMILY, 24, QFont.Bold))
        btn_plus.setFixedSize(40, 40)
        
        layout.addWidget(btn_minus)
        layout.addWidget(lbl_center, 1)
        layout.addWidget(btn_plus)
        
        row_widget.btn_minus = btn_minus
        row_widget.btn_plus = btn_plus
        row_widget.lbl_center = lbl_center
        return row_widget

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet(self.DARK_THEME)
            self.btn_theme_toggle.setText("낮")
        else:
            self.setStyleSheet(self.LIGHT_THEME)
            self.btn_theme_toggle.setText("밤")