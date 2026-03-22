#!/bin/bash

# --- 사용자 설정 ---
# 스크립트와 같은 폴더에 있는 이미지 파일명을 여기에 적어주세요.
# (현재 bootimg.png 로 되어 있습니다. 파일명이 다르면 이 부분만 수정하세요)
IMAGE_NAME="bootimg.png"
CURRENT_DIR=$(cd "$(dirname "$0")" && pwd)
IMAGE_PATH="${CURRENT_DIR}/${IMAGE_NAME}"
THEME_NAME="grapesorter"

if [[ $EUID -ne 0 ]]; then
   echo "이 스크립트는 sudo 권한으로 실행해야 합니다. (예: sudo ./setup_boot_screen.sh)"
   exit 1
fi

echo "=========================================================="
echo "라즈베리파이 부팅/종료 화면 설정을 시작합니다."
echo "=========================================================="

echo "1/6. 패키지 설치 및 환경 점검..."
apt-get update
apt-get install -y plymouth plymouth-themes pix-plym-splash

echo "2/6. 테마 디렉토리 생성..."
mkdir -p /usr/share/plymouth/themes/${THEME_NAME}

echo "3/6. 이미지 확인 및 복사..."
if [ ! -f "${IMAGE_PATH}" ]; then
    echo "❌ 오류: 이미지를 찾을 수 없습니다!"
    echo "찾고 있는 경로: ${IMAGE_PATH}"
    echo "이미지 파일명이 정확히 '${IMAGE_NAME}'인지 확인해 주세요."
    exit 1
fi
cp "${IMAGE_PATH}" /usr/share/plymouth/themes/${THEME_NAME}/background.png

echo "4/6. 테마 설정 파일 작성..."
# [중요] 여기를 소문자 cat으로 수정했습니다.
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
# [중요] 여기를 소문자 cat으로 수정했습니다.
cat > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script <<EOF
bg_image = Image("background.png");
screen_width = Window.GetWidth();
screen_height = Window.GetHeight();
resized_image = bg_image.Scale(screen_width, screen_height);
sprite = Sprite(resized_image);
sprite.SetX(0);
sprite.SetY(0);
EOF

echo "6/6. 테마 적용 및 시스템 업데이트 (1~2분 정도 소요됩니다)..."
plymouth-set-default-theme ${THEME_NAME} -R

if [ $? -eq 0 ]; then
    echo "=========================================================="
    echo "✅ 모든 설정이 완료되었습니다!"
    echo "이제 'sudo reboot'를 입력하여 결과를 확인하세요."
    echo "=========================================================="
else
    echo "❌ 업데이트 중 문제가 발생했습니다. 수동으로 'sudo update-initramfs -u'를 실행해 보세요."
fi