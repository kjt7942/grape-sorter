"""800x480 화면 안에 모든 요소가 들어가는지, 오버레이가 스스로 닫히는지."""
import harness as h


def main():
    app, main_mod, main_ui = h.boot()
    window, sent = h.new_app(main_mod, connected=False)

    # 설정 행이 5개(제품/목표/허용오차/최소/최대)라 세로가 빠듯하다.
    right_panel = window.setting_max.parentWidget()
    need = right_panel.minimumSizeHint().height()
    print(f"  우측 패널 최소 높이 {need}px / 창 {window.height()}px")
    assert need <= 460, f"우측 패널이 화면을 넘음: {need}px"
    h.ok("우측 패널이 800x480 안에 들어감")

    # 다이얼로그 3종은 메인화면과 같은 크기여야 정확히 덮는다.
    for cls in (main_ui.PresetDialog, main_ui.ScaleCheckDialog):
        dialog = cls(window, is_dark_mode=True)
        assert dialog.size().width() == 800 and dialog.size().height() == 480, dialog.size()
        dialog.close()
    cal = main_ui.CalibrationDialog(window, is_dark_mode=True, ref_weight=430)
    assert cal.size().width() == 800 and cal.size().height() == 480
    cal.close()
    h.ok("다이얼로그 크기가 메인화면과 일치")

    # 터치 전용 기기라 오버레이가 걸린 채 남으면 빠져나올 방법이 없다.
    window.show_message("테스트", 200)
    assert window.overlay_label.isVisible()
    h.wait(600)
    assert not window.overlay_label.isVisible(), "타임아웃 뒤에도 오버레이가 남음"
    h.ok("오버레이가 시한이 지나면 스스로 닫힘")

    # 화면을 눌러도 닫혀야 한다 (최후의 탈출구).
    window.show_message("테스트", None)
    assert window.overlay_label.isVisible()
    window.hide_message()
    assert not window.overlay_label.isVisible()
    h.ok("오버레이 수동 해제")

    # 두 테마 모두 그려지는지
    for _ in range(2):
        window.toggle_theme()
        window.on_data_received([500] * 12)
    h.ok("밝은/어두운 테마 전환")

    h.teardown(window)


if __name__ == "__main__":
    main()
    print("test_layout OK")
