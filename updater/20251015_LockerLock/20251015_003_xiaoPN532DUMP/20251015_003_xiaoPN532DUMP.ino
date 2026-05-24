/*
  Seeed XIAO SAMD21 + PN532 (I2C) FeliCa 全体ダンプ（無暗号領域スキャン）
  - elechouse/PN532 ライブラリ使用
  - 起動: while(!Serial) を使わず delay(1500) のみ
  - まず 0x000B を従来通りダンプ
  - 続いてサービスコードを走査し、無暗号で読める領域をひたすらダンプ

  配線:
    XIAO SAMD21 3.3V/GND
    SDA(D4) -> PN532 SDA
    SCL(D5) -> PN532 SCL
    IRQ/RESET 未接続（ポーリング）
  シリアル: 115200 bps
*/

#include <Wire.h>
#include <PN532_I2C.h>
#include <PN532.h>

// ====== I2C + PN532 ======
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// ====== パラメータ ======
static const uint16_t FELICA_SYSTEM_CODE   = 0xFFFF; // 0xFFFF=全探索
static const uint8_t  FELICA_REQUEST_CODE  = 0x01;   // system code を返す

// まず読む既定サービス（共通領域など）
static const uint16_t SERVICE_CODE_COMMON  = 0x000B;
static const uint16_t START_BLOCK_DEFAULT  = 0;
static const uint16_t BLOCK_COUNT_DEFAULT  = 32;     // 例: 32ブロック

// 走査パラメータ（必要に応じて狭めてください）
static const uint16_t SCAN_SERVICE_BEGIN   = 0x0000;
static const uint16_t SCAN_SERVICE_END     = 0x01FF; // 0x0000〜0x01FF を走査

// 読み出し挙動
static const uint8_t  MAX_BLOCKS_PER_CMD   = 12;     // 1コマンドのブロック上限
static const uint16_t MAX_BLOCKS_PER_SVC   = 64;     // サービスごと最大読み出しブロック数（安全上限）
static const bool     STOP_AT_FIRST_FAIL   = true;   // 途中で失敗したらそのサービスは終了

// ====== ユーティリティ ======
void dumpHexLine(const uint8_t* data, size_t len) {
  for (size_t i = 0; i < len; i++) {
    if (data[i] < 0x10) Serial.print('0');
    Serial.print(data[i], HEX);
    Serial.print(' ');
  }
}

// Polling（カード待ち）して IDm/PMm/SystemCode を表示
bool felicaPollPrint(uint8_t idm[8], uint8_t pmm[8], uint16_t *sysCodeResp) {
  Serial.print("Waiting for a FeliCa card... ");
  uint8_t ok = nfc.felica_Polling(FELICA_SYSTEM_CODE, FELICA_REQUEST_CODE, idm, pmm, sysCodeResp, 5000);
  if (ok != 1) {
    Serial.println("not found");
    return false;
  }
  Serial.println("detected!");

  Serial.print("  IDm: "); dumpHexLine(idm, 8); Serial.println();
  Serial.print("  PMm: "); dumpHexLine(pmm, 8); Serial.println();
  Serial.print("  System Code: 0x");
  if (*sysCodeResp < 0x1000) Serial.print('0');
  if (*sysCodeResp < 0x0100) Serial.print('0');
  if (*sysCodeResp < 0x0010) Serial.print('0');
  Serial.println(*sysCodeResp, HEX);
  return true;
}

// サービス存在確認（鍵不要かのざっくり確認）
bool requestServiceOnce(uint16_t serviceCode, uint16_t *keyVersionOut) {
  uint16_t serviceList[1] = { serviceCode };
  uint16_t keyVersions[1] = { 0x0000 };
  uint8_t ok = nfc.felica_RequestService(1, serviceList, keyVersions);
  if (ok == 1) {
    if (keyVersionOut) *keyVersionOut = keyVersions[0];
    return true; // 一応 OK（=応答あり）
  }
  return false;
}

