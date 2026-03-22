#!/bin/bash

# --- 사용자 설정 ---
# 스크립트와 같은 폴더에 이미지 파일이 있다고 가정하고 절대경로를 자동으로 잡습니다.
# 이미지 파일명이 정확히 일치해야 합니다. (아래 파일명 확인)
IMAGE_NAME="bootimg.png"
CURRENT_DIR=$(cd "$(dirname "$0")" && pwd)
IMAGE_PATH="${CURRENT_DIR}/${IMAGE_NAME}"
THEME_NAME="grapesorter"

if [[ $EUID -ne 0 ]]; then
   echo "이 스크립트는 sudo 권한으로 실행해야 합니다. (sudo ./setup_boot_screen.sh)"
   exit 1
fi

echo "=========================================================="
echo "1/6. 패키지 설치 및 환경 점검..."
apt-get update
apt-get install -y plymouth plymouth-themes pix-plym-splash

echo "2/6. 테마 디렉토리 생성..."
mkdir -p /usr/share/plymouth/themes/${THEME_NAME}

echo "3/6. 이미지 확인 및 복사..."
# 이미지 파일이 있는지 확인합니다.
if [ ! -f "${IMAGE_PATH}" ]; then
    echo "❌ 오류: 이미지를 찾을 수 없습니다!"
    echo "경로 확인: ${IMAGE_PATH}"
    echo "이미지 파일명이 ${IMAGE_NAME} 이 맞는지 확인해 주세요."
    exit 1
fi
cp "${IMAGE_PATH}" /usr/share/plymouth/themes/${THEME_NAME}/background.png

echo "4/6. 테마 설정 파일 작성 (소문자 cat 사용)..."
# 여기에 있던 대문자 CAT을 모두 소문자로 수정했습니다.
cat > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.plymouth <<EOF
[Plymouth Theme]
Name=GrapeSorter
Description=Smart Grape Sorting System
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/${THEME_NAME}
ScriptFile=/usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script
EOF

echo "5/6. 스크립트 파일 작성..."
cat > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script <<EOF
bg_image = Image("background.png");
screen_width = Window.GetWidth();
screen_height = Window.GetHeight();
resized_image = bg_image.Scale(screen_width, screen_height);
sprite = Sprite(resized_image);
sprite.SetX(0);
sprite.SetY(0);
EOF

echo "6/6. 테마 적용 및 시스템 업데이트 (시간이 다소 소요됩니다)..."
plymouth-set-default-theme ${THEME_NAME} -R

echo "=========================================================="
echo "✅ 모든 설정이 완료되었습니다!"
echo "이제 'sudo reboot'를 입력하여 부팅 화면을 확인하세요."
echo "=========================================================="