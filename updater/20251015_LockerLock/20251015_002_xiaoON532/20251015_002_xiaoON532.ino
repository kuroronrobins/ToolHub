/*
  Seeed XIAO SAMD21 + PN532 (I2C)
  FeliCa: サービス 0x020B の [0000],[0001] を読み、ASCII から 9桁目(=index 8)の7桁を社員番号として抽出
  - ライブラリ: elechouse/PN532 (PN532_I2C, PN532)
  - シリアル: 115200bps / Serial
  - 起動待ち: while(!Serial) は使わず delay(1500) のみ

  配線:
    XIAO SAMD21 3.3V/GND
    SDA(D4) -> PN532 SDA
    SCL(D5) -> PN532 SCL
    IRQ/RESET 未接続（ポーリング）
*/

#include <Wire.h>
#include <PN532_I2C.h>
#include <PN532.h>

PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

// ---- FeliCa Polling ----
static const uint16_t FELICA_SYSTEM_CODE  = 0xFFFF; // 全探索
static const uint8_t  FELICA_REQUEST_CODE = 0x01;   // system code を返す

// ---- 対象サービス/ブロック ----
static const uint16_t TARGET_SERVICE_CODE = 0x020B; // Random Access R/O（読み出し対象）
static const uint16_t TARGET_START_BLOCK  = 0;      // [0000]
static const uint8_t  TARGET_BLOCKS_TO_READ = 2;    // [0000],[0001] の 2ブロック(計32B)
static const uint8_t  MAX_BLOCKS_PER_CMD  = 12;     // ライブラリ実用上限

// ---- 任意: 共通領域 0x000B の簡易ダンプ（必要に応じてON/OFF）----
static const bool     ALSO_DUMP_000B      = false;  // 必要なら true に
static const uint16_t SERVICE_CODE_COMMON = 0x000B;
static const uint16_t COMMON_START_BLOCK  = 0;
static const uint16_t COMMON_BLOCK_COUNT  = 32;

// ---- ユーティリティ ----
void dumpHexLine(const uint8_t* data, size_t len) {
  for (size_t i = 0; i < len; i++) {
    if (data[i] < 0x10) Serial.print('0');
    Serial.print(data[i], HEX);
    Serial.print(' ');
  }
}