// 任意サービスを連続ダンプ（先頭から読めるだけ/上限まで）
bool dumpServiceSequential(uint16_t serviceCode,
                           uint16_t startBlock,
                           uint16_t maxBlocks,
                           bool stopAtFirstFail) {
  // 12ブロックずつ読んで、成功した分だけ出力
  uint16_t remaining = maxBlocks;
  uint16_t current   = startBlock;

  bool everSucceeded = false;

  while (remaining > 0) {
    uint8_t thisTime = (remaining > MAX_BLOCKS_PER_CMD) ? MAX_BLOCKS_PER_CMD : remaining;

    // ブロックリスト 0x8000 | ブロック番号（サービス内ブロック指定）
    uint16_t blockList[MAX_BLOCKS_PER_CMD];
    for (uint8_t i = 0; i < thisTime; i++) {
      blockList[i] = 0x8000 | (uint16_t)(current + i);
    }

    // 出力バッファ [thisTime][16]
    uint8_t blockData[MAX_BLOCKS_PER_CMD][16];
    memset(blockData, 0, sizeof(blockData));

    uint16_t serviceList[1] = { serviceCode };

    uint8_t ok = nfc.felica_ReadWithoutEncryption(
                   1,               // サービス数
                   serviceList,     // サービスコード配列
                   thisTime,        // 読みブロック数
                   blockList,       // ブロックリスト
                   blockData        // 出力
                 );

    if (ok != 1) {
      if (!everSucceeded) {
        // 1回目から失敗 ⇒ このサービスは読めない/存在しないと判断
        return false;
      }
      // 途中で失敗
      if (stopAtFirstFail) return true;
      // 続行モードなら、そのブロック群は飛ばして進める
      current   += thisTime;
      remaining -= thisTime;
      continue;
    }

    // 表示
    for (uint8_t i = 0; i < thisTime; i++) {
      Serial.print("  Block ");
      Serial.print(current + i);
      Serial.print(": ");
      dumpHexLine(blockData[i], 16);
      Serial.println();
    }

    everSucceeded = true;
    current   += thisTime;
    remaining -= thisTime;
  }

  return true;
}

// “0x000Bの定番ダンプ” → “サービススキャン＆全ダンプ”
void dumpFelicaAll_NoEnc() {
  uint8_t  idm[8] = {0};
  uint8_t  pmm[8] = {0};
  uint16_t sysc   = 0;

  if (!felicaPollPrint(idm, pmm, &sysc)) return;

  // --- まず共通領域 0x000B をダンプ ---
  Serial.println("\n[Common service 0x000B dump]");
  uint16_t keyv = 0xFFFF;
  bool svcOK = requestServiceOnce(SERVICE_CODE_COMMON, &keyv);
  Serial.print("  RequestService(0x000B): "); Serial.println(svcOK ? "OK" : "NG");
  if (svcOK) {
    Serial.print("  KeyVersion: 0x"); Serial.println(keyv, HEX);
    bool ok = dumpServiceSequential(SERVICE_CODE_COMMON,
                                    START_BLOCK_DEFAULT,
                                    BLOCK_COUNT_DEFAULT,
                                    STOP_AT_FIRST_FAIL);
    if (!ok) Serial.println("  -> Could not read 0x000B (no readable blocks).");
  } else {
    Serial.println("  -> Service 0x000B not available or requires keys.");
  }

  // --- サービススキャン ---
  Serial.println("\n[Service scan + dump (no-encryption, sequential)]");
  Serial.print("  Scan range: 0x"); Serial.print(SCAN_SERVICE_BEGIN, HEX);
  Serial.print(" .. 0x"); Serial.println(SCAN_SERVICE_END, HEX);

  for (uint16_t svc = SCAN_SERVICE_BEGIN; svc <= SCAN_SERVICE_END; ++svc) {
    // 0x000B は上で処理済みなのでスキップ（必要なら消してください）
    if (svc == SERVICE_CODE_COMMON) continue;

    uint16_t keyver = 0xFFFF;
    bool present = requestServiceOnce(svc, &keyver);
    if (!present) continue; // 応答なし

    Serial.print("\n  [Service 0x"); Serial.print(svc, HEX); Serial.println("]");
    Serial.print("    KeyVersion: 0x"); Serial.println(keyver, HEX);

    bool ok = dumpServiceSequential(svc,
                                    0,                 // 先頭から
                                    MAX_BLOCKS_PER_SVC,// 上限まで
                                    STOP_AT_FIRST_FAIL);
    if (!ok) {
      Serial.println("    (read failed at start; skipping)");
    }
  }

  Serial.println("\n[Scan finished]");
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);

  Serial.begin(115200);
  delay(1500);  // USB列挙待ち（Windowsで重要）

  // 起動インジケータ
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, HIGH); delay(120);
    digitalWrite(LED_BUILTIN, LOW);  delay(120);
  }

  Serial.println("\nPN532 FeliCa Dump (I2C) [XIAO SAMD21 / Full-scan ver.]");

  Wire.begin();      // XIAO: SDA=D4, SCL=D5
  nfc.begin();

  uint32_t ver = nfc.getFirmwareVersion();
  if (!ver) {
    Serial.println("Didn't find PN532. Check wiring and I2C mode.");
  } else {
    Serial.print("Found PN532: IC=");
    Serial.print((ver >> 24) & 0xFF, HEX);
    Serial.print(", Ver=");
    Serial.print((ver >> 16) & 0xFF, DEC);
    Serial.print('.');
    Serial.println((ver >> 8) & 0xFF, DEC);

    nfc.setPassiveActivationRetries(0xFF);
    nfc.SAMConfig();
    Serial.println("Ready.");
  }
}

void loop() {
  // LEDで生存表示
  digitalWrite(LED_BUILTIN, HIGH); delay(20);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("\nPlace a FeliCa card on the reader...");
  dumpFelicaAll_NoEnc();

  Serial.println("Done. Retry in 1s...");
  delay(1000);
}
