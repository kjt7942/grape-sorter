#!/bin/bash

# ==========================================================
# 라즈베리파이 부팅/종료 화면 적용 스크립트 (Plymouth 기반)
# ==========================================================

# --- 사용자 설정 ---
# 원본 이미지 파일의 절대 경로를 입력하세요. (이미지 파일은 PNG 형식이어야 합니다)
IMAGE_PATH="/home/user/grape-sorter/bootimg.png"
# 새로운 테마 이름
THEME_NAME="grapesorter"

# --- 스크립트 시작 (루트 권한 확인) ---
if [[ $EUID -ne 0 ]]; then
   echo "이 스크립트는 루트 권한으로 실행되어야 합니다. (sudo 사용)"
   exit 1
fi

echo "=========================================================="
echo "라즈베리파이 부팅/종료 화면 설정을 시작합니다."
echo "=========================================================="

# 1. 필수 패키지 설치
echo "1/6. 필요한 패키지 (plymouth)를 설치/확인합니다..."
apt-get update > /dev/null
apt-get install -y plymouth plymouth-themes > /dev/null

if [ $? -ne 0 ]; then
    echo "패키지 설치에 실패했습니다. 인터넷 연결을 확인하세요."
    exit 1
fi

# 2. 새로운 Plymouth 테마 디렉토리 생성
echo "2/6. 테마 디렉토리를 생성합니다: /usr/share/plymouth/themes/${THEME_NAME}..."
mkdir -p /usr/share/plymouth/themes/${THEME_NAME}

# 3. 원본 이미지를 테마 디렉토리로 복사 및 이름 변경
if [ ! -f "${IMAGE_PATH}" ]; then
    echo "원본 이미지 파일을 찾을 수 없습니다: ${IMAGE_PATH}"
    echo "IMAGE_PATH 변수를 실제 파일 경로로 수정해 주세요."
    exit 1
fi

echo "3/6. 이미지를 복사합니다..."
cp "${IMAGE_PATH}" /usr/share/plymouth/themes/${THEME_NAME}/background.png

# 4. Plymouth 테마 설정 파일 작성
echo "4/6. Plymouth 테마 정의 파일을 작성합니다..."
CAT > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.plymouth <<EOF
[Plymouth Theme]
Name=GrapeSorter Boot/Shutdown
Description=Boot and Shutdown screen for the Smart Grape Sorting System
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/${THEME_NAME}
ScriptFile=/usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script
EOF

# 5. Plymouth 테마 스크립트 파일 작성 (이미지만 표시하는 심플 스크립트)
echo "5/6. Plymouth 스크립트 파일을 작성합니다..."
CAT > /usr/share/plymouth/themes/${THEME_NAME}/${THEME_NAME}.script <<EOF
// 배경색 설정 (이미지가 검은색이므로 검은색으로)
Window.SetBackgroundTopColor (0, 0, 0);
Window.SetBackgroundBottomColor (0, 0, 0);

// 배경 이미지 불러오기
bg_image = Image("background.png");

// 화면 크기 가져오기
screen_width = Window.GetWidth();
screen_height = Window.GetHeight();

// 이미지 크기 가져오기
image_width = bg_image.GetWidth();
image_height = bg_image.GetHeight();

// 화면 중앙 좌표 계산
scaled_image = bg_image; # 원본 비율 유지
sprite = Sprite(scaled_image);

// 이미지를 화면 중앙에 배치
sprite.SetX((screen_width - image_width) / 2);
sprite.SetY((screen_height - image_height) / 2);

# --- 상태 업데이트 시 추가 작업이 필요한 경우 여기에 ---
# (예: 진행 바, 텍스트 표시 등. 여기서는 Simple 이미지 로고만 표시)
fun refresh_callback ()
{
}

Plymouth.SetRefreshFunction (refresh_callback);
EOF

# 6. 테마 적용 및 시스템 업데이트
echo "6/6. 새로운 테마를 시스템에 적용하고 커널 이미지를 업데이트합니다..."
# 현재 테마를 로고 테마로 설정
plymouth-set-default-theme ${THEME_NAME} -R

if [ $? -eq 0 ]; then
    echo "=========================================================="
    echo "설정이 완료되었습니다!"
    echo "시스템을 재부팅하면 새로운 부팅 화면과 종료 화면을 볼 수 있습니다."
    echo "=========================================================="
else
    echo "커널 이미지 업데이트에 실패했습니다. 수동으로 'sudo update-initramfs -u'를 실행해 보세요."
fi