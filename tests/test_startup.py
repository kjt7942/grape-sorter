"""시작 준비 절차(LED 안내 -> 자동 영점 -> 사용 가능)와 보정 화면 흐름.

라즈베리파이와 아두이노는 전원이 분리되어 있어 켜는 순서가 정해져 있지 않다.
어느 쪽을 먼저 켜도 USB 연결이 성립하는 순간 이 절차가 돌아야 한다.
"""
import harness as h


def check_sequence(window, sent):
    sent.clear()
    window.begin_startup("테스트")
    assert window.startup_active
    assert "준비" in window.overlay_label.text(), window.overlay_label.text()

    # 준비 중에는 조합 연산이 LED 안내를 덮으면 안 된다.
    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.on_data_received([1000, 1050] + [0] * 10)

    h.wait(4000)

    all_on = "<" + ",".join(str(i) for i in range(1, 13)) + ">"
    assert sent[0] == all_on, sent[0]
    assert "<1>" in sent and "<12>" in sent, "순차 훑기가 없음"
    assert "<TARE>" in sent, sent[-5:]
    assert sent.index("<1>") < sent.index("<12>") < sent.index("<TARE>"), \
        "순차 훑기가 영점보다 늦음 (영점 중에는 LED 를 못 움직인다)"
    assert "영점" in window.overlay_label.text()
    h.ok(f"안내 {len(sent)}프레임 -> 순차 1~12 -> 영점")

    window.on_tare_offsets([250] * 12)
    window.on_system_message("TARE_DONE")
    h.wait(1500)
    assert not window.startup_active, "마무리 후에도 준비 상태"
    assert window.settings_data.get("tare_offsets") == [250] * 12
    h.ok("영점 완료 후 사용 가능 상태로 복귀")


def check_bad_tare(window):
    """접시에 물건이 올려진 채 영점을 잡으면 조용히 미달 박스가 나간다."""
    base = [250] * 12
    window.settings_data["tare_offsets"] = base

    dirty = list(base)
    dirty[2] = 900
    warning = window.check_tare_offsets(dirty)
    assert warning and "3번" in warning, warning
    h.ok("접시 위 이물 감지")

    # 배선을 늘리거나 줄이는 것은 이물이 아니다. 미연결 채널은 오프셋 0으로 온다.
    partial = [250, 250, 0, 0, 0, 0, 250, 250, 0, 0, 0, 0]
    window.settings_data["tare_offsets"] = partial
    assert window.check_tare_offsets([250] * 12) is None, "허브보드 추가를 이물로 오탐"
    assert window.check_tare_offsets(partial) is None, "허브보드 제거를 이물로 오탐"
    h.ok("허브보드 증설/제거는 오탐하지 않음")


def check_arduino_restart(window):
    """운전 중 아두이노가 재부팅되면 스스로 영점을 다시 잡는다.

    그때 접시에 포도가 있었을 수 있으므로 준비 절차를 다시 돌려 확인해야 한다.
    요청하지 않았는데 도착한 [VER] 이 그 신호다.
    """
    window.hide_message()
    window.startup_active = False
    window.scale_check_dialog = None
    window.on_firmware_version_received("abc1234")
    assert window.startup_active, "아두이노 재시작을 감지하지 못함"
    window.finish_startup(None)
    h.ok("예고 없는 [VER] 을 아두이노 재시작으로 감지")


def check_calibration(window, main_ui, sent):
    """보정 화면은 들어갈 때 영점을 먼저 잡고, 끝날 때까지 조작을 막는다."""
    assert window.cal_ref_weight == 430, window.cal_ref_weight
    h.ok("기본 분동 무게 430g")

    sent.clear()
    state = {}

    def while_busy():
        dialog = window.cal_dialog
        state["busy_locked"] = not dialog.btn_apply.isEnabled()
        state["tare_sent"] = "<TARE>" in sent
        h.shot(dialog, "cal_busy.png")

    def after_tare():
        dialog = window.cal_dialog
        state["ready"] = dialog.btn_apply.isEnabled()
        state["progress"] = dialog.lbl_progress.text()
        h.shot(dialog, "cal_ready.png")

    from PyQt5.QtCore import QTimer
    QTimer.singleShot(300, while_busy)
    QTimer.singleShot(600, lambda: window.on_system_message("TARE_DONE"))
    QTimer.singleShot(1200, after_tare)
    QTimer.singleShot(2200, lambda: window.cal_dialog and window.cal_dialog.accept())
    window.show_calibration_dialog()

    assert state.get("busy_locked"), "영점 전인데 보정 적용이 가능함"
    assert state.get("tare_sent"), "보정 진입 시 영점을 안 보냄"
    assert state.get("ready"), "영점이 끝났는데 버튼이 잠겨 있음"
    h.ok(f"보정 진입 시 자동 영점, 완료 전까지 조작 차단 ({state['progress']})")


def check_calibration_guard(window, main_ui):
    """분동을 안 올렸거나 다른 저울에 올렸으면 배율이 터무니없이 나온다."""
    window.cal_dialog = main_ui.CalibrationDialog(window, is_dark_mode=True, ref_weight=430)
    window.cal_dialog.show()
    window.cal_dialog.set_ready()
    window.cal_waiting_tare = False
    window.cal_target_idx = 0
    window.cal_multipliers[0] = 1.0

    window.raw_history.clear()
    for _ in range(5):
        window.raw_history.append([50] + [0] * 11)     # 분동 없이 50g
    window.raw_weights = [50] + [0] * 11
    window.apply_current_calibration()
    assert window.cal_multipliers[0] == 1.0, "8.6배 배율이 저장됨"
    assert "비정상" in window.cal_dialog.lbl_guide.text()
    h.ok("비정상 배율 거부")

    window.raw_history.clear()
    for _ in range(5):
        window.raw_history.append([420] + [0] * 11)
    window.raw_weights = [420] + [0] * 11
    window.apply_current_calibration()
    assert abs(window.cal_multipliers[0] - 430 / 420) < 1e-6, window.cal_multipliers[0]
    h.ok(f"정상 범위 보정 적용 (배율 {window.cal_multipliers[0]:.4f})")

    window.cal_target_idx = 0
    window.reset_current_calibration()
    assert window.cal_multipliers[0] == 1.0
    h.ok("보정 초기화")

    window.cal_dialog.close()
    window.cal_dialog = None


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod)

    check_sequence(window, sent)
    check_bad_tare(window)
    check_arduino_restart(window)
    check_calibration(window, main_ui, sent)
    check_calibration_guard(window, main_ui)

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_startup OK")
