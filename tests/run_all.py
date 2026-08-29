"""테스트 전부 실행.

    python3 tests/run_all.py            # 전체
    python3 tests/run_all.py leds       # 이름에 leds 가 들어간 것만

각 테스트는 별도 프로세스에서 돈다. QApplication 과 main 모듈 전역 상태가
서로 간섭하기 때문이다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# (표시 이름, 실행 명령). test_sorter.py 는 PyQt5 없이 돌아야 하므로 저장소 루트에 둔다.
SUITES = [
    ("test_sorter (조합 로직, OTA 관문)", [sys.executable, os.path.join(REPO, "test_sorter.py")], REPO),
    ("test_layout (800x480 배치)", [sys.executable, os.path.join(HERE, "test_layout.py")], HERE),
    ("test_leds (LED 송신 경로)", [sys.executable, os.path.join(HERE, "test_leds.py")], HERE),
    ("test_operation (재조합/실적/프리셋/백업)", [sys.executable, os.path.join(HERE, "test_operation.py")], HERE),
    ("test_startup (시작 절차/영점/보정)", [sys.executable, os.path.join(HERE, "test_startup.py")], HERE),
    ("test_assembly (조립 단계별)", [sys.executable, os.path.join(HERE, "test_assembly.py")], HERE),
    ("test_ota_rollback (OTA 자동 롤백)", ["bash", os.path.join(HERE, "test_ota_rollback.sh")], HERE),
]


def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    suites = [s for s in SUITES if keyword in s[0]]
    if not suites:
        print(f"'{keyword}' 에 해당하는 테스트가 없습니다.")
        return 1

    env = dict(os.environ, PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen")
    failed = []

    for name, command, cwd in suites:
        print(f"\n=== {name} ===")
        # Windows 기본 인코딩(cp949)으로 읽으면 한글 출력에서 터진다.
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=300)
        output = (result.stdout or "") + (result.stderr or "")
        print(output.rstrip())
        if result.returncode != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    if failed:
        print(f"실패 {len(failed)} / {len(suites)}")
        for name in failed:
            print(f"  - {name}")
        return 1
    print(f"전부 통과 ({len(suites)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
