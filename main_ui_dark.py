import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

class SmartSorterUIDark(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("스마트 포도 선별기 (다크 모드)")
        self.resize(1280, 800)
        self.initUI()
        
    def initUI(self):
        # 중앙 위젯 및 기본 레이아웃 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(30)

        # 전체 애플리케이션에 대한 스타일 (QSS) - 다크 모드 특화
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QLabel {
                color: #E0E0E0;
            }
            QFrame#Card {
                background-color: #1E1E1E;
                border-radius: 16px;
                border: 1px solid #333333;
            }
            QPushButton {
                background-color: #2D2D2D;
                border: 1px solid #404040;
                border-radius: 12px;
                color: #E0E0E0;
                font-family: 'Malgun Gothic';
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #383838;
                border-color: #4D4D4D;
            }
            QPushButton:pressed {
                background-color: #252525;
            }
            QPushButton#ActionBtn {
                background-color: #2563EB;
                color: white;
                border: none;
            }
            QPushButton#ActionBtn:hover {
                background-color: #3B82F6;
            }
            QPushButton#ActionBtn:pressed {
                background-color: #1D4ED8;
            }
            QPushButton#ControlBtn {
                background-color: #2D2D2D;
                border: 1px solid #404040;
                color: #E0E0E0;
                font-size: 28px;
                font-weight: bold;
                border-radius: 12px;
            }
            QPushButton#ControlBtn:hover {
                background-color: #383838;
            }
        """)

        # -------------------------------------------------------------
        # 왼쪽 패널 (저울 데이터 모니터링 영역)
        # -------------------------------------------------------------
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)

        # 12개의 로드셀(저울) 무게 패널 (6행 2열 배치)
        grid_layout = QGridLayout()
        grid_layout.setSpacing(20)
        
        # 샘플 무게 데이터
        weights = [725, 670, 725, 820, 595, 620, 910, 680, 825, 710, 820, 745]
        label_numbers = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '⑪', '⑫']
        
        for i in range(12):
            card = self.create_loadcell_card(label_numbers[i], f"{weights[i]:,} g")
            row = i % 6
            col = i // 6
            grid_layout.addWidget(card, row, col)

        left_layout.addLayout(grid_layout)

        # 하단 합계 카드
        sum_card = QFrame()
        sum_card.setObjectName("Card")
        sum_layout = QHBoxLayout(sum_card)
        sum_layout.setContentsMargins(30, 25, 30, 25)
        
        sum_lbl = QLabel("합계")
        sum_lbl.setFont(QFont("Malgun Gothic", 26, QFont.Bold))
        self.sum_val_lbl = QLabel("8,845 g")
        self.sum_val_lbl.setFont(QFont("Malgun Gothic", 28, QFont.Bold))
        self.sum_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sum_val_lbl.setStyleSheet("color: #F87171;") # 포인트 컬러 (코랄 레드)
        
        sum_layout.addWidget(sum_lbl)
        sum_layout.addWidget(self.sum_val_lbl)
        left_layout.addWidget(sum_card)

        # -------------------------------------------------------------
        # 오른쪽 패널 (설정 컨트롤 및 결과, 동작 버튼)
        # -------------------------------------------------------------
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(25)

        # 1. 설정 항목들
        self.setting_product = self.create_setting_row("제품명", "포도 2KG")
        self.setting_target = self.create_setting_row("목표무게", "2,050")
        self.setting_min = self.create_setting_row("최소조합개수", "3")
        self.setting_max = self.create_setting_row("최대조합개수", "4")

        right_layout.addWidget(self.setting_product)
        right_layout.addWidget(self.setting_target)
        right_layout.addWidget(self.setting_min)
        right_layout.addWidget(self.setting_max)

        right_layout.addStretch()

        # 2. 조합결과 하이라이트 카드 (다크모드 에메랄드)
        combo_card = QFrame()
        combo_card.setObjectName("Card")
        combo_card.setStyleSheet("""
            QFrame#Card { 
                border: 2px solid #059669; 
                background-color: #064E3B; 
                border-radius: 20px;
            }
        """)
        
        # 다크모드용 은은한 네온 그린 그림자 효과
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(16, 185, 129, 80))
        shadow.setOffset(0, 4)
        combo_card.setGraphicsEffect(shadow)

        combo_layout = QHBoxLayout(combo_card)
        combo_layout.setContentsMargins(40, 50, 40, 50)
        
        combo_title = QLabel("조합무게")
        combo_title.setFont(QFont("Malgun Gothic", 28, QFont.Bold))
        combo_title.setStyleSheet("color: #6EE7B7;") # 밝은 에메랄드
        
        self.combo_val = QLabel("2,050 g")
        self.combo_val.setFont(QFont("Malgun Gothic", 48, QFont.Bold))
        self.combo_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.combo_val.setStyleSheet("color: #A7F3D0;") # 매우 밝은 에메랄드
        
        combo_layout.addWidget(combo_title)
        combo_layout.addWidget(self.combo_val)
        
        right_layout.addWidget(combo_card)
        right_layout.addStretch()

        # 3. 조작 버튼 세트
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        btn_pause = QPushButton("일시정지")
        btn_pause.setFont(QFont("Malgun Gothic", 22, QFont.Bold))
        btn_pause.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        btn_pause.setMinimumHeight(90)
        
        btn_run = QPushButton("동작")
        btn_run.setObjectName("ActionBtn") 
        btn_run.setFont(QFont("Malgun Gothic", 22, QFont.Bold))
        btn_run.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        btn_run.setMinimumHeight(90)
        
        btn_register = QPushButton("제품등록")
        btn_register.setFont(QFont("Malgun Gothic", 22, QFont.Bold))
        btn_register.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        btn_register.setMinimumHeight(90)

        btn_layout.addWidget(btn_pause)
        btn_layout.addWidget(btn_run)
        btn_layout.addWidget(btn_register)
        
        right_layout.addLayout(btn_layout)

        # 좌/우 패널 레이아웃 비율 설정 (좌측 13, 우측 10 비율)
        main_layout.addWidget(left_panel, 13)
        main_layout.addWidget(right_panel, 10)

    def create_loadcell_card(self, num_str, weight):
        """1~12번까지 저울의 무게를 표시하는 다크모드 카드 위젯"""
        card = QFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setMinimumHeight(80)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(25, 10, 25, 10)
        
        lbl_num = QLabel(num_str)
        lbl_num.setFont(QFont("Malgun Gothic", 20))
        lbl_num.setStyleSheet("color: #858585;") # 약간 어두운 회색
        
        lbl_weight = QLabel(weight)
        lbl_weight.setFont(QFont("Malgun Gothic", 24, QFont.Bold))
        lbl_weight.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_weight.setStyleSheet("color: #E0E0E0;")
        
        layout.addWidget(lbl_num)
        layout.addWidget(lbl_weight)
        
        return card

    def create_setting_row(self, label_text, value_text):
        """+ / - 버튼이 포함된 다크모드 설정 조작 위젯"""
        row_widget = QFrame()
        row_widget.setObjectName("Card")
        row_widget.setMinimumHeight(85)
        
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        btn_minus = QPushButton("-")
        btn_minus.setObjectName("ControlBtn")
        btn_minus.setFixedSize(65, 65)
        
        lbl_center = QLabel(f"{label_text} : {value_text}")
        lbl_center.setFont(QFont("Malgun Gothic", 20, QFont.Bold))
        lbl_center.setAlignment(Qt.AlignCenter)
        
        btn_plus = QPushButton("+")
        btn_plus.setObjectName("ControlBtn")
        btn_plus.setFixedSize(65, 65)
        
        layout.addWidget(btn_minus)
        layout.addWidget(lbl_center, 1) # 중앙 라벨이 빈 공간을 채우도록 stretch 적용
        layout.addWidget(btn_plus)
        
        return row_widget

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 고해상도 모니터에서도 선명하게 보이도록 스케일링 옵션 활성화
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    window = SmartSorterUIDark()
    window.show()
    sys.exit(app.exec_())
