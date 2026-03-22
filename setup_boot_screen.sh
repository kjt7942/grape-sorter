#!/bin/bash

# --- 사용자 설정 ---
# ⚠️ 현재 파일이 위치한 폴더의 경로를 자동으로 가져와 이미지 경로를 설정합니다.
# 이미지 파일명이 boot_image.png가 맞는지 확인해 주세요.
CURRENT_DIR=$(pwd)
IMAGE_PATH="${CURRENT_DIR}/bootimg.png"
THEME_NAME="grapesorter"

if [[ $EUID -ne 0 ]]; then
   echo "이 스크립트는 sudo 권한으로 실행해야 합니다."
   exit 1
fi

echo "=========================================================="
echo "1/6. 필요한 패키지 설치 및 복구 중..."
apt-get update
apt-get install -y plymouth plymouth-themes pix-plym-splash

echo "2/6. 테마 디렉토리 생성..."
mkdir -p /usr/share/plymouth/themes/${THEME_NAME}

echo "3/6. 이미지 복사 (절대경로: ${IMAGE_PATH})..."
if [ ! -f "${IMAGE_PATH}" ]; then
    echo "❌ [오류] 이미지를 찾을 수 없습니다: ${IMAGE_PATH}"
    echo "이미지 파일이 스크립트와 같은 폴더에 있는지 확인하세요."
    exit 1
fi
cp "${IMAGE_PATH}" /usr/share/plymouth/themes/${THEME_NAME}/background.png

echo "4/6. Plymouth 테마 정의 파일 작성..."
cat > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.plymouth <<EOF
[Plymouth Theme]
Name=GrapeSorter
Description=Smart Grape Sorting System
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/${THEME_NAME}
ScriptFile=/usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script
EOF
#

echo "5/6. Plymouth 스크립트 파일 작성..."
cat > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script <<EOF
bg_image = Image("background.png");
screen_width = Window.GetWidth();
screen_height = Window.GetHeight();
resized_image = bg_image.Scale(screen_width, screen_height);
sprite = Sprite(resized_image);
sprite.SetX(0);
sprite.SetY(0);
EOF
#

echo "6/6. 테마 적용 및 시스템 업데이트 (약 1~2분 소요)..."
plymouth-set-default-theme ${THEME_NAME} -R

if [ $? -eq 0 ]; then
    echo "✅ 모든 설정이 완료되었습니다!"
    echo "sudo reboot 명령어로 재부팅하여 확인해 보세요."
else
    echo "❌ 업데이트 중 문제가 발생했습니다. 'sudo update-initramfs -u'를 수동으로 실행해 보세요."
fi