import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect, QDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QFontDatabase
import os

# 전역 폰트 설정 (기본값: 나눔바른고딕)
UI_FONT_FAMILY = "NanumBarunGothic"

class HoldButton(QPushButton):
    """
    버튼을 길게 누르고 있을 때 연속적인 이벤트를 발생시키는 커스텀 버튼 클래스.
    설정값(무게, 개수 등)을 빠르게 증감시킬 때 사용됩니다.
    """
    stepTriggered = pyqtSignal(int) # 증감 수치(배율)를 전달하는 시그널

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timeout)

    def mousePressEvent(self, event):
        """마우스 클릭 시 즉시 1단계 변화를 주고 타이머를 시작합니다."""
        if event.button() == Qt.LeftButton:
            self.timer.start(400) # 처음 길게 누르기 판단 대기 시간 (0.4초)
            self.stepTriggered.emit(1) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """마우스를 떼면 타이머를 중지합니다."""
        if event.button() == Qt.LeftButton:
            self.timer.stop() 
        super().mouseReleaseEvent(event)

    def on_timeout(self):
        """길게 누르고 있는 동안 0.1초 간격으로 5배속 변화를 줍니다."""
        self.timer.setInterval(100) 
        self.stepTriggered.emit(5) 


class LongPressButton(QPushButton):
    """
    짧게 누르기와 길게 누르기(2초 이상)를 구분하여 처리하는 버튼 클래스.
    프리셋 슬롯의 불러오기(짧게)와 저장하기(길게)에 사용됩니다.
    """
    shortClicked = pyqtSignal() # 짧은 클릭 시 시그널
    longPressed = pyqtSignal()  # 2초 이상 롱프레스 시 시그널

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_long_press)
        self.is_long_pressed = False

    def mousePressEvent(self, event):
        """마우스 클릭 시 2초 타이머를 시작합니다."""
        if event.button() == Qt.LeftButton:
            self.is_long_pressed = False
            self.timer.start(2000) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """마우스를 뗄 때까지의 시간을 체크하여 각기 다른 시그널을 보냅니다."""
        if event.button() == Qt.LeftButton:
            self.timer.stop()
            if not self.is_long_pressed:
                self.shortClicked.emit()
        super().mouseReleaseEvent(event)

    def on_long_press(self):
        """타이머가 만료되면 롱프레스로 간주합니다."""
        self.is_long_pressed = True
        self.longPressed.emit()


class PresetDialog(QDialog):
    """
    제품 프리셋(A~H 슬롯)을 관리하는 팝업 다이얼로그.
    기존 설정을 불러오거나 현재 설정을 저장하는 인터페이스를 제공합니다.
    """
    def __init__(self, parent=None, is_dark_mode=True):
        super().__init__(parent)
        self.setWindowTitle("제품 등록 (프리셋)")
        self.setFixedSize(800, 480) 
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint) # 프레임 없는 전체화면 다이얼로그
        
        self.is_dark_mode = is_dark_mode
        self.preset_buttons = []
        self.initUI()
        
    def initUI(self):
        """프리셋 다이얼로그의 레이아웃과 UI 요소들을 초기화합니다."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        
        # 상단 타이틀 및 비우기 버튼
        title_layout = QHBoxLayout()
        title_layout.addStretch(1)
        
        title = QLabel("제품 등록 및 불러오기")
        title.setFont(QFont(UI_FONT_FAMILY, 22, QFont.Bold))
        title_layout.addWidget(title)
        title_layout.addStretch(1)
        
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
        
        # A~H 프리셋 버튼 그리드 (2행 4열)
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
        
        # 닫기 버튼
        btn_close = QPushButton("닫기")
        btn_close.setFont(QFont(UI_FONT_FAMILY, 16, QFont.Bold))
        btn_close.setFixedHeight(60)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
        
        self.apply_theme()

    def apply_theme(self):
        """다이얼로그 전용 테마(밝게/어둡게)를 스타일시트로 적용합니다."""
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
            """)


class ClickableFrame(QFrame):
    """
    더블 클릭 이벤트와 워터마크(텍스트) 그리기 기능을 갖춘 프레임 클래스.
    개별 로드셀 트레이 정보를 담는 카드로 사용됩니다.
    """
    doubleClicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watermark_text = ""

    def mouseDoubleClickEvent(self, event):
        """프레임 더블 클릭 시 시그널을 발생시킵니다."""
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
        
    def paintEvent(self, event):
        """프레임 배경을 그린 후, 설정된 워터마크 안내 문구(반투명)를 가운데 그립니다."""
        super().paintEvent(event) 
        
        if self.watermark_text:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.TextAntialiasing)
            
            font = QFont(UI_FONT_FAMILY, 10, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(128, 128, 128, 70)) # 아주 흐릿한 회색
            
            painter.drawText(self.rect(), Qt.AlignCenter, self.watermark_text)
            painter.end()


