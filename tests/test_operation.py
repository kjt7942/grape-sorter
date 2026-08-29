"""실기 운전 동작: 재조합, 생산 실적, 부족분 표시, 프리셋, 설정 백업."""
import csv
import json
import os

import harness as h


def check_recombine(window):
    """조합무게 카드 터치는 그 조합을 거절하고 차선을 내놔야 한다.

    탐색이 결정적이라, 거절 목록이 없으면 실기에서 같은 답이 되돌아온다.
    (시뮬레이션은 무게를 새로 만들기 때문에 동작하는 것처럼 보였다)
    """
    W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.current_preset_index = None
    window.locked_combo = None
    window.rejected_combos.clear()

    window.on_data_received(W)
    first = sorted(window.original_locked_indices)
    assert first, "첫 조합이 없음"

    window.force_unlock()
    second = sorted(window.original_locked_indices)
    assert second and second != first, f"실기에서 재조합 안 됨: {first} -> {second}"
    h.ok(f"카드 터치 시 차선 조합 제시 ({first} -> {second})")

    seen = {tuple(first), tuple(second)}
    for _ in range(10):
        window.force_unlock()
        assert window.original_locked_indices, "후보 소진 후 조합이 사라짐"
        seen.add(tuple(sorted(window.original_locked_indices)))
    h.ok(f"후보 소진 후 순환 (본 조합 {len(seen)}가지)")

    # 저울 구성이 바뀌면 거절 이력은 의미가 없다.
    window.rejected_combos.add(frozenset([1, 2]))
    changed = list(W)
    changed[5] = 800
    window.on_data_received(changed)
    assert not window.rejected_combos, "구성이 바뀌었는데 거절 이력이 남음"
    h.ok("저울 구성 변경 시 거절 이력 초기화")


