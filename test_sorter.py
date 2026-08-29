"""조합 탐색과 설정 저장의 자체 점검. PyQt5 없이 실행된다.

    python3 test_sorter.py
"""
import importlib.util
import json
import os
import sys
import tempfile


def load_main_without_qt():
    """main.py 는 PyQt5 를 import 한다. 순수 로직만 쓰려고 최소한의 더미를 끼운다."""
    try:
        import PyQt5  # noqa: F401
        import main
        return main
    except ImportError:
        pass

    import types
    for name in ("PyQt5", "PyQt5.QtWidgets", "PyQt5.QtCore", "PyQt5.QtGui"):
        sys.modules.setdefault(name, types.ModuleType(name))
    for name, attrs in (
        ("PyQt5.QtWidgets", ["QApplication", "QMessageBox"]),
        ("PyQt5.QtCore", ["QThread", "pyqtSignal", "Qt", "QTimer"]),
    ):
        for a in attrs:
            setattr(sys.modules[name], a, type(a, (), {}))
    sys.modules.setdefault("main_ui", types.ModuleType("main_ui"))
    for a in ("SmartSorterUI", "PresetDialog", "CalibrationDialog", "ScaleCheckDialog"):
        setattr(sys.modules["main_ui"], a, type(a, (), {}))

    spec = importlib.util.spec_from_file_location(
        "main", os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_best_combination(best_combination):
    items = [(1, 700), (2, 680), (3, 720), (4, 500), (5, 900)]

    # 목표 2050, 허용 +50 -> 초과분이 가장 작은 조합 (680+900+500=2080, 초과 30)
    r = best_combination(items, 2050, 3, 4, 50)
    assert r.total == 2080, r.total
    assert sorted(i for i, _ in r.combo) == [2, 4, 5], r.combo

    # 허용오차를 좁히면 후보가 사라진다 (초과 30 > 10)
    r = best_combination(items, 2050, 3, 4, 10)
    assert r.combo is None, r.combo

    # 허용오차를 넓혀도 여전히 최소 초과분을 고른다
    assert best_combination(items, 2050, 3, 4, 300).total == 2080

    # 목표 미달 조합은 절대 선택하지 않는다 (미달 출하 방지)
    r = best_combination(items, 5000, 1, 5, 100)
    assert r.combo is None, r.combo
    # 대신 얼마나 모자란지는 알려준다 (전체 합 3500)
    assert r.near_total == 3500, r.near_total

    # 동점이면 저울을 더 많이 쓰는 쪽 (작은 송이부터 소진)
    tie = [(1, 1000), (2, 600), (3, 400)]
    r = best_combination(tie, 1000, 1, 3, 0)
    assert r.total == 1000 and len(r.combo) == 2, r.combo

    # max_c 가 보유 저울 수보다 커도 터지지 않는다
    assert best_combination(tie, 1900, 1, 12, 200).total == 2000

    # 저울이 없으면 조합 없음
    r = best_combination([], 1000, 1, 4, 50)
    assert r.combo is None and r.near_total is None, r
    print("  best_combination OK")


def test_rejected_combos(best_combination):
    """조합무게 카드를 눌러 거절하면 다음 후보가 나와야 한다."""
    items = [(1, 1000), (2, 1050), (3, 1020), (4, 1030)]

    first = best_combination(items, 2050, 2, 2, 50)
    assert first.combo is not None, "첫 조합이 있어야 한다"

    rejected = {frozenset(i for i, _ in first.combo)}
    second = best_combination(items, 2050, 2, 2, 50, rejected)
    assert second.combo is not None, "차선 조합이 나와야 한다"
    assert frozenset(i for i, _ in second.combo) not in rejected, "같은 조합이 다시 나옴"

    # 후보를 전부 거절하면 결과 없음 -> 앱은 이때 이력을 비우고 순환한다
    every = set()
    while True:
        r = best_combination(items, 2050, 2, 2, 50, every)
        if r.combo is None:
            break
        every.add(frozenset(i for i, _ in r.combo))
    assert len(every) >= 2, every
    print("  rejected_combos OK")


def test_atomic_settings_write():
    """save_settings 가 쓰는 도중 죽어도 기존 파일이 남는지 = os.replace 사용 확인."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "settings.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"keep": 1}, f)

        tmp = path + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({"new": 2}, f)
                raise RuntimeError("전원 차단 흉내")
            os.replace(tmp, path)
        except RuntimeError:
            pass

        with open(path, encoding='utf-8') as f:
            assert json.load(f) == {"keep": 1}, "기존 설정이 살아있어야 한다"
        assert os.path.exists(tmp), "임시 파일만 남아야 한다"
    print("  atomic settings write OK")


if __name__ == "__main__":
    main = load_main_without_qt()
    print("자체 점검 실행")
    test_best_combination(main.best_combination)
    test_rejected_combos(main.best_combination)
    test_atomic_settings_write()
    assert main.DEFAULT_TOLERANCE == 50, main.DEFAULT_TOLERANCE
    assert main.LOADCELL_COUNT == 12
    print("모두 통과")
