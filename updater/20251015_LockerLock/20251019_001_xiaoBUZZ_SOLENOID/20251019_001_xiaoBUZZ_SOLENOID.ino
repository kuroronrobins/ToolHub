// =====================
// XIAO (SAMD21) テスト用スケッチ
//  - A0/A1: 反相 4kHz ブザー（差動駆動）
//  - D3   : ソレノイド駆動用信号（パルス）
// =====================

// --- 接続ピン定義 ---
#define BUZZER_POS_PIN   A0   // ブザーの片側（正相）
#define BUZZER_NEG_PIN   A1   // ブザーの片側（逆相）
#define SOLENOID_SIG_PIN 3    // D3（ソレノイド駆動信号）

// --- ブザー設定 ---
#define BUZZER_FREQ_HZ   4000UL         // ブザー周波数
#define BUZZER_ON_MS     2000UL         // 鳴動時間
#define BUZZER_OFF_MS    1000UL         // 無音時間

// --- ソレノイド信号設定（例：3秒毎に100msパルス） ---
#define SOLENOID_PERIOD_MS 3000UL
#define SOLENOID_PULSE_MS   100UL

// 内部タイマ（micros/ millis）
static unsigned long halfPeriod_us;      // ブザー用：半周期(μs)
static unsigned long nextToggle_us = 0;  // ブザー位相反転の次時刻(μs)
static bool buzzerPhase = false;         // 位相フラグ（false/trueで反転）

static unsigned long buzzerStateChange_ms = 0;
static bool buzzerEnabled = true;        // ON/OFFの周期駆動

static unsigned long solenoidNext_ms = 0;
static bool solenoidPulsing = false;
static unsigned long solenoidPulseEnd_ms = 0;

void setup() {
  pinMode(BUZZER_POS_PIN, OUTPUT);
  pinMode(BUZZER_NEG_PIN, OUTPUT);
  pinMode(SOLENOID_SIG_PIN, OUTPUT);

  // 初期状態：無音（両ピンLOW）
  digitalWrite(BUZZER_POS_PIN, LOW);
  digitalWrite(BUZZER_NEG_PIN, LOW);

  digitalWrite(SOLENOID_SIG_PIN, LOW);

  // 周期計算（半周期）
  halfPeriod_us = (unsigned long)(1000000.0 / (2.0 * BUZZER_FREQ_HZ));

  // タイマ初期化
  nextToggle_us = micros() + halfPeriod_us;
  buzzerStateChange_ms = millis() + BUZZER_ON_MS;

  // ソレノイド初期スケジュール
  solenoidNext_ms = millis() + 500; // 最初の動作を0.5秒後に
}

// 反相でブザーを駆動（buzzerEnabled=true の間だけ実行）
static inline void driveBuzzerDifferential() {
  if (!buzzerEnabled) {
    // 無音：両方LOWに固定
    digitalWrite(BUZZER_POS_PIN, LOW);
    digitalWrite(BUZZER_NEG_PIN, LOW);
    return;
  }

  unsigned long now = micros();
  // 半周期ごとに反転
  if ((long)(now - nextToggle_us) >= 0) {
    buzzerPhase = !buzzerPhase;
    nextToggle_us += halfPeriod_us;

    // 反相出力：片方HIGH、片方LOW
    if (buzzerPhase) {
      digitalWrite(BUZZER_POS_PIN, HIGH);
      digitalWrite(BUZZER_NEG_PIN, LOW);
    } else {
      digitalWrite(BUZZER_POS_PIN, LOW);
      digitalWrite(BUZZER_NEG_PIN, HIGH);
    }
  }
}

// ブザーのON/OFFを一定周期で繰り返す
static inline void serviceBuzzerOnOff() {
  unsigned long now_ms = millis();
  if (buzzerEnabled) {
    if ((long)(now_ms - buzzerStateChange_ms) >= 0) {
      // ON期間終了 → OFFへ
      buzzerEnabled = false;
      buzzerStateChange_ms = now_ms + BUZZER_OFF_MS;
      // 無音に即座に落とす
      digitalWrite(BUZZER_POS_PIN, LOW);
      digitalWrite(BUZZER_NEG_PIN, LOW);
    }
  } else {
    if ((long)(now_ms - buzzerStateChange_ms) >= 0) {
      // OFF期間終了 → ONへ
      buzzerEnabled = true;
      buzzerStateChange_ms = now_ms + BUZZER_ON_MS;
      // 次のトグル基準を更新（音の連続性は不要なのでリセットでOK）
      nextToggle_us = micros() + halfPeriod_us;
    }
  }
}

// ソレノイド信号（D3）を周期パルスで駆動
static inline void serviceSolenoidPulse() {
  unsigned long now_ms = millis();

  if (!solenoidPulsing) {
    // 次のパルス開始タイミング？
    if ((long)(now_ms - solenoidNext_ms) >= 0) {
      solenoidPulsing = true;
      solenoidPulseEnd_ms = now_ms + SOLENOID_PULSE_MS;
      digitalWrite(SOLENOID_SIG_PIN, HIGH);  // パルス開始
    }
  } else {
    // パルス終了？
    if ((long)(now_ms - solenoidPulseEnd_ms) >= 0) {
      digitalWrite(SOLENOID_SIG_PIN, LOW);   // パルス終了
      solenoidPulsing = false;
      solenoidNext_ms = now_ms + (SOLENOID_PERIOD_MS - SOLENOID_PULSE_MS);
    }
  }
}

void loop() {
  // ブザーの反相駆動（4kHz）
  driveBuzzerDifferential();

  // ブザーON/OFFの周期制御
  serviceBuzzerOnOff();

  // ソレノイド信号の周期パルス
  serviceSolenoidPulse();

  // できるだけ軽く回す（SAMD21ならdelayMicroseconds不要）
}
