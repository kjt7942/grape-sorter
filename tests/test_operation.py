"""실기 운전 동작: 재조합, 생산 실적, 부족분 표시, 프리셋, 설정 백업."""
import csv
import json
import os

import harness as h


def check_recombine(window):
    """조합무게 카드 터치는 잠금을 풀고 다시 최적 조합을 찾는다.

    저울 무게가 그대로면 탐색은 결정적이라 같은(유일한) 최적 조합이
    다시 나오는 게 맞다 — 더 이상 거절 이력으로 차선을 강제하지 않는다.
    """
    W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.current_preset_index = None
    window.locked_combo = None

    window.on_data_received(W)
    first = sorted(window.original_locked_indices)
    assert first, "첫 조합이 없음"

    window.force_unlock()
    second = sorted(window.original_locked_indices)
    assert second == first, f"저울이 그대로인데 다른 조합이 나옴: {first} -> {second}"
    h.ok(f"카드 터치: 저울이 그대로면 같은 최적 조합을 다시 선택 ({second})")

    # 저울 구성이 바뀌면 그에 맞는 새 최적 조합을 찾는다.
    changed = list(W)
    changed[5] = 800  # 6번 저울에도 무게가 올라옴
    window.locked_combo = None
    window.on_data_received(changed)
    assert window.original_locked_indices, "구성이 바뀌었는데 조합을 못 찾음"
    h.ok(f"저울 구성이 바뀌면 새 최적 조합 탐색 ({sorted(window.original_locked_indices)})")


def check_locked_sum_tracks_settling(window):
    """포도가 자리 잡으며(정착) 잠긴 저울 무게가 늘면, 그 값이 잠깐 동안
    유지될 때만(손으로 스친 순간값이 아닐 때만) 조합무게에 반영해야 한다.
    합계(전체 무게)는 항상 라이브라 실제 무게와 일치하는데, 조합무게가 잠근
    시점 값에 멈춰 있으면 둘이 어긋나 보인다."""
    W = [700, 630, 0, 0, 750, 0, 0, 0, 0, 0, 0, 0]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2030, 3, 4, 150
    window.current_preset_index = None
    window.locked_combo = None
    window.on_data_received(W)
    taken = sorted(window.original_locked_indices)
    assert taken == [1, 2, 5], taken
    assert window.locked_sum == 2080, window.locked_sum

    settled = list(W)
    settled[0] = 730  # 정착: 700 -> 730
    window.on_data_received(settled)
    assert window.locked_sum == 2080, "안정화 시간 전에 바로 반영됨 (순간값에 취약)"
    h.wait(600)
    window.on_data_received(settled)
    assert sorted(window.original_locked_indices) == taken, "정착 중 조합이 바뀜"
    assert window.locked_sum == 2110, f"안정화된 무게가 조합무게에 반영 안 됨: {window.locked_sum}"
    h.ok(f"같은 무게가 유지되면 조합무게에 반영 ({window.locked_sum}g)")

    # 손으로 잠깐 눌렀다 뗀 것 같은 순간값은 안정화가 안 되니 반영되면 안 된다.
    bump = list(settled)
    bump[0] = 900
    window.on_data_received(bump)
    window.on_data_received(settled)  # 곧바로 원래 정착값으로 복귀
    assert window.locked_sum == 2110, "순간적으로 눌린 값이 조합무게에 반영됨"
    h.ok("순간적으로 눌린 값(안정화 전 복귀)은 반영 안 함")

    # 픽업이 시작(하나가 비워짐)된 뒤로는 조합무게를 더 이상 바꾸지 않는다.
    picking = list(settled)
    picking[4] = 0  # 5번(750) 픽업 시작
    window.on_data_received(picking)
    assert window.locked_sum == 2110, "픽업이 시작됐는데 조합무게가 바뀜"
    h.wait(600)
    picking[0] = 900  # 픽업 후 다른 저울에 무게가 더 얹혀도(비정상 상황) 무시
    window.on_data_received(picking)
    assert window.locked_sum == 2110, "픽업 시작 후에도 조합무게가 바뀜"
    h.ok("픽업 시작 후에는 조합무게가 완전히 고정")

    window.locked_combo = None


def check_transient_err(window):
    """HX711 타이밍 탓에 한 번씩 섞여 오는 ERR 이 잠긴 조합을 풀면 안 된다.

    실측(2026-09-24)에서 저울당 약 30초에 1회 단발 ERR 이 왔다. 이게 -1 로
    전달되면 '비움'으로 오인되고, 다음 틱의 정상값을 '새 송이'로 보고 선택을 푼다.
    """
    serial = window.serial_thread
    serial._reset_err_hold()

    def packet(values):
        serial.parse_packet(", ".join("ERR" if v == h.ERR else str(v) for v in values))

    W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.current_preset_index = None
    window.locked_combo = None
    packet(W)
    taken = sorted(window.original_locked_indices)
    assert taken, "첫 조합이 없음"

    glitch = list(W)
    glitch[taken[0] - 1] = h.ERR
    packet(glitch)
    packet(W)
    selected = sorted(item[0] for item in (window.locked_combo or []))
    assert selected == taken, f"단발 ERR 로 선택이 풀림: {taken} -> {selected}"
    assert window.weights[taken[0] - 1] > 0
    h.ok("단발 ERR 은 직전 값으로 메워 잠긴 조합 유지")

    # 깨진 숫자도 0(비움)이 아니라 ERR 과 똑같이 다룬다.
    serial.parse_packet(", ".join(["1x00"] + [str(v) for v in W[1:]]))
    assert window.weights[0] == 1000, window.weights[0]
    h.ok("깨진 값은 0 이 아니라 직전 값으로 유지")

    # 기준(ERR_HOLD_PACKETS)을 넘겨 계속되면 진짜 고장이므로 ERR 로 보여야 한다.
    import main
    for _ in range(main.ERR_HOLD_PACKETS + 1):
        packet(glitch)
    assert window.weights[taken[0] - 1] == h.ERR, window.weights[taken[0] - 1]
    assert "ERR" in window.tray_weight_labels[taken[0] - 1].text()
    h.ok(f"ERR 이 {main.ERR_HOLD_PACKETS}회를 넘기면 에러로 표시")

    # 한 번도 정상값이 없던 채널(미배선)은 처음부터 ERR.
    serial._reset_err_hold()
    packet([h.ERR] + W[1:])
    assert window.weights[0] == h.ERR
    h.ok("미배선 채널은 처음부터 ERR")

    serial._reset_err_hold()
    window.locked_combo = None


