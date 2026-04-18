/*
 * BrailleDesk - 6-dot rotating-ball Braille cell firmware
 * Target: Arduino Uno / Nano (ATmega328P)
 *
 * Serial protocol (9600 baud):
 *   Input:  "BRAILLE:xxxxxx\n"  where x is '0' (flat) or '1' (raised)
 *           Dots are numbered 1..6 in standard Braille order:
 *              1 4
 *              2 5
 *              3 6
 *   Output: "OK\n"  after servos have been commanded
 *           "ERR:<reason>\n" on a bad packet
 *
 * Power notes:
 *   - Do NOT power six servos from the Arduino 5V pin. Use a separate
 *     5-6V / 3A buck converter for the servo rail. Tie grounds together.
 *   - Add a 1000uF cap across the servo rail near the servos.
 */

#include <Servo.h>

// -------- Pin mapping (all PWM-capable on the Uno/Nano) --------
const uint8_t DOT_PINS[6] = {3, 5, 6, 9, 10, 11};

// -------- Servo end-angles --------
// Tune these per mechanism. FLAT is the flat face up, RAISED is the bumpy face up.
const uint8_t FLAT_ANGLE   = 10;
const uint8_t RAISED_ANGLE = 170;

Servo dots[6];
char currentState[7] = "000000";   // last commanded state (+ null)

void setAll(const char* bits) {
  for (uint8_t i = 0; i < 6; i++) {
    dots[i].write(bits[i] == '1' ? RAISED_ANGLE : FLAT_ANGLE);
  }
  memcpy(currentState, bits, 6);
  currentState[6] = '\0';
}

void setup() {
  Serial.begin(9600);
  for (uint8_t i = 0; i < 6; i++) {
    dots[i].attach(DOT_PINS[i]);
    dots[i].write(FLAT_ANGLE);
  }
  // Give servos time to reach home before accepting commands
  delay(500);
  Serial.println("READY");
}

void loop() {
  static char buf[32];
  static uint8_t idx = 0;

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[idx] = '\0';
      handleLine(buf);
      idx = 0;
    } else if (idx < sizeof(buf) - 1) {
      buf[idx++] = c;
    } else {
      // overflow - reset
      idx = 0;
    }
  }
}

void handleLine(const char* line) {
  // Expect "BRAILLE:xxxxxx"
  const char* prefix = "BRAILLE:";
  const uint8_t pref_len = 8;
  if (strncmp(line, prefix, pref_len) != 0) {
    Serial.println("ERR:prefix");
    return;
  }
  const char* bits = line + pref_len;
  if (strlen(bits) < 6) {
    Serial.println("ERR:len");
    return;
  }
  for (uint8_t i = 0; i < 6; i++) {
    if (bits[i] != '0' && bits[i] != '1') {
      Serial.println("ERR:char");
      return;
    }
  }
  char clean[7];
  memcpy(clean, bits, 6);
  clean[6] = '\0';
  setAll(clean);
  Serial.println("OK");
}