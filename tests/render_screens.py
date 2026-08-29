"""모든 화면을 PNG 로 떨궈 눈으로 확인한다. 판정은 하지 않는다.

라즈베리파이 없이 화면 변경을 검토할 때 쓴다. 결과는 tests/_screens/ 에 쌓인다.
"""
import harness as h

WEIGHTS = [700, 680, 720, 500, 900, h.ERR, 640, 0, 830, 760, 0, 590]


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod, connected=False)
    window.resize(800, 480)

    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 3, 4, 50
    window.on_data_received(WEIGHTS)
    h.shot(window, "01_main_dark.png")

    window.toggle_theme()
    window.on_data_received(WEIGHTS)
    h.shot(window, "02_main_light.png")
    window.toggle_theme()

    window.toggle_topup_mode()
    window.on_data_received(WEIGHTS)
    h.shot(window, "03_topup.png")
    window.toggle_topup_mode()

    window.show_message("영점 조정 중입니다.\n저울에서 손을 떼세요.")
    h.shot(window, "04_overlay.png")
    window.hide_message()

    window.locked_combo = None
    window.target_weight = 9000
    window.on_data_received(WEIGHTS)
    h.shot(window, "05_combo_failed.png")
    window.target_weight = 2050

    window.update_sim_mode_display(True, True)
    window.on_data_received([h.ERR] * 12)
    h.shot(window, "06_disconnected.png")
    window.update_sim_mode_display(False, False)

    preset = main_ui.PresetDialog(window, is_dark_mode=True)
    for i, button in enumerate(preset.preset_buttons):
        window.refresh_preset_button(button, i)
    preset.show()
    h.shot(preset, "07_preset.png")
    preset.close()

    window.raw_weights = WEIGHTS
    window.cal_dialog = main_ui.CalibrationDialog(window, is_dark_mode=True,
                                                  ref_weight=window.cal_ref_weight)
    window.cal_dialog.show()
    window.cal_dialog.set_ready()
    window.cal_waiting_tare = False
    window.cal_target_idx = 0
    window.update_cal_dialog_ui()
    h.shot(window.cal_dialog, "08_calibration.png")
    window.cal_dialog.close()
    window.cal_dialog = None

    window.scale_check_dialog = main_ui.ScaleCheckDialog(window, is_dark_mode=True)
    window.scale_check_dialog.show()
    window.expected_firmware_version = "abc1234"
    window.on_data_received(WEIGHTS)
    window.on_firmware_version_received("abc1234")
    h.shot(window.scale_check_dialog, "09_scale_check.png")
    window.scale_check_dialog.close()
    window.scale_check_dialog = None

    h.teardown(window)
    print(f"  화면 이미지: {h.SCREEN_DIR}")


if __name__ == "__main__":
    main()
    print("render_screens OK")
