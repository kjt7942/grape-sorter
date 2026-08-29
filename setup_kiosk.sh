#!/bin/bash
# =========================================================================
# 라즈베리파이 스마트 포도 선별기 환경 구축 및 Kiosk 부팅 스크립트
# OS: Raspberry Pi OS Lite (CLI 전용 환경 권장)
# =========================================================================

echo "=== 스마트 포도 선별기 Kiosk 환경 설정을 시작합니다 ==="

# 1. 필수 의존성 패키지 설치
echo "[1/4] X11 및 파이썬 필수 패키지 설치 중..."
sudo apt update
sudo apt install -y xinit x11-xserver-utils python3-tk python3-pyqt5 python3-serial git unclutter

# 2. X 환경 설정 파일 생성 (.xinitrc)
# 소스 위치는 이 스크립트가 있는 디렉토리를 그대로 쓴다. 경로를 손으로 맞출 필요 없음.
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[2/4] X 서버 시작 스크립트(.xinitrc) 작성 중... (앱 경로: $APP_DIR)"
cat << EOF > ~/.xinitrc
#!/bin/sh
# 화면 보호기 및 전원 관리(DPMS) 끄기
xset s off
xset -dpms
xset s noblank

# 터치 환경 대비 마우스 커서 숨기기 (unclutter)
unclutter -idle 0.1 -root &

cd "$APP_DIR" || exit 1

# 창 관리자가 없어 앱이 죽으면 화면이 빈 콘솔로 떨어진다.
# 비정상 종료(0이 아닌 종료코드)면 자동으로 다시 띄운다.
# 화면 ① 카드 더블탭으로 정상 종료하면 0을 반환하므로 루프가 끝난다.
until python3 main.py; do
    echo "[kiosk] 프로그램이 비정상 종료됨. 3초 후 재시작." >&2
    sleep 3
done
EOF

# 스크립트 실행 권한 부여
chmod +x ~/.xinitrc

# 2-1. 재부팅/전원끄기 권한 부여
# 화면의 ⑪·⑫ 카드 더블탭이 동작하려면 비밀번호 없는 sudo 가 필요하다.
# reboot/shutdown 두 명령에만 한정해서 허용한다.
echo "[2-1/4] 재부팅·전원끄기 sudo 권한 설정 중..."
SUDOERS_FILE=/etc/sudoers.d/grape-sorter
cat << EOF | sudo tee "$SUDOERS_FILE" > /dev/null
$(whoami) ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/shutdown, /usr/sbin/reboot, /usr/sbin/shutdown
EOF
sudo chmod 440 "$SUDOERS_FILE"
if sudo visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo " -> $SUDOERS_FILE 적용 완료"
else
    echo " -> [경고] sudoers 문법 오류. 파일을 제거합니다."
    sudo rm -f "$SUDOERS_FILE"
fi

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
echo "* 앱 경로는 이 스크립트 위치($APP_DIR)로 자동 설정되었습니다."
echo "* 기본적으로 Raspberry Pi Configuration에서 'Console Autologin'이 켜져있어야 합니다."
echo "  (설정 방법: sudo raspi-config -> 1 System Options -> S5 Boot / Auto Login -> B2 Console Autologin 선택)"
echo "* 위 세팅 후 재부팅(sudo reboot) 시 선별기 프로그램이 자동으로 전체화면 실행됩니다."
echo "========================================================================="
