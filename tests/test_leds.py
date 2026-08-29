"""조합이 성립하면 아두이노로 LED 신호가 나가는지, 그리고 중복 억제가
엉뚱한 순간에 신호를 삼키지 않는지.

LED 는 조작자가 어느 저울을 집을지 판단하는 유일한 표시다. 신호가 하나라도
누락되면 엉뚱한 저울을 집게 된다.
"""
import harness as h


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod)

    window.target_weight, window.min_comb, window.max_comb, window.tolerance = 2050, 2, 2, 50
    window.current_preset_index = None

    A = h.weights(ch1=1000, ch2=1050)          # 1+2 = 2050 정확
    B = h.weights(ch3=1020, ch4=1030)          # 3+4 = 2050
    for row in (A, B):
        for i in range(12):
            if row[i] == h.ERR:
                row[i] = 0

    sent.clear()
    window.on_data_received(A)
    assert sent == ["<1,2>"], sent
    h.ok("조합 성립 -> LED 점등 신호")

    sent.clear()
    for _ in range(20):
        window.on_data_received(A)
    assert sent == [], f"같은 조합인데 {len(sent)}회 재전송"
    h.ok("같은 조합 반복 시 재전송 없음 (아두이노가 상태 유지)")

    sent.clear()
    window.locked_combo = None
    window.on_data_received(B)
    assert sent == ["<3,4>"], sent
    h.ok("조합이 바뀌면 새 신호")

    sent.clear()
    window.locked_combo = None
    window.target_weight = 9000
    window.on_data_received(B)
    assert sent == ["<>"], sent
    window.target_weight = 2050
    h.ok("조합 실패 -> 전체 소등")

    # 저울점검 중에는 수동 LED 가 우선. 조합 신호가 덮으면 점검 기능이 무의미해진다.
    window.locked_combo = None
    window.on_data_received(A)
    window.scale_check_dialog = main_ui.ScaleCheckDialog(window, is_dark_mode=True)
    window.scale_check_dialog.show()
    sent.clear()
    window.toggle_scale_check_led(6, True)
    for _ in range(15):
        window.locked_combo = None
        window.on_data_received(A)
    assert sent == ["<7>"], f"조합 LED 가 수동 점등을 덮어씀: {sent}"
    h.ok("저울점검 중 수동 LED 를 조합이 덮지 않음")

    window.scale_check_dialog.close()
    window.scale_check_dialog = None
    window._last_led = None
    window.serial_thread.send_signal([])
    sent.clear()
    window.locked_combo = None
    window.on_data_received(A)
    assert sent == ["<1,2>"], sent
    h.ok("점검 종료 후 조합이 LED 제어권 회복")

    # 재연결이면 아두이노가 리셋되어 LED 가 다 꺼진다. 캐시를 비워 다시 보내야 한다.
    sent.clear()
    window.update_sim_mode_display(False, False)
    window.locked_combo = None
    window.on_data_received(A)
    assert sent == ["<1,2>"], f"재연결 후 LED 가 꺼진 채로 남음: {sent}"
    h.ok("재연결 시 LED 재전송")

    sent.clear()
    window.on_data_received([1000] + [0] * 11)
    assert sent == ["<1>"], sent
    h.ok("저울을 빼가면 남은 저울만 점등")

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_leds OK")
