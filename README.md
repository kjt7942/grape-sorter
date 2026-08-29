# grape-sorter

꿀송이농장 포도선별기.

라즈베리파이 + 7인치 터치스크린(800x480)에서 도는 선별 제어 프로그램입니다.
아두이노 메가 2560에 붙은 12채널 로드셀(HX711)에서 무게를 받아, 목표무게에 가장
가까운 조합을 찾아 해당 저울의 LED를 켭니다.

```
[로드셀 x12] --HX711--> [Arduino Mega 2560] --USB 시리얼 115200--> [Raspberry Pi]
                                 ^                                        |
                                 +------------ LED 점등 명령 -------------+
```

## 설치 (라즈베리파이)

```bash
git clone https://github.com/kjt7942/grape-sorter.git
cd grape-sorter
bash setup_kiosk.sh          # X11, PyQt5, PySerial, 자동시작, sudo 권한
sudo bash setup_boot_screen.sh   # (선택) 부팅 스플래시 화면
```

이후 `sudo raspi-config` 에서 Console Autologin 을 켜고 재부팅하면 전체화면으로 자동 실행됩니다.
자세한 절차와 트러블슈팅은 [dev_environment_spec.md](dev_environment_spec.md) 를 보세요.

## 개발 환경에서 실행

아두이노가 없으면 시뮬레이션 모드로 뜹니다. 저울 카드를 클릭해 무게를 만들고 조합 동작을 확인할 수 있습니다.

```bash
python3 main.py
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `main.py` | 시리얼 통신, 조합 연산, 설정/실적 저장, OTA |
| `main_ui.py` | PyQt5 화면 정의 (메인 + 다이얼로그 3종) |
| `arduino_firmware/` | 아두이노 메가 펌웨어 (로드셀 읽기, LED, 영점) |
| `test_sorter.py` | 조합 로직 자체 점검. PyQt5 없이 실행되며 OTA 검증 관문으로도 쓰임 |
| `tests/` | 화면·시작절차·조립단계별 테스트. [tests/README.md](tests/README.md) 참고 |
| `setup_kiosk.sh` | 라즈베리파이 키오스크 환경 구축 |
| `setup_boot_screen.sh` | 부팅 스플래시(Plymouth) 설정 |

## 실행 중 생기는 파일 (git 추적 안 함)

| 파일 | 내용 |
|---|---|
| `settings.json` | 프리셋 A~H, 저울 보정값, 마지막 설정 |
| `settings.backup.json` | 위 파일의 자동 백업 |
| `production.csv` | 박스 완성 실적 (시각, 목표/실제 무게, 사용 저울) |
| `sorter.log` | 실행 로그 (1MB 회전, 3개 보관) |

## 테스트

라즈베리파이나 아두이노 없이 개발 PC에서 전부 돕니다.

```bash
python3 tests/run_all.py         # 전체 (7개 스위트)
python3 tests/render_screens.py  # 모든 화면을 PNG 로 저장
python3 test_sorter.py           # 조합 로직만 (OTA 관문과 동일)
```

무엇을 지키는지는 [tests/README.md](tests/README.md) 에 정리돼 있습니다.