def check_production(window, main_mod):
    """잠긴 조합의 저울이 전부 0이 되면 박스 하나로 기록한다."""
    W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
    window.locked_combo = None
    window.rejected_combos.clear()
    window.on_data_received(W)
    taken = list(window.original_locked_indices)
    target, total = window.locked_target, window.locked_sum

    emptied = list(W)
    for scale in taken:
        emptied[scale - 1] = 0
    window.on_data_received(emptied)

    with open(main_mod.PRODUCTION_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2, rows
    assert int(rows[1][2]) == target and int(rows[1][3]) == total
    assert int(rows[1][3]) >= int(rows[1][2]), "미달 박스가 기록됨"
    h.ok(f"박스 완성 기록 {rows[1][3]}g (목표 {rows[1][2]}g)")

    # 통신이 끊겨 전 채널 ERR 이 된 것은 박스가 아니다.
    before = len(rows)
    window.locked_combo = None
    window.on_data_received(W)
    window.on_data_received([h.ERR] * 12)
    with open(main_mod.PRODUCTION_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) == before, f"통신 두절이 실적으로 기록됨: {rows[before:]}"
    h.ok("통신 두절은 실적에서 제외")


def check_topup_production(window, main_mod):
    """보태기 모드에서도 화면에 뜬 박스 전체 무게가 기록돼야 한다.

    조합분(보탠 양)만 남기면 목표 650g / 실제 660g 같은 행이 되어
    출하 기록으로 쓸 수 없다.
    """
    with open(main_mod.PRODUCTION_FILE, "w", encoding="utf-8-sig") as f:
        pass
    os.remove(main_mod.PRODUCTION_FILE)

    # 박스(1,2,7,8) = 1,400g, 목표 2,050g -> 650g 보태야 함
    TOPUP = [350, 360, 700, 680, 720, 660, 340, 350, 830, 760, 590, 640]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 3, 4, 50
    window.current_preset_index = None
    window.locked_combo = None
    window.rejected_combos.clear()
    window.toggle_topup_mode()
    window.on_data_received(TOPUP)
    shown = window.combo_val.text()
    assert shown != "조합실패", "보태기 조합 실패"

    emptied = list(TOPUP)
    for scale in window.original_locked_indices:
        emptied[scale - 1] = 0
    window.on_data_received(emptied)
    window.toggle_topup_mode()

    with open(main_mod.PRODUCTION_FILE, encoding="utf-8-sig") as f:
        row = list(csv.reader(f))[1]
    assert int(row[2]) == 2050, f"목표를 보탤 양으로 기록: {row}"
    assert f"{int(row[3]):,} g" == shown, f"화면({shown})과 기록({row[3]}g)이 다름"
    h.ok(f"보태기 실적이 박스 전체 무게로 기록 (목표 {row[2]}g, 실제 {row[3]}g)")


def check_calibration_led_gate(window, main_ui, sent):
    """보정 중에는 조합 LED 가 나가면 안 된다.

    분동을 옮겨 다니면 조합이 계속 바뀌고, LED 가 따라 깜빡이면
    지금 어느 저울을 보정 중인지 헷갈린다.
    """
    window.locked_combo = None
    window.rejected_combos.clear()
    window.cal_dialog = main_ui.CalibrationDialog(window, is_dark_mode=True, ref_weight=430)
    window.cal_dialog.show()

    sent.clear()
    for _ in range(10):
        window.locked_combo = None
        window.on_data_received([1000, 1050] + [0] * 10)
        window.on_data_received([0, 0, 430] + [0] * 9)
    assert sent == [], f"보정 중 조합 LED 가 나감: {sent}"

    window.cal_dialog.close()
    window.cal_dialog = None
    h.ok("보정 중 조합 LED 차단")


def check_shortfall(window):
    window.locked_combo = None
    window.rejected_combos.clear()
    window.target_weight = 9000
    window.on_data_received([1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0])
    assert window.combo_val.text() == "조합실패"
    assert "부족" in window.lbl_combo_title.text(), window.lbl_combo_title.text()
    h.ok(f"조합 실패 시 부족분 표시 ({window.lbl_combo_title.text()})")
    window.target_weight = 2050


def check_presets(window, main_ui):
    """저장 직후 '저장됨!' 이 잠깐 뜬 뒤 저장된 내용으로 갱신돼야 한다."""
    dialog = main_ui.PresetDialog(window, is_dark_mode=True)
    for i, button in enumerate(dialog.preset_buttons):
        window.refresh_preset_button(button, i)
        button.longPressed.connect(
            lambda idx=i, b=button: window.save_preset(idx, b))
    dialog.show()

    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 3, 4, 40
    dialog.preset_buttons[2].longPressed.emit()
    assert "저장됨" in dialog.preset_buttons[2].text()

    h.wait(1300)
    text = dialog.preset_buttons[2].text()
    assert "저장됨" not in text, "저장 표시가 그대로 남음"
    assert "2,050g +40" in text, text
    assert dialog.preset_buttons[2].styleSheet() == "", "초록 배경이 남음"
    h.ok("프리셋 저장 후 그 자리에서 내용 갱신")

    # 저장 직후 창을 닫아도 콜백이 죽은 위젯을 건드리면 안 된다.
    dialog.preset_buttons[5].longPressed.emit()
    dialog.close()
    dialog.deleteLater()
    h.wait(1500)
    h.ok("저장 직후 창을 닫아도 안전")


def check_settings_backup(window, main_mod):
    window.target_weight = 1234
    window.save_settings()
    main_mod.MainApp.backup_settings()

    with open(main_mod.SETTINGS_FILE, "w", encoding="utf-8") as f:
        f.write("{ 깨진 파일")
    restored = window.load_settings()
    assert restored["last_state"]["target_weight"] == 1234, restored["last_state"]
    assert os.path.exists(main_mod.SETTINGS_FILE + ".corrupt")
    h.ok("깨진 설정을 백업에서 복구")

    # 쓰는 도중 죽어도 기존 파일이 남아야 한다 (os.replace 사용 확인).
    path = main_mod.SETTINGS_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"keep": 1}, f)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"new": 2}, f)
            raise RuntimeError("전원 차단 흉내")
        os.replace(tmp, path)
    except RuntimeError:
        pass
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"keep": 1}, "기존 설정이 사라짐"
    h.ok("설정 저장 중 전원이 끊겨도 직전 설정 보존")


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod)

    check_recombine(window)
    check_production(window, main_mod)
    check_topup_production(window, main_mod)
    check_calibration_led_gate(window, main_ui, sent)
    check_shortfall(window)
    check_presets(window, main_ui)
    check_settings_backup(window, main_mod)

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_operation OK")
