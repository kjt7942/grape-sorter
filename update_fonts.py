import os
import urllib.request
import sys

def download_font():
    url = "https://raw.githubusercontent.com/wmakerjun/Webfonts/master/NanumBarunGothic.ttf"
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    
    if not os.path.exists(font_path):
        print(f"Downloading NanumBarunGothic.ttf from {url}...")
        try:
            urllib.request.urlretrieve(url, font_path)
            print("Download complete.")
        except Exception as e:
            print(f"Failed to download font: {e}")
            sys.exit(1)
    else:
        print("NanumBarunGothic.ttf already exists.")

def update_ui_font():
    with open('main_ui.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update CSS font-family to exactly NanumBarunGothic
    content = content.replace(
        "font-family: 'Pretendard', 'Noto Sans KR', 'Segoe UI', '맑은 고딕', sans-serif;", 
        "font-family: 'NanumBarunGothic', '나눔바른고딕';"
    )
    content = content.replace(
        "font-family: 'Malgun Gothic';", 
        "font-family: 'NanumBarunGothic', '나눔바른고딕';"
    )

    # 2. Extract QFont definitions
    if 'UI_FONT_FAMILY = "NanumBarunGothic"' not in content:
        if 'UI_FONT_FAMILY = "Pretendard"' in content:
            content = content.replace('UI_FONT_FAMILY = "Pretendard"', 'UI_FONT_FAMILY = "NanumBarunGothic"\nimport os\nfrom PyQt5.QtGui import QFontDatabase')
        else:
            content = content.replace("class SmartSorterUI(QMainWindow):", 'UI_FONT_FAMILY = "NanumBarunGothic"\nimport os\nfrom PyQt5.QtGui import QFontDatabase\n\nclass SmartSorterUI(QMainWindow):')
            content = content.replace('"Malgun Gothic"', 'UI_FONT_FAMILY')

    # 3. Add High-DPI and Anti-aliasing configurations, and load the custom font dynamically
    old_app_setup = """    app = QApplication(sys.argv)
    
    # 폰트 렌더링 개선 (안티앨리어싱)
    default_font = app.font()
    default_font.setFamily(UI_FONT_FAMILY)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)"""
    
    new_app_setup = """    app = QApplication(sys.argv)
    
    # 동적 폰트 로드 (나눔바른고딕)
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NanumBarunGothic.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                UI_FONT_FAMILY = families[0]
                print(f"Loaded Custom Font: {UI_FONT_FAMILY}")
    
    # 폰트 렌더링 개선 (안티앨리어싱)
    default_font = app.font()
    default_font.setFamily(UI_FONT_FAMILY)
    default_font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(default_font)"""

    if new_app_setup not in content:
        if old_app_setup in content:
            content = content.replace(old_app_setup, new_app_setup)
        else:
            content = content.replace("    app = QApplication(sys.argv)", new_app_setup)

    with open('main_ui.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    download_font()
    update_ui_font()
    print("Font updated to NanumBarunGothic successfully.")
