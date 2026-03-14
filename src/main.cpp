#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>

// ─── WIFI CONFIG ────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";

// ─── STATIC IP CONFIG ───────────────────────────────────
IPAddress staticIP(192, 168, 1, 200);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns1(1, 1, 1, 1);
IPAddress dns2(1, 0, 0, 1);

// ─── PIN ASSIGNMENTS ────────────────────────────────────
const int btnMe   = 15;
const int btnThem = 13;
const int ledThem = 5;
const int ledMe   = 4;

// ─── STATE ──────────────────────────────────────────────
enum State { THEM, ME };
State currentState = ME;

unsigned long lastDebounce = 0;
const unsigned long debounceDelay = 150;

struct LogEntry {
  unsigned long ms;
  State state;
};
const int MAX_LOG = 200;
LogEntry logBuffer[MAX_LOG];
int logCount = 0;

WebServer server(80);

// ─── STATE SWITCH ───────────────────────────────────────
void switchState(State newState) {
  if (currentState == newState) return;
  currentState = newState;

  digitalWrite(ledThem, currentState == THEM);
  digitalWrite(ledMe,   currentState == ME);

  if (logCount < MAX_LOG) {
    logBuffer[logCount++] = { millis(), currentState };
  }

  Serial.printf("%lu,%s\n", millis(),
                currentState == THEM ? "THEM" : "ME");
}

