#!/bin/bash
# OTA 자동 롤백 검증.
#
# 가짜 원격 저장소를 만들어 깨진 커밋을 푸시하고, 현장 기기 역할의 클론이
# main.py 의 OTA 순서(reset --hard -> pull -> test_sorter.py -> 실패 시 롤백)를
# 그대로 따랐을 때 이전 커밋으로 되돌아가는지 확인한다.
#
# 이 검증이 지키는 것: 깨진 코드를 푸시해도 현장 기기가 크래시 루프에 빠지지 않는다.
set -e

SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE="$(mktemp -d)"
trap 'rm -rf "$BASE"' EXIT

GIT="git -c user.email=test@test -c user.name=test -c commit.gpgsign=false"

echo "  원격 저장소 흉내 준비"
git init -q --bare "$BASE/remote.git"
git clone -q "$BASE/remote.git" "$BASE/work" 2>/dev/null
cp "$SRC/main.py" "$SRC/main_ui.py" "$SRC/test_sorter.py" "$BASE/work/"
cd "$BASE/work"
$GIT add -A
$GIT commit -qm "good"
$GIT push -q origin HEAD:refs/heads/main
$GIT branch -q -M main

git clone -q -b main "$BASE/remote.git" "$BASE/device"
GOOD=$(cd "$BASE/device" && git rev-parse HEAD)
echo "  정상 커밋 ${GOOD:0:8}"

echo "  깨진 코드 푸시 (목표 미달 조합도 통과시키도록 고장냄)"
cd "$BASE/work"
python - <<'PY'
import io
path = "main.py"
source = io.open(path, encoding="utf-8").read()
broken = source.replace("            if diff < 0:", "            if False:")
assert broken != source, "고장낼 지점을 찾지 못함 (main.py 구조가 바뀜)"
io.open(path, "w", encoding="utf-8").write(broken)
PY
$GIT commit -qam "broken"
$GIT push -q origin main

echo "  기기에서 OTA 수행"
cd "$BASE/device"
PREV=$(git rev-parse HEAD)
git reset -q --hard
git -c user.email=test@test -c user.name=test pull -q
echo "  pull 후 HEAD $(git rev-parse --short HEAD)"

if python test_sorter.py > /dev/null 2>&1; then
    echo "  [FAIL] 깨진 코드가 자체 점검을 통과했다"
    exit 1
fi
echo "  자체 점검 실패 감지 -> 롤백"
git reset -q --hard "$PREV"

if [ "$(git rev-parse HEAD)" != "$GOOD" ]; then
    echo "  [FAIL] 롤백 실패: $(git rev-parse --short HEAD)"
    exit 1
fi
echo "  [OK] 정상 커밋 $(git rev-parse --short HEAD) 으로 복귀"

python test_sorter.py > /dev/null 2>&1
echo "  [OK] 되돌린 코드는 자체 점검 통과"
echo "test_ota_rollback OK"
