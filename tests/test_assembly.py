"""조립 단계별 동작.

허브보드 1장(저울 1,2,7,8)만 물린 상태에서도 쓸 수 있어야 하고,
보드 2·3을 마저 달았을 때 코드 수정 없이 12채널로 넘어가야 한다.
"""
import csv
import time

import harness as h

PART = h.weights(ch1=520, ch2=540, ch7=500, ch8=490)
FULL = [520, 540, 700, 680, 720, 660, 500, 490, 830, 760, 590, 640]


def check_partial(window, sent, main_ui):
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 3, 4, 50
    window.current_preset_index = None
    window.locked_combo = None
    window._last_led = None
    sent.clear()
    window.on_data_received(PART)

    labels = [window.tray_weight_labels[i].text() for i in range(12)]
    assert labels[0] == "520 g" and labels[2] == "에러(ERR)", labels
    assert window.sum_val_lbl.text() == "2,050 g", window.sum_val_lbl.text()
    assert sorted(window.original_locked_indices) == [1, 2, 7, 8]
    assert sent == ["<1,2,7,8>"], sent
    h.ok("미연결 8채널은 ERR, 연결된 4채널로 조합")

    # 보유 저울보다 큰 최대조합을 넣어도 터지지 않아야 한다.
    window.max_comb = 12
    window.locked_combo = None
    window.on_data_received(PART)
    assert window.original_locked_indices, "최대조합 12에서 실패"
    window.max_comb = 4
    h.ok("최대조합이 보유 저울 수보다 커도 안전")

    # 하필 박스무게 채널(1,2,7,8)이 유일하게 연결된 채널이라 보태기는 못 쓴다.
    window.locked_combo = None
    window.toggle_topup_mode()
    window.on_data_received(PART)
    assert window.combo_val.text() == "조합실패", \
        "보드 1장만으로 보태기가 되면 안 됨 (박스 채널과 겹침)"
    window.toggle_topup_mode()
    h.ok("보태기는 보드 1장 상태에서 사용 불가 (예상된 제약)")

    window.scale_check_dialog = main_ui.ScaleCheckDialog(window, is_dark_mode=True)
    window.scale_check_dialog.show()
    window.on_data_received(PART)
    assert window.scale_check_dialog.lbl_summary.text() == "정상 4 / 12"
    assert window.scale_check_dialog.channel_labels[2].text() == "연결안됨 (ERR)"
    h.shot(window.scale_check_dialog, "assembly_scalecheck.png")
    window.scale_check_dialog.close()
    window.scale_check_dialog = None
    h.ok("저울점검이 정상 4 / 12 로 표시")


def check_production_partial(window, main_mod):
    window.locked_combo = None
    window.on_data_received(PART)
    taken = list(window.original_locked_indices)
    emptied = list(PART)
    for scale in taken:
        emptied[scale - 1] = 0
    window.on_data_received(emptied)
    with open(main_mod.PRODUCTION_FILE, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) >= 2, rows
    h.ok(f"4채널 상태에서도 실적 기록 ({rows[-1][3]}g, 저울 {rows[-1][6]})")


def check_full(window, sent, main_ui):
    window.locked_combo = None
    window._last_led = None
    window.rejected_combos.clear()
    window.target_weight, window.min_comb, window.max_comb = 2050, 3, 4
    sent.clear()
    window.on_data_received(FULL)

    err_count = sum(1 for i in range(12)
                    if window.tray_weight_labels[i].text() == "에러(ERR)")
    assert err_count == 0, err_count
    assert window.original_locked_indices, "12채널에서 조합 실패"
    total = sum(window.weights[i - 1] for i in window.original_locked_indices)
    assert total >= 2050
    h.ok(f"12채널 전부 인식, 조합 {sorted(window.original_locked_indices)} = {total}g")

    # 보드 증설 후 첫 영점에 오탐이 없어야 한다.
    window.settings_data["tare_offsets"] = [250, 260, 0, 0, 0, 0, 245, 255, 0, 0, 0, 0]
    warning = window.check_tare_offsets([250, 260, 240, 255, 248, 252,
                                         245, 255, 250, 249, 251, 247])
    assert warning is None, f"배선 추가를 이물로 오탐: {warning}"
    h.ok("보드 증설 후 첫 영점에 오탐 없음")

    # 보태기가 살아난다. 박스가 목표에 미달해야 보탤 여지가 있다.
    topup = [350, 360, 700, 680, 720, 660, 340, 350, 830, 760, 590, 640]
    window.locked_combo = None
    window.toggle_topup_mode()
    window.on_data_received(topup)
    assert window.combo_val.text() != "조합실패", "12채널인데 보태기 실패"
    assert not (set(window.original_locked_indices) & {1, 2, 7, 8}), \
        "박스 채널을 보태기 조합에 씀"
    h.ok(f"보태기 동작 (박스 {window.sum_val_lbl.text()}, 보탤 저울 "
         f"{sorted(window.original_locked_indices)})")
    window.toggle_topup_mode()

    # 최대조합을 12까지 열어도 라즈베리파이 3B 가 버티는지.
    window.min_comb, window.max_comb = 1, 12
    start = time.perf_counter()
    for _ in range(20):
        window.locked_combo = None
        window.on_data_received(FULL)
    per_call = (time.perf_counter() - start) / 20 * 1000
    assert per_call < 200, f"조합 연산이 {per_call:.0f}ms"
    h.ok(f"최소1~최대12 조합 연산 1회 {per_call:.1f}ms")
    window.min_comb, window.max_comb = 3, 4

    window.scale_check_dialog = main_ui.ScaleCheckDialog(window, is_dark_mode=True)
    window.scale_check_dialog.show()
    window.on_data_received(FULL)
    assert window.scale_check_dialog.lbl_summary.text() == "정상 12 / 12"
    window.scale_check_dialog.close()
    window.scale_check_dialog = None
    h.ok("저울점검 정상 12 / 12")


def check_uncalibrated_marker(window, main_ui):
    """새로 단 채널은 배율 1.0 이라 '미보정' 으로 떠서 빠뜨린 곳이 보여야 한다."""
    window.cal_multipliers = [1.02, 1.01, 1.0, 1.0, 1.0, 1.0,
                              0.99, 1.03, 1.0, 1.0, 1.0, 1.0]
    window.cal_dialog = main_ui.CalibrationDialog(window, is_dark_mode=True, ref_weight=430)
    window.cal_dialog.show()
    window.cal_dialog.set_ready()
    window.cal_waiting_tare = False
    window.cal_target_idx = 2
    window.raw_weights = FULL
    window.update_cal_dialog_ui()

    states = [window.cal_dialog.cal_states[i].text() for i in range(12)]
    assert states[0].startswith("배율"), states
    assert states[2] == "미보정", states
    h.shot(window.cal_dialog, "assembly_calibration.png")
    window.cal_dialog.close()
    window.cal_dialog = None
    h.ok("보정한 채널과 미보정 채널이 구분됨")


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod)

    print(" [허브보드 1장: 저울 1,2,7,8]")
    check_partial(window, sent, main_ui)
    check_production_partial(window, main_mod)

    print(" [보드 2,3 조립 완료: 12채널]")
    check_full(window, sent, main_ui)
    check_uncalibrated_marker(window, main_ui)

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_assembly OK")