// ─── WEB PAGE ───────────────────────────────────────────
const char HTML_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🕐 DuoClock — Time Logger</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .header {
    text-align: center;
    padding: 2rem 1rem 1rem;
  }
  .header h1 { font-size: 2.2rem; }
  .header p { color: #94a3b8; margin-top: 0.3rem; }
  .status-bar {
    display: flex;
    gap: 1rem;
    margin: 1rem 0;
    padding: 0.8rem 1.5rem;
    background: #1e293b;
    border-radius: 1rem;
    font-size: 0.95rem;
  }
  .status-bar .dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 0.4rem;
    vertical-align: middle;
  }
  .dot.on  { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
  .dot.off { background: #475569; }
  .btn-row {
    display: flex;
    gap: 1.5rem;
    margin: 1.5rem 0;
    flex-wrap: wrap;
    justify-content: center;
  }
  .big-btn {
    width: 180px; height: 180px;
    border: none;
    border-radius: 1.5rem;
    font-size: 1.4rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: #fff;
  }
  .big-btn:active { transform: scale(0.95); }
  .big-btn.them {
    background: linear-gradient(135deg, #7c3aed, #6d28d9);
    box-shadow: 0 4px 24px rgba(124,58,237,0.4);
  }
  .big-btn.them.active {
    background: linear-gradient(135deg, #a78bfa, #7c3aed);
    box-shadow: 0 0 40px rgba(167,139,250,0.6);
  }
  .big-btn.me {
    background: linear-gradient(135deg, #0ea5e9, #0284c7);
    box-shadow: 0 4px 24px rgba(14,165,233,0.4);
  }
  .big-btn.me.active {
    background: linear-gradient(135deg, #38bdf8, #0ea5e9);
    box-shadow: 0 0 40px rgba(56,189,248,0.6);
  }
  .big-btn .emoji { font-size: 3rem; }
  .log-section {
    width: 90%; max-width: 500px;
    margin: 1.5rem 0 2rem;
  }
  .log-section h2 {
    font-size: 1.1rem;
    margin-bottom: 0.5rem;
    color: #94a3b8;
  }
  .log-box {
    background: #1e293b;
    border-radius: 1rem;
    padding: 1rem;
    max-height: 300px;
    overflow-y: auto;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.85rem;
    line-height: 1.6;
  }
  .log-entry { padding: 0.15rem 0; }
  .log-entry.them { color: #a78bfa; }
  .log-entry.me   { color: #38bdf8; }
  .info-bar {
    display: flex;
    gap: 2rem;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    color: #64748b;
    flex-wrap: wrap;
    justify-content: center;
  }
  .copy-btn {
    background: #334155;
    color: #e2e8f0;
    border: none;
    padding: 0.5rem 1.2rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font-size: 0.85rem;
    margin-top: 0.5rem;
  }
  .copy-btn:hover { background: #475569; }
</style>
</head>
<body>

<div class="header">
  <h1>🕐 DuoClock</h1>
  <p>⏱️ Billable Time Logger</p>
</div>

<div class="status-bar">
  <span><span class="dot" id="dotThem"></span>💜 THEM</span>
  <span><span class="dot" id="dotMe"></span>💙 ME</span>
  <span>📡 <span id="uptime">--</span></span>
</div>

<div class="btn-row">
  <button class="big-btn them" id="btnThem" onclick="sw('THEM')">
    <span class="emoji">💼</span>
    THEM
  </button>
  <button class="big-btn me" id="btnMe" onclick="sw('ME')">
    <span class="emoji">🏠</span>
    ME
  </button>
</div>

<div class="info-bar">
  <span>🔌 IP: <span id="ip">--</span></span>
  <span>📊 Entries: <span id="count">0</span></span>
</div>

<div class="log-section">
  <h2>📋 Session Log</h2>
  <div class="log-box" id="logBox">
    <div style="color:#64748b">No entries yet...</div>
  </div>
  <button class="copy-btn" onclick="copyLog()">📋 Copy Log to Clipboard</button>
</div>

<script>
function sw(s) {
  fetch('/switch?state=' + s).then(() => poll());
}
function poll() {
  fetch('/status').then(r => r.json()).then(d => {
    document.getElementById('dotThem').className = 'dot ' + (d.state === 'THEM' ? 'on' : 'off');
    document.getElementById('dotMe').className   = 'dot ' + (d.state === 'ME' ? 'on' : 'off');
    document.getElementById('btnThem').className  = 'big-btn them' + (d.state === 'THEM' ? ' active' : '');
    document.getElementById('btnMe').className    = 'big-btn me' + (d.state === 'ME' ? ' active' : '');
    document.getElementById('uptime').textContent = d.uptime;
    document.getElementById('ip').textContent     = d.ip;
    document.getElementById('count').textContent  = d.log.length;
    var box = document.getElementById('logBox');
    if (d.log.length === 0) {
      box.innerHTML = '<div style="color:#64748b">No entries yet...</div>';
    } else {
      box.innerHTML = d.log.map(function(e) {
        var icon = e.s === 'THEM' ? '💼' : '🏠';
        var cls  = e.s === 'THEM' ? 'them' : 'me';
        return '<div class="log-entry ' + cls + '">' + icon + ' ' + e.t + ' → ' + e.s + '</div>';
      }).join('');
      box.scrollTop = box.scrollHeight;
    }
  });
}
function copyLog() {
  fetch('/status').then(r => r.json()).then(d => {
    var csv = 'millis,state\n' + d.log.map(function(e) { return e.ms + ',' + e.s; }).join('\n');
    navigator.clipboard.writeText(csv);
  });
}
setInterval(poll, 2000);
poll();
</script>
</body>
</html>
)rawliteral";

// ─── WEB HANDLERS ───────────────────────────────────────
String formatUptime(unsigned long ms) {
  unsigned long s = ms / 1000;
  int h = s / 3600;
  int m = (s % 3600) / 60;
  int sec = s % 60;
  char buf[16];
  snprintf(buf, sizeof(buf), "%02d:%02d:%02d", h, m, sec);
  return String(buf);
}

void handleRoot() {
  server.send(200, "text/html", HTML_PAGE);
}

void handleStatus() {
  String json = "{\"state\":\"";
  json += (currentState == THEM ? "THEM" : "ME");
  json += "\",\"uptime\":\"";
  json += formatUptime(millis());
  json += "\",\"ip\":\"";
  json += WiFi.localIP().toString();
  json += "\",\"log\":[";
  for (int i = 0; i < logCount; i++) {
    if (i > 0) json += ",";
    json += "{\"ms\":";
    json += logBuffer[i].ms;
    json += ",\"t\":\"";
    json += formatUptime(logBuffer[i].ms);
    json += "\",\"s\":\"";
    json += (logBuffer[i].state == THEM ? "THEM" : "ME");
    json += "\"}";
  }
  json += "]}";
  server.send(200, "application/json", json);
}

void handleSwitch() {
  String s = server.arg("state");
  if (s == "THEM") switchState(THEM);
  else if (s == "ME") switchState(ME);
  server.send(200, "text/plain", "OK");
}

// ─── SETUP ──────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // Pins
  pinMode(btnMe,   INPUT_PULLUP);
  pinMode(btnThem, INPUT_PULLUP);
  pinMode(ledThem, OUTPUT);
  pinMode(ledMe,   OUTPUT);

  // Initial state
  currentState = THEM; // force different so switchState works
  switchState(ME);

  // WiFi with static IP
  WiFi.config(staticIP, gateway, subnet, dns1, dns2);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());

  // OTA
  ArduinoOTA.setHostname("duoclock");
  ArduinoOTA.onStart([]() {
    Serial.println("OTA update starting...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nOTA update complete!");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("OTA: %u%%\r", (progress * 100) / total);
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("OTA Error[%u]\n", error);
  });
  ArduinoOTA.begin();

  // Web server
  server.on("/",       handleRoot);
  server.on("/status", handleStatus);
  server.on("/switch", handleSwitch);
  server.begin();
  Serial.println("Web server started on port 80");
}

// ─── LOOP ───────────────────────────────────────────────
void loop() {
  ArduinoOTA.handle();
  server.handleClient();

  unsigned long now = millis();
  if (now - lastDebounce > debounceDelay) {
    if (!digitalRead(btnThem)) {
      switchState(THEM);
      lastDebounce = now;
    }
    if (!digitalRead(btnMe)) {
      switchState(ME);
      lastDebounce = now;
    }
  }
}
