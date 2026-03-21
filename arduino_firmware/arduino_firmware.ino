#include <string.h> 

// --- 핀 설정 ---
const int LOADCELL_COUNT = 12;
const int SCK_PIN = 2; 
const int DT_PINS[LOADCELL_COUNT] = {22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33}; 
const int LED_PINS[LOADCELL_COUNT] = {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}; 

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
  Serial.begin(115200);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);
  
  for(int i = 0; i < LOADCELL_COUNT; i++) {
    pinMode(DT_PINS[i], INPUT);
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
      // 이미 격리된 센서는 무시 (ERR 출력만 유지)
      continue;
    }

    if (successArray[i]) {
      errorCount[i] = 0; // 정상 통신 시 카운터 즉시 초기화
    } else {
      errorCount[i]++;
      if (errorCount[i] >= 5) {
        isIsolated[i] = true; // 5번 연속 실패 시 즉시 블랙리스트 격리!
        // 격리되는 순간 전체 속도는 다시 정상으로 빨라집니다.
      }
    }
  }

  // 4. 라즈베리파이로 데이터 송신
  Serial.print("<");
  for (int i = 0; i < LOADCELL_COUNT; i++) {
    // 격리되지 않았고, 이번 턴에 성공한 데이터만 출력
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
      // 5진 아웃으로 격리된 채널은 무조건 비상 깜빡임!
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
  
  // TARE 명령을 받으면 모든 에러 카운트와 격리 상태를 전면 초기화합니다. (부활)
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

// --- 🌟 개별 성공 여부를 추적하는 동시 읽기 함수 🌟 ---
void readSensors(long* targetArray, bool* successArray) {
  unsigned long startTime = millis();
  bool allReady = false;
  
  // 격리되지 않은(살아있는) 센서들만 준비되었는지 확인
  while (millis() - startTime < 100) {
    allReady = true;
    for (int i = 0; i < LOADCELL_COUNT; i++) {
      if (!isIsolated[i] && digitalRead(DT_PINS[i]) == HIGH) { 
        allReady = false; 
        break; 
      }
    }
    if (allReady) break;
  }

  // 누가 성공적으로 준비되었는지 개별적으로 기록
  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (!isIsolated[i] && digitalRead(DT_PINS[i]) == LOW) {
      successArray[i] = true;
    } else {
      successArray[i] = false;
    }
  }

  // 살아있는 센서들의 싱크를 맞추기 위해 무조건 25펄스는 발생시킴
  long values[LOADCELL_COUNT] = {0};
  for (int i = 0; i < 24; i++) {
    digitalWrite(SCK_PIN, HIGH); delayMicroseconds(1);
    for (int j = 0; j < LOADCELL_COUNT; j++) {
      values[j] = (values[j] << 1) | digitalRead(DT_PINS[j]);
    }
    digitalWrite(SCK_PIN, LOW); delayMicroseconds(1);
  }
  
  digitalWrite(SCK_PIN, HIGH); delayMicroseconds(1);
  digitalWrite(SCK_PIN, LOW); delayMicroseconds(1);

  for (int i = 0; i < LOADCELL_COUNT; i++) {
    if (successArray[i]) {
      if (values[i] & 0x800000) values[i] |= 0xFF000000; 
      targetArray[i] = values[i];
    }
  }
}