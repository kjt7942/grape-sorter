#include <string.h> 

// --- 핀 설정 ---
const int LOADCELL_COUNT = 12;
const int SCK_PIN = 2; 
const int DT_PINS[LOADCELL_COUNT] = {22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33}; 
// --- 테스트중 샘플 핀 설정 ---
const int LED_PINS[LOADCELL_COUNT] = {3, 4, 5, 6, 36, 37, 9, 10, 11, 12, 34, 35};

// --- 영점 및 '개별' 보정 설정 ---
float calFactors[LOADCELL_COUNT] = {
  424.0, 425.5, 423.8, 424.2, 426.0, 422.9, 
  424.1, 425.0, 423.5, 424.8, 425.2, 424.0   
}; 
long offsets[LOADCELL_COUNT] = {0}; 

// --- 필터 설정 (슬라이딩 윈도우) ---
const int SAMPLE_SIZE = 5; 
long weightBuffer[LOADCELL_COUNT][SAMPLE_SIZE] = {0};

// --- 산업용 고정 통신 버퍼 ---
const int MAX_CMD_LEN = 64;
char cmdBuffer[MAX_CMD_LEN];
int cmdIndex = 0;
bool cmdReady = false;

// --- 🌟 5진 아웃 & 상태 저장 변수 🌟 ---
bool ledCommandState[LOADCELL_COUNT] = {false}; 
unsigned long lastBlinkTime = 0;                
bool blinkState = false;                        

int errorCount[LOADCELL_COUNT] = {0};       // 채널별 에러 누적 카운터 (5진 아웃용)
bool isIsolated[LOADCELL_COUNT] = {false};  // 격리(블랙리스트) 상태 

// --- 함수 선언 ---
void readSensors(long* targetArray, bool* successArray);
void performTare();

void setup() {
  delay(1000); // 🌟 필수 추가: 전원 인가 후 로드셀이 깨어날 때까지 1초 대기
  Serial.begin(115200);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);
  
  for(int i = 0; i < LOADCELL_COUNT; i++) {
    // 🚨 핵심 수술: 아두이노 내부에 5V 저항을 강제로 연결하여 노이즈 원천 차단!
    pinMode(DT_PINS[i], INPUT_PULLUP); 
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }

  performTare();
  Serial.println("--- 24시간 무중단 모드 (5진 아웃 격리 시스템 가동 중) ---");
}

void loop() {
  // 1. 라즈베리파이 명령 수신
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      cmdBuffer[cmdIndex] = '\0'; 
      cmdReady = true;
      break; 
    } 
    else if (c != '\r' && cmdIndex < MAX_CMD_LEN - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // 2. 명령어 파싱
  if (cmdReady) {
    char *startPtr = strchr(cmdBuffer, '<'); 
    char *endPtr = strchr(cmdBuffer, '>');   

    if (startPtr != NULL && endPtr != NULL && startPtr < endPtr) {
      *endPtr = '\0'; 
      char *innerCmd = startPtr + 1; 

      if (strcmp(innerCmd, "TARE") == 0) {
        performTare();
      } 
      else {
        for (int i = 0; i < LOADCELL_COUNT; i++) ledCommandState[i] = false;
        
        char *token = strtok(innerCmd, ", ");
        while (token != NULL) {
          int ledNum = atoi(token); 
          if (ledNum >= 1 && ledNum <= LOADCELL_COUNT) {
            ledCommandState[ledNum - 1] = true;
          }
          token = strtok(NULL, ", "); 
        }
      }
    }
    cmdIndex = 0;
    cmdReady = false;
  }

  // 3. 센서 데이터 동시 읽기 및 5진 아웃 판정
  long rawValues[LOADCELL_COUNT] = {0};
  bool successArray[LOADCELL_COUNT] = {false};
  
  readSensors(rawValues, successArray);

  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (isIsolated[i]) {
      continue;
    }

    if (successArray[i]) {
      errorCount[i] = 0; 
    } else {
      errorCount[i]++;
      if (errorCount[i] >= 5) {
        isIsolated[i] = true; 
      }
    }
  }

  // 4. 라즈베리파이로 데이터 송신
  Serial.print("<");
  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (!isIsolated[i] && successArray[i]) {
      float weight = (rawValues[i] - offsets[i]) / calFactors[i];

      for (int j = 0; j < SAMPLE_SIZE - 1; j++) {
        weightBuffer[i][j] = weightBuffer[i][j + 1];
      }
      weightBuffer[i][SAMPLE_SIZE - 1] = (long)weight;

      long temp[SAMPLE_SIZE];
      for (int k = 0; k < SAMPLE_SIZE; k++) temp[k] = weightBuffer[i][k];
      for (int m = 0; m < SAMPLE_SIZE - 1; m++) {
        for (int n = m + 1; n < SAMPLE_SIZE; n++) {
          if (temp[m] > temp[n]) {
            long t = temp[m]; temp[m] = temp[n]; temp[n] = t;
          }
        }
      }

      long filteredWeight = (temp[1] + temp[2] + temp[3]) / 3;
      if (filteredWeight > -2 && filteredWeight < 2) filteredWeight = 0;

      Serial.print(filteredWeight);
    } else {
      Serial.print("ERR");
    }
    
    if (i < LOADCELL_COUNT - 1) Serial.print(", ");
  }
  Serial.println(">");

  // 5. LED 최종 출력 제어 (비상 깜빡임 vs 정상 명령)
  if (millis() - lastBlinkTime >= 100) { 
    blinkState = !blinkState;
    lastBlinkTime = millis();
  }

  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (isIsolated[i]) {
      digitalWrite(LED_PINS[i], blinkState ? HIGH : LOW);
    } else {
      digitalWrite(LED_PINS[i], ledCommandState[i] ? HIGH : LOW);
    }
  }

  delay(50); 
}