bool felica_poll(uint8_t idm[8], uint8_t pmm[8], uint16_t *sysCodeResp) {
  Serial.print("Waiting for a FeliCa card... ");
  uint8_t ok = nfc.felica_Polling(FELICA_SYSTEM_CODE, FELICA_REQUEST_CODE, idm, pmm, sysCodeResp, 5000);
  if (ok != 1) { Serial.println("not found"); return false; }
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

// 任意サービスから、サービス内ブロック番号指定で blockCount 個を読む（最大12/回に分割）
bool felica_read_blocks_noenc(uint16_t serviceCode,
                              uint16_t startBlock,
                              uint8_t  blockCount,
                              uint8_t  outData[][16]) {
  uint8_t totalRead = 0;
  while (totalRead < blockCount) {
    uint8_t remain   = blockCount - totalRead;
    uint8_t thisTime = (remain > MAX_BLOCKS_PER_CMD) ? MAX_BLOCKS_PER_CMD : remain;

    uint16_t blockList[MAX_BLOCKS_PER_CMD];
    for (uint8_t i = 0; i < thisTime; i++) {
      blockList[i] = 0x8000 | (uint16_t)(startBlock + totalRead + i);
    }

    uint16_t serviceList[1] = { serviceCode };

    // ★第5引数は uint8_t (*)[16] を渡す必要がある
    uint8_t (*dst)[16] = &outData[totalRead];

    int8_t ok = nfc.felica_ReadWithoutEncryption(
                  1,                // numService
                  serviceList,      // serviceCodeList
                  thisTime,         // numBlock
                  blockList,        // blockList
                  dst               // blockData (uint8_t (*)[16])
                );
    if (ok != 1) return false;

    totalRead += thisTime;
  }
  return true;
}

// ASCII 文字列化（0x00 に当たったら終了。可視ASCIIのみ、そのほかは '.'）
String ascii_from_blocks(uint8_t data[][16], uint8_t blocks) {
  String s;
  for (uint8_t b = 0; b < blocks; b++) {
    for (uint8_t i = 0; i < 16; i++) {
      uint8_t c = data[b][i];
      if (c == 0x00) return s;     // NULL 終端
      if (c >= 0x20 && c <= 0x7E)  // 可視ASCIIのみ
        s += (char)c;
      else
        s += '.';
    }
  }
  return s;
}

// 9桁目(=0-basedでindex 8)から7桁を固定抽出。
// 先頭8桁が "11194005" であることを確認（不要ならこのチェックは外してOK）
String extract_emp7_at_pos9(const String& s) {
  const String prefix = "11194005";
  const int start = 8;   // 0-based: 9桁目
  const int len   = 7;

  if (s.length() < start + len) return String("");

  // 接頭辞確認（不要ならコメントアウト）
  if (s.substring(0, prefix.length()) != prefix) return String("");

  String cand = s.substring(start, start + len);
  for (int i = 0; i < len; i++) {
    char c = cand[i];
    if (c < '0' || c > '9') return String("");
  }
  return cand;
}

// 任意: 0x000B を連続ダンプ（必要なときのみ呼ぶ）
void dump_common_000B() {
  uint16_t keyv = 0x0000;
  uint16_t svcList[1] = { SERVICE_CODE_COMMON };
  uint8_t  ok = nfc.felica_RequestService(1, svcList, &keyv);
  Serial.print("\n[Common 0x000B] RequestService: ");
  Serial.println(ok == 1 ? "OK" : "NG");
  if (ok != 1) return;

  uint8_t buf[12][16]; // 12ブロック単位で使い回す
  uint16_t remaining = COMMON_BLOCK_COUNT;
  uint16_t current   = COMMON_START_BLOCK;
  while (remaining > 0) {
    uint8_t thisTime = (remaining > 12) ? 12 : remaining;
    if (!felica_read_blocks_noenc(SERVICE_CODE_COMMON, current, thisTime, buf)) {
      Serial.print("  Read fail at block "); Serial.println(current); break;
    }
    for (uint8_t i = 0; i < thisTime; i++) {
      Serial.print("  Block "); Serial.print(current + i); Serial.print(": ");
      dumpHexLine(buf[i], 16); Serial.println();
    }
    current   += thisTime;
    remaining -= thisTime;
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  delay(1500); // USB列挙待ち（Windowsで重要）

  // 起動インジケータ
  for (int i = 0; i < 3; i++) { digitalWrite(LED_BUILTIN, HIGH); delay(120); digitalWrite(LED_BUILTIN, LOW); delay(120); }

  Serial.println("\nPN532 FeliCa Dump (I2C) [XIAO SAMD21 / 0x020B fixed-pos extractor]");

  Wire.begin();  // XIAO: SDA=D4, SCL=D5
  nfc.begin();

  uint32_t ver = nfc.getFirmwareVersion();
  if (!ver) {
    Serial.println("Didn't find PN532. Check wiring and I2C mode.");
  } else {
    Serial.print("Found PN532: IC="); Serial.print((ver >> 24) & 0xFF, HEX);
    Serial.print(", Ver="); Serial.print((ver >> 16) & 0xFF, DEC);
    Serial.print('.');      Serial.println((ver >> 8) & 0xFF, DEC);
    nfc.setPassiveActivationRetries(0xFF);
    nfc.SAMConfig();
    Serial.println("Ready.");
  }
}

void loop() {
  // 生存インジケータ
  digitalWrite(LED_BUILTIN, HIGH); delay(20); digitalWrite(LED_BUILTIN, LOW);

  // --- Polling ---
  uint8_t idm[8], pmm[8]; uint16_t sysc = 0;
  if (!felica_poll(idm, pmm, &sysc)) { delay(800); return; }

  // --- サービス 0x020B を 2ブロック読む ---
  Serial.println("\n[Read Service 0x020B blocks 0..1]");
  {
    uint16_t svcList[1] = { TARGET_SERVICE_CODE };
    uint16_t keyv = 0x0000;
    uint8_t  ok = nfc.felica_RequestService(1, svcList, &keyv);
    Serial.print("  RequestService(0x020B): "); Serial.println(ok == 1 ? "OK" : "NG");
    if (ok != 1) {
      Serial.println("  -> Service not available or protected.");
    } else {
      uint8_t blk[2][16];
      if (felica_read_blocks_noenc(TARGET_SERVICE_CODE, TARGET_START_BLOCK, TARGET_BLOCKS_TO_READ, blk)) {
        // HEX 表示
        for (uint8_t i = 0; i < TARGET_BLOCKS_TO_READ; i++) {
          Serial.print("  ["); Serial.print(i, DEC); Serial.print("] ");
          dumpHexLine(blk[i], 16); Serial.println();
        }

        // ASCII 化（NULL 終端まで）
        String ascii = ascii_from_blocks(blk, TARGET_BLOCKS_TO_READ);
        Serial.print("  ASCII: '"); Serial.print(ascii); Serial.println("'");

        // ★ 9桁目から7桁固定で抽出
        String emp = extract_emp7_at_pos9(ascii);
        if (emp.length() == 7) {
          Serial.print("  Employee No (pos9..15): "); Serial.println(emp);
        } else {
          Serial.println("  Employee No not found at fixed position (pos9..15).");
        }
      } else {
        Serial.println("  ReadWithoutEncryption failed for 0x020B.");
      }
    }
  }

  // ----（任意）共通領域 0x000B のダンプ ----
  if (ALSO_DUMP_000B) dump_common_000B();

  Serial.println("\nDone. Retry in 1s...");
  delay(1000);
}
