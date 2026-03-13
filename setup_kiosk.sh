#!/bin/bash
# =========================================================================
# 라즈베리파이 스마트 포도 선별기 환경 구축 및 Kiosk 부팅 스크립트
# OS: Raspberry Pi OS Lite (CLI 전용 환경 권장)
# =========================================================================

echo "=== 스마트 포도 선별기 Kiosk 환경 설정을 시작합니다 ==="

# 1. 필수 의존성 패키지 설치
echo "[1/4] X11 및 파이썬 필수 패키지 설치 중..."
sudo apt update
sudo apt install -y xinit x11-xserver-utils python3-tk python3-serial git unclutter

# 2. X 환경 설정 파일 생성 (.xinitrc)
echo "[2/4] X 서버 시작 스크립트(.xinitrc) 작성 중..."
cat << 'EOF' > ~/.xinitrc
#!/bin/sh
# 화면 보호기 및 전원 관리(DPMS) 끄기
xset s off
xset -dpms
xset s noblank

# 터치 환경 대비 마우스 커서 숨기기 (unclutter)
unclutter -idle 0.1 -root &

# 창 관리자 없이 파이썬 GUI 메인 프로그램 다이렉트 실행 (최대화면)
# 소스 코드가 ~/포도선별기 디렉토리에 위치해있다고 가정
cd ~/포도선별기 || exit 1
exec python3 main.py
EOF

# 스크립트 실행 권한 부여
chmod +x ~/.xinitrc

# 3. 자동 부팅 시 X 서버 기동 설정 (.bash_profile)
echo "[3/4] CLI 자동 로그인 시 GUI 구동 적용 중..."
if ! grep -q "startx" ~/.bash_profile 2>/dev/null; then
    cat << 'EOF' >> ~/.bash_profile

# TTY1 (기본 터미널 콘솔)에서 자동 로그인이 된 경우 즉시 xinit 실행
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    startx
fi
EOF
    echo " -> .bash_profile 에 startx가 추가되었습니다."
else
    echo " -> 이미 .bash_profile 에 startx가 반영되어 있습니다."
fi

echo "[4/4] 모든 설정이 완료되었습니다."
echo "========================================================================="
echo "* 앱 구동을 위해 소스코드를 홈 디렉토리의 '포도선별기' 폴더(~/포도선별기)에 위치시켜주세요."
echo "* 기본적으로 Raspberry Pi Configuration에서 'Console Autologin'이 켜져있어야 합니다."
echo "  (설정 방법: sudo raspi-config -> 1 System Options -> S5 Boot / Auto Login -> B2 Console Autologin 선택)"
echo "* 위 세팅 후 재부팅(sudo reboot) 시 선별기 프로그램이 자동으로 전체화면 실행됩니다."
echo "========================================================================="