class SmartSorterUI(QMainWindow):
    """
    프로그램의 메인 UI 레이아웃과 디자인 테마를 정의하는 핵심 클래스.
    """
    # 라이트 모드 디자인 상수
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
            margin: 0px; padding: 0px; /* 미세 크기 흔들림 방지 */
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
            padding: 0px; /* 중앙 정렬 개선 */
        }
        
        QPushButton#ThemeBtn {
            background-color: #FEE2E2;
            color: #991B1B;
            border: 2px solid #FCA5A5;
            font-size: 16px;
        }
    """

    # 다크 모드 디자인 상수
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
        self.setFixedSize(800, 480) # 고정 해상도 (터치패널 최적화)
        self.is_dark_mode = True 
        self.combo_shadow = QGraphicsDropShadowEffect(self) # 조합무게 카드 효과 관리용(현재는 비활성화됨)
        self.initUI()
        self.apply_theme()
        
    def initUI(self):
        """메인 화면의 전체 레이아웃 구성을 담당합니다."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget) # 전체 1:1 또는 특정 비율 분할
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. 왼쪽 패널: 12개의 로드셀 트레이 격자 정보
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        weights = [0] * 12 # 초기 더미 데이터
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

        # 왼쪽 하단 합계 요약
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

        # 2. 오른쪽 패널: 설정(목표무게 등) 및 결과(조합무게), 버튼들
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10) 

        # 설정 행들 (제품명, 목표무게, 개수 범위)
        self.setting_product = self.create_setting_row("제품명", "포도 2KG")
        self.setting_target = self.create_setting_row("목표무게", "2,050")
        self.setting_min = self.create_setting_row("최소", "3")
        self.setting_max = self.create_setting_row("최대", "4")

        right_layout.addWidget(self.setting_product) 
        right_layout.addWidget(self.setting_target)  
        right_layout.addWidget(self.setting_min)     
        right_layout.addWidget(self.setting_max)     
        
        right_layout.addStretch(2) # 상단 설정영역과 조합카드 사이 여백

        # 결과: 조합무게 카드
        self.combo_card = QFrame()
        self.combo_card.setObjectName("ComboCard")
        self.combo_card.setMinimumHeight(100) 

        self.combo_shadow.setBlurRadius(0) # 번짐 방지를 위해 현재는 0으로 고정
        self.combo_shadow.setOffset(0, 0)
        self.combo_shadow.setColor(QColor(0, 0, 0, 0)) 
        self.combo_card.setGraphicsEffect(self.combo_shadow)

        combo_layout = QHBoxLayout(self.combo_card)
        combo_layout.setContentsMargins(25, 20, 25, 20) 
        
        combo_title = QLabel("조합무게")
        combo_title.setObjectName("ComboTitle")
        combo_title.setFont(QFont(UI_FONT_FAMILY, 18, QFont.Bold)) 
        
        self.combo_val = QLabel("0 g")
        self.combo_val.setObjectName("ComboValue")
        self.combo_val.setFont(QFont(UI_FONT_FAMILY, 36, QFont.Bold)) 
        self.combo_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        combo_layout.addWidget(combo_title)
        combo_layout.addWidget(self.combo_val)
        
        right_layout.addWidget(self.combo_card)
        right_layout.addStretch(1) 

        # 하단 조작 버튼들 (영점, 보태기, 등록, 밤/낮)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_tare = QPushButton("영점")
        self.btn_tare.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_tare.setMinimumHeight(55)
        
        self.btn_topup = QPushButton("보태기") # 텍스트 고정, 배경색으로 상태 표시
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

        # 각 버튼이 동일한 가로 공간을 차지하게 함 (흔들림 방지)
        btn_layout.addWidget(self.btn_tare, 1)
        btn_layout.addWidget(self.btn_topup, 1)
        btn_layout.addWidget(self.btn_register, 1)
        btn_layout.addWidget(self.btn_theme_toggle, 1)
        
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(left_panel, 10) # 10 : 8 약 5:4 비율 분할
        main_layout.addWidget(right_panel, 8)

    def create_loadcell_card(self, num_str, weight):
        """12개의 트레이 중 하나의 카드 위젯을 생성합니다."""
        card = ClickableFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setMinimumHeight(50)
        
        # 관리자 기능을 위한 숨겨진 더블클릭 워터마크 안내
        if num_str == '①':
            card.watermark_text = "더블클릭:\n프로그램 종료"
        elif num_str == '⑦':
            card.watermark_text = "더블클릭:\n프로그램 재시작"
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
        """-, 값 정보, + 버튼이 포함된 설정 한 줄 위젯을 생성합니다."""
        row_widget = QFrame()
        row_widget.setObjectName("Card")
        row_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) 
        row_widget.setFixedHeight(60) 
        
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        btn_minus = HoldButton("-") # 길게 누르기 대응
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
        """다크/라이트 모드 플래그를 전환합니다."""
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        """현재 모드 플래그에 따라 미리 정의된 테마 스펙을 전체 위젯에 반영합니다."""
        if self.is_dark_mode:
            self.setStyleSheet(self.DARK_THEME)
            self.btn_theme_toggle.setText("낮")
        else:
            self.setStyleSheet(self.LIGHT_THEME)
            self.btn_theme_toggle.setText("밤")
