// ============================================
//  Dual-Pin Buzzer Melody Driver (A0 & A1)
//  Events: door-ajar (escalating), unlocked, locked, low-battery
//  Board: Seeeduino XIAO (SAMD21) 他
// ============================================

// ---- ピン定義 ----
#define BUZZER_PIN_A A0
#define BUZZER_PIN_B A1

// ====================== 基本ユーティリティ ======================
void restMs(uint16_t ms) {
  digitalWrite(BUZZER_PIN_A, LOW);
  digitalWrite(BUZZER_PIN_B, LOW);
  delay(ms);
}

// 周波数=0は休符
void buzzTone(uint16_t freq, uint16_t dur_ms) {
  if (freq == 0) { restMs(dur_ms); return; }

  // 片周期 [us] と周期数
  uint32_t halfPeriod = 500000UL / (uint32_t)freq;           // 500,000 = 1e6/2
  uint32_t cycles     = (uint32_t)freq * dur_ms / 1000UL;

  for (uint32_t i = 0; i < cycles; i++) {
    // 逆位相で差動駆動
    digitalWrite(BUZZER_PIN_A, HIGH);
    digitalWrite(BUZZER_PIN_B, LOW);
    delayMicroseconds(halfPeriod);

    digitalWrite(BUZZER_PIN_A, LOW);
    digitalWrite(BUZZER_PIN_B, HIGH);
    delayMicroseconds(halfPeriod);
  }

  // 消音
  digitalWrite(BUZZER_PIN_A, LOW);
  digitalWrite(BUZZER_PIN_B, LOW);
}

void playSequence(const uint16_t* notes, const uint16_t* lens, uint8_t len, uint16_t gap_ms = 25) {
  for (uint8_t i = 0; i < len; i++) {
    buzzTone(notes[i], lens[i]);
    if (gap_ms) restMs(gap_ms);
  }
}

// ====================== イベント別メロディ ======================

// ---- 開きっぱなし警告：家電風「ピッ・ピッ・・ピー↑」を小節で繰り返し
//      小節間の休符がだんだん短くなり“急かし感”が増す
void alertDoorAjar_bar(uint16_t short_ms = 90, uint16_t long_ms = 300) {
  // 4kHz近傍で少しだけ上がる長音
  const uint16_t N1  = 3800; // 短1
  const uint16_t N2  = 3800; // 短2
  const uint16_t N3a = 3950; // 長・前段
  const uint16_t N3b = 4100; // 長・後段（上昇）

  // 短・短
  buzzTone(N1, short_ms);
  restMs(80);
  buzzTone(N2, short_ms);
  restMs(120);

  // 長（内部でちょい上昇）
  buzzTone(N3a, (uint16_t)(long_ms * 2 / 3));
  buzzTone(N3b, (uint16_t)(long_ms * 1 / 3));
}

void alertDoorAjar_escalating(uint8_t bars = 6, uint16_t gap_start_ms = 700, uint16_t gap_end_ms = 250) {
  if (bars == 0) return;
  for (uint8_t i = 0; i < bars; i++) {
    alertDoorAjar_bar();
    // 線形にギャップを短縮（急かす）
    uint32_t gap = gap_start_ms + (int32_t)(gap_end_ms - gap_start_ms) * i / (bars - 1);
    restMs(gap);
  }
}

// ---- ロック解除成功：上昇3音（明るめ）
void chimeUnlocked() {
  const uint16_t notes[] = { 1047, 1319, 1568 };   // C6, E6, G6 付近
  const uint16_t lens[]  = { 120, 120, 220 };
  playSequence(notes, lens, 3, 35);
}

// ---- 再ロック成功：下降3音（落ち着き）
void chimeLocked() {
  const uint16_t notes[] = { 1568, 1319, 1047 };
  const uint16_t lens[]  = { 120, 120, 200 };
  playSequence(notes, lens, 3, 35);
}

// ---- 低バッテリー警告：低めの 3短 + 1長（聞き取りやすく）
void warnLowBattery(uint8_t repeats = 2) {
  const uint16_t notes[] = { 650, 650, 650, 650 };
  const uint16_t lens[]  = { 120, 120, 120, 420 };
  for (uint8_t r = 0; r < repeats; r++) {
    playSequence(notes, lens, 4, 90);
    restMs(350);
  }
}

// ====================== セットアップ / デモ ======================
void setup() {
  pinMode(BUZZER_PIN_A, OUTPUT);
  pinMode(BUZZER_PIN_B, OUTPUT);
  digitalWrite(BUZZER_PIN_A, LOW);
  digitalWrite(BUZZER_PIN_B, LOW);

  // --- デモ（必要なければコメントアウト） ---
  chimeUnlocked();              // 解除成功音
  restMs(400);
  chimeLocked();                // 再ロック成功音
  restMs(600);
  warnLowBattery(1);            // 低バッテリー警告（1セット）
  restMs(600);
  alertDoorAjar_escalating(6);  // 開きっぱなし（6小節、だんだん急かす）
}

void loop() {
  restMs(600);
  alertDoorAjar_escalating(6);
}
