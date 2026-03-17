import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter

UI_FONT_FAMILY = "NanumBarunGothic"
import os
from PyQt5.QtGui import QFontDatabase

class ClickableFrame(QFrame):
    doubleClicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watermark_text = ""

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
            border: 1px solid #E5E7EB;
        }
        QFrame#ComboCard { 
            border: 3px solid #10B981; 
            background-color: #ECFDF5; 
            border-radius: 20px;
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
        QPushButton#ActionBtn:hover { background-color: #1D4ED8; }
        QPushButton#ActionBtn:pressed { background-color: #1E40AF; }
        
        QPushButton#ControlBtn {
            background-color: #F3F4F6;
            border: none;
            color: #374151;
            font-size: 28px;
            font-weight: bold;
            border-radius: 12px;
        }
        QPushButton#ControlBtn:hover { background-color: #E5E7EB; }
        
        QPushButton#ThemeBtn {
            background-color: #FEE2E2;
            color: #991B1B;
            border: 1px solid #FCA5A5;
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
            border: 1px solid #333333;
        }
        QFrame#ComboCard { 
            border: 2px solid #059669; 
            background-color: #064E3B; 
            border-radius: 20px;
        }
        
        QPushButton {
            background-color: #2D2D2D;
            border: 1px solid #404040;
            border-radius: 12px;
            color: #E0E0E0;
            font-family: 'NanumBarunGothic', '나눔바른고딕';
            font-weight: bold;
            padding: 10px;
        }
        QPushButton:hover { background-color: #383838; border-color: #4D4D4D; }
        QPushButton:pressed { background-color: #252525; }
        
        QPushButton#ActionBtn {
            background-color: #2563EB;
            color: white;
            border: none;
        }
        QPushButton#ActionBtn:hover { background-color: #3B82F6; }
        QPushButton#ActionBtn:pressed { background-color: #1D4ED8; }
        
        QPushButton#ControlBtn {
            background-color: #2D2D2D;
            border: 1px solid #404040;
            color: #E0E0E0;
            font-size: 28px;
            font-weight: bold;
            border-radius: 12px;
        }
        QPushButton#ControlBtn:hover { background-color: #383838; }
        
        QPushButton#ThemeBtn {
            background-color: #1E3A8A;
            color: #BFDBFE;
            border: 1px solid #3B82F6;
            font-size: 16px;
        }
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("스마트 포도 선별기")
        self.setFixedSize(800, 480)
        self.is_dark_mode = True 
        self.combo_shadow = QGraphicsDropShadowEffect(self)
        self.initUI()
        self.apply_theme()
        
    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.lbl_sim_mode = QLabel("⚠️ 시뮬레이션 모드 (아두이노 미연결)")
        self.lbl_sim_mode.setObjectName("SimMode")
        self.lbl_sim_mode.setFont(QFont(UI_FONT_FAMILY, 14))
        self.lbl_sim_mode.setAlignment(Qt.AlignCenter)
        self.lbl_sim_mode.hide() 

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        weights = [725, 670, 725, 820, 595, 620, 910, 680, 825, 710, 820, 745]
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
        self.sum_val_lbl = QLabel("8,845 g")
        self.sum_val_lbl.setObjectName("SumValue")
        self.sum_val_lbl.setFont(QFont(UI_FONT_FAMILY, 20, QFont.Bold))
        self.sum_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        sum_layout.addWidget(self.lbl_sum_title)
        sum_layout.addWidget(self.sum_val_lbl)
        left_layout.addWidget(sum_card)

        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10) 

        self.setting_product = self.create_setting_row("제품명", "포도 2KG")
        self.setting_target = self.create_setting_row("목표무게", "2,050")
        self.setting_min = self.create_setting_row("최소조합개수", "3")
        self.setting_max = self.create_setting_row("최대조합개수", "4")

        right_layout.addWidget(self.setting_product) 
        right_layout.addWidget(self.setting_target)  
        right_layout.addWidget(self.setting_min)     
        right_layout.addWidget(self.setting_max)     
        
        right_layout.addStretch(2) 
        right_layout.addSpacing(1) 

        self.combo_card = QFrame()
        self.combo_card.setObjectName("ComboCard")
        self.combo_card.setMinimumHeight(100) 

        self.combo_shadow.setBlurRadius(20)
        self.combo_shadow.setOffset(0, 4)
        self.combo_card.setGraphicsEffect(self.combo_shadow)

        combo_layout = QHBoxLayout(self.combo_card)
        combo_layout.setContentsMargins(25, 20, 25, 20) 
        
        combo_title = QLabel("조합무게")
        combo_title.setObjectName("ComboTitle")
        combo_title.setFont(QFont(UI_FONT_FAMILY, 18, QFont.Bold)) 
        
        self.combo_val = QLabel("2,050 g")
        self.combo_val.setObjectName("ComboValue")
        self.combo_val.setFont(QFont(UI_FONT_FAMILY, 36, QFont.Bold)) 
        self.combo_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        combo_layout.addWidget(combo_title)
        combo_layout.addWidget(self.combo_val)
        
        right_layout.addWidget(self.combo_card)
        right_layout.addStretch(1) 

        # ✨ 핵심 변경점: 세 버튼의 크기 비율을 동일하게 조정
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_tare = QPushButton("영점")
        self.btn_tare.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_tare.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.btn_tare.setMinimumHeight(55)
        
        self.btn_register = QPushButton("제품등록")
        self.btn_register.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold))
        self.btn_register.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.btn_register.setMinimumHeight(55)

        self.btn_theme_toggle = QPushButton("어둡게") 
        self.btn_theme_toggle.setObjectName("ThemeBtn")
        self.btn_theme_toggle.setFont(QFont(UI_FONT_FAMILY, 14, QFont.Bold)) # 폰트 크기 통일
        self.btn_theme_toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum) # 가로 크기 확장
        self.btn_theme_toggle.setMinimumHeight(55)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)

        btn_layout.addWidget(self.btn_tare)
        btn_layout.addWidget(self.btn_register)
        btn_layout.addWidget(self.btn_theme_toggle)
        
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(left_panel, 10)
        main_layout.addWidget(right_panel, 8)

    def create_loadcell_card(self, num_str, weight):
        card = ClickableFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setMinimumHeight(50)
        
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
        row_widget = QFrame()
        row_widget.setObjectName("Card")
        row_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) 
        row_widget.setFixedHeight(60) 
        
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        btn_minus = QPushButton("-")
        btn_minus.setObjectName("ControlBtn")
        btn_minus.setFixedSize(40, 40)
        
        lbl_center = QLabel(f"{label_text} : {value_text}")
        lbl_center.setFont(QFont(UI_FONT_FAMILY, 13, QFont.Bold))
        lbl_center.setAlignment(Qt.AlignCenter)
        
        btn_plus = QPushButton("+")
        btn_plus.setObjectName("ControlBtn")
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
            self.btn_theme_toggle.setText("밝게")
            self.combo_shadow.setColor(QColor(16, 185, 129, 80)) 
        else:
            self.setStyleSheet(self.LIGHT_THEME)
            self.btn_theme_toggle.setText("어둡게")
            self.combo_shadow.setColor(QColor(16, 185, 129, 60)) 

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                UI_FONT_FAMILY = families[0]
                print(f"Loaded Custom Font: {UI_FONT_FAMILY}")
    
    default_font = app.font()
    default_font.setFamily(UI_FONT_FAMILY)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    window = SmartSorterUI()
    window.show()
    sys.exit(app.exec_())