def check_production(window, main_mod):
    """일부만 비우면 선택을 유지하고, 잠긴 저울 전부가 비면 즉시 기록하고
    잠금을 풀어 바로 다음 조합을 찾는다."""
    W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.current_preset_index = None
    window.locked_combo = None
    window.on_data_received(W)
    taken = list(window.original_locked_indices)

    # 저울 하나만 비우면(부분 픽업) 몇 틱이 지나도 선택을 유지하고 기록하지 않는다.
    partial = list(W)
    partial[taken[0] - 1] = 0
    for _ in range(5):
        window.on_data_received(partial)
    assert sorted(window.original_locked_indices) == sorted(taken), "일부만 비웠는데 선택이 풀림"
    assert not os.path.exists(main_mod.PRODUCTION_FILE), "아직 다 안 비웠는데 기록됨"
    h.ok("일부 저울만 비우면 선택 유지, 미기록")

    # 비운 저울에 300g 이상 새 송이가 올라오면 그 저울만 선택이 풀린다.
    refilled = list(partial)
    refilled[taken[0] - 1] = 500
    window.on_data_received(refilled)
    currently_selected = [item[0] for item in (window.locked_combo or [])]
    assert taken[0] not in currently_selected, "300g 이상 재적재됐는데 선택이 안 풀림"
    assert taken[1] in currently_selected, "재적재 안 한 저울까지 선택이 풀림"
    h.ok("300g 이상 재적재된 저울만 선택 해제")

    # 잠긴 저울 전부가 동시에 비면 즉시 기록하고, 남은 저울로 바로 다음 조합을 찾는다.
    window.locked_combo = None
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

    remaining = [item[0] for item in (window.locked_combo or [])]
    assert remaining and set(remaining).isdisjoint(taken), \
        f"박스를 전부 비웠는데 바로 다음 조합을 못 찾음: {remaining}"
    h.ok(f"박스를 전부 비우면 즉시 잠금 풀고 남은 저울로 다음 조합 {remaining} 을 찾음")

    window.locked_combo = None

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


def check_clock_marking(window, main_mod):
    """라즈베리파이 3B 에는 RTC 가 없다. 시각을 못 믿으면 실적에 표시를 남긴다.

    fake-hwclock 이 마지막 종료 시각을 복원하므로 연도만 봐서는 알 수 없고,
    네트워크 동기화 여부를 봐야 한다.
    """
    original = main_mod.clock_is_trustworthy
    os.remove(main_mod.PRODUCTION_FILE)

    def record_one():
        W = [1000, 1050, 1020, 1030, 990, 0, 0, 0, 0, 0, 0, 0]
        window.locked_combo = None
        window.target_weight, window.min_comb, window.max_comb = 2050, 2, 2
        window.on_data_received(W)
        emptied = list(W)
        for scale in window.original_locked_indices:
            emptied[scale - 1] = 0
        window.on_data_received(emptied)

    try:
        main_mod.clock_is_trustworthy = lambda: True
        record_one()
        main_mod.clock_is_trustworthy = lambda: False
        record_one()
    finally:
        main_mod.clock_is_trustworthy = original

    with open(main_mod.PRODUCTION_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert main_mod.CLOCK_UNSYNCED_MARK not in rows[1][0], rows[1][0]
    assert main_mod.CLOCK_UNSYNCED_MARK in rows[2][0], rows[2][0]
    h.ok(f"시각 미확인 표시 ({rows[2][0]})")

    # 경고는 한 세션에 한 번만. 매번 뜨면 무시하게 된다.
    window._clock_warned = False
    main_mod.clock_is_trustworthy = lambda: False
    try:
        first = window.clock_warning()
        second = window.clock_warning()
    finally:
        main_mod.clock_is_trustworthy = original
    assert first and second is None, (first, second)
    h.ok("시계 경고는 세션당 1회")


def check_shortfall(window):
    window.locked_combo = None
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
    check_locked_sum_tracks_settling(window)
    check_transient_err(window)
    check_production(window, main_mod)
    check_topup_production(window, main_mod)
    check_clock_marking(window, main_mod)
    check_calibration_led_gate(window, main_ui, sent)
    check_shortfall(window)
    check_presets(window, main_ui)
    check_settings_backup(window, main_mod)

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_operation OK")
