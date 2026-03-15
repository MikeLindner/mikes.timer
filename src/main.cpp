#include <Arduino.h>

// DuoClock — dumb serial button box
// TX: "T\n" or "M\n" on button press (press only, not release)
// RX: "T1\n" "T0\n" "M1\n" "M0\n" to control LEDs

const int BTN_THEM = 13;
const int BTN_ME   = 15;
const int LED_THEM = 16;
const int LED_ME   = 17;

bool lastBtnThem = true;
bool lastBtnMe   = true;

void processSerial() {
  while (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "T1" || cmd == "t1")      digitalWrite(LED_THEM, HIGH);
    else if (cmd == "T0" || cmd == "t0") digitalWrite(LED_THEM, LOW);
    else if (cmd == "M1" || cmd == "m1") digitalWrite(LED_ME, HIGH);
    else if (cmd == "M0" || cmd == "m0") digitalWrite(LED_ME, LOW);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(LED_THEM, OUTPUT);
  pinMode(LED_ME,   OUTPUT);
  pinMode(BTN_THEM, INPUT_PULLUP);
  pinMode(BTN_ME,   INPUT_PULLUP);
  Serial.println("DUOCLOCK");
}

void loop() {
  processSerial();

  bool btnThem = digitalRead(BTN_THEM);
  if (btnThem != lastBtnThem) {
    delay(20);
    btnThem = digitalRead(BTN_THEM);
    if (btnThem != lastBtnThem) {
      lastBtnThem = btnThem;
      if (!btnThem) Serial.println("T");
    }
  }

  bool btnMe = digitalRead(BTN_ME);
  if (btnMe != lastBtnMe) {
    delay(20);
    btnMe = digitalRead(BTN_ME);
    if (btnMe != lastBtnMe) {
      lastBtnMe = btnMe;
      if (!btnMe) Serial.println("M");
    }
  }

  delay(5);
}