// --- 🌟 개선된 영점 조절 (격리 해제 기능 포함) 🌟 ---
void performTare() {
  Serial.println("\n[SYSTEM] 영점 조절(TARE) 및 에러 초기화 시작...");
  
  for(int i = 0; i < LOADCELL_COUNT; i++) {
    errorCount[i] = 0;
    isIsolated[i] = false;
  }

  long sum[LOADCELL_COUNT] = {0};
  int validReads[LOADCELL_COUNT] = {0};
  
  for(int k = 0; k < 10; k++) {
    long rawValues[LOADCELL_COUNT] = {0};
    bool successArray[LOADCELL_COUNT] = {false};
    
    readSensors(rawValues, successArray);

    for(int i = 0; i < LOADCELL_COUNT; i++) {
      if (successArray[i]) {
        sum[i] += rawValues[i];
        validReads[i]++;
      }
    }
    delay(50);
  }
  
  for(int i = 0; i < LOADCELL_COUNT; i++) {
    if(validReads[i] > 0) offsets[i] = sum[i] / validReads[i];
    for(int j = 0; j < SAMPLE_SIZE; j++) weightBuffer[i][j] = 0;
  }
  Serial.println("[SYSTEM] 영점 조절 완료! 정상 가동 재개.");
}

// --- 🌟 개선된 초고속 동시 읽기 함수 (60us 수면 버그 원천 차단) 🌟 ---
void readSensors(long* targetArray, bool* successArray) {
  unsigned long startTime = millis();
  bool allReady = false;
  
  // 센서들이 준비될 때까지 대기
  while (millis() - startTime < 150) { 
    allReady = true;
    for (int i = 0; i < LOADCELL_COUNT; i++) {
      if (!isIsolated[i] && digitalRead(DT_PINS[i]) == HIGH) { 
        allReady = false; 
        break; 
      }
    }
    if (allReady) break;
  }

  // 성공적으로 준비된 녀석들 기록
  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (!isIsolated[i] && digitalRead(DT_PINS[i]) == LOW) {
      successArray[i] = true;
    } else {
      successArray[i] = false;
    }
  }

  long values[LOADCELL_COUNT] = {0};
  
  // 24번의 펄스를 발생시켜 데이터를 동시에 빨아들임
  for (int i = 0; i < 24; i++) {
    digitalWrite(SCK_PIN, HIGH); 
    delayMicroseconds(1);       // 1. 아주 짧게 전기를 쏜다 (1마이크로초)
    digitalWrite(SCK_PIN, LOW); // 2. 🚨 즉시 끈다! (수면 모드 절대 진입 불가)

    // 3. 전기가 꺼진 안전한 상태에서 느긋하게 12개의 핀을 다 읽는다!
    int b0  = digitalRead(DT_PINS[0]);
    int b1  = digitalRead(DT_PINS[1]);
    int b2  = digitalRead(DT_PINS[2]);
    int b3  = digitalRead(DT_PINS[3]);
    int b4  = digitalRead(DT_PINS[4]);
    int b5  = digitalRead(DT_PINS[5]);
    int b6  = digitalRead(DT_PINS[6]);
    int b7  = digitalRead(DT_PINS[7]);
    int b8  = digitalRead(DT_PINS[8]);
    int b9  = digitalRead(DT_PINS[9]);
    int b10 = digitalRead(DT_PINS[10]);
    int b11 = digitalRead(DT_PINS[11]);

    // 읽은 비트를 합친다
    values[0]  = (values[0]  << 1) | b0;
    values[1]  = (values[1]  << 1) | b1;
    values[2]  = (values[2]  << 1) | b2;
    values[3]  = (values[3]  << 1) | b3;
    values[4]  = (values[4]  << 1) | b4;
    values[5]  = (values[5]  << 1) | b5;
    values[6]  = (values[6]  << 1) | b6;
    values[7]  = (values[7]  << 1) | b7;
    values[8]  = (values[8]  << 1) | b8;
    values[9]  = (values[9]  << 1) | b9;
    values[10] = (values[10] << 1) | b10;
    values[11] = (values[11] << 1) | b11;
  }
  
  // 마지막 25번째 펄스 (다음 데이터를 위해 필수)
  digitalWrite(SCK_PIN, HIGH); delayMicroseconds(1);
  digitalWrite(SCK_PIN, LOW); delayMicroseconds(1);

  // 음수 처리 등 최종 마무리
  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (successArray[i]) {
      if (values[i] & 0x800000) values[i] |= 0xFF000000; 
      targetArray[i] = values[i];
    }
  }
}