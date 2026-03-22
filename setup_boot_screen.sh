#!/bin/bash

# --- 사용자 설정 ---
# ⚠️ 주의: 실제 이미지 파일이 있는 절대경로로 수정하세요!
IMAGE_PATH="/home/pi/grape-sorter/boot_image.png"
THEME_NAME="grapesorter"

if [[ $EUID -ne 0 ]]; then
   echo "이 스크립트는 sudo 권한으로 실행해야 합니다."
   exit 1
fi

echo "1/6. 패키지 설치 상태 확인 중..."
# 중단된 설치가 있다면 복구하고 plymouth 설치
apt-get update
apt-get install -y plymouth plymouth-themes pix-plym-splash

echo "2/6. 테마 디렉토리 생성..."
mkdir -p /usr/share/plymouth/themes/${THEME_NAME}

echo "3/6. 이미지 복사..."
if [ ! -f "${IMAGE_PATH}" ]; then
    echo "❌ 오류: 이미지를 찾을 수 없습니다: ${IMAGE_PATH}"
    exit 1
fi
cp "${IMAGE_PATH}" /usr/share/plymouth/themes/${THEME_NAME}/background.png

echo "4/6. 테마 설정 파일 작성..."
# cat은 반드시 소문자로 작성해야 합니다.
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

echo "6/6. 테마 적용 및 시스템 업데이트..."
plymouth-set-default-theme ${THEME_NAME} -R

echo "✅ 모든 설정이 완료되었습니다. 재부팅하여 확인해 보세요!"