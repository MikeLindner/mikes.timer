# ⏱️ DuoClock — Two-Person Activity Timer

> **Milestone 1** ✅ — Core timer logging + web dashboard, deployed and running.

---

## 📖 What Is This?

DuoClock is a physical two-button timer system for tracking shared activities between
two people. Press a button, the corresponding LED lights up for 30 minutes, and the
event is logged. A web dashboard shows the last 7 days of activity at a glance.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   🔴 THEM button ──┐     ┌── 🟡 ME button              │
│                     │     │                             │
│              ┌──────▼─────▼──────┐                      │
│              │                   │                      │
│              │    ESP32 Box      │  ← Physical device   │
│              │  (Button + LED)   │     on the desk      │
│              │                   │                      │
│              └────────┬──────────┘                      │
│                       │ USB Serial                      │
│              ┌────────▼──────────┐                      │
│              │                   │                      │
│              │   Pi Zero W       │  ← Under the desk    │
│              │  "clockradio"     │     always-on        │
│              │                   │                      │
│              │  🧠 Timer logic   │                      │
│              │  📝 Event logger  │                      │
│              │  🌐 Web dashboard │                      │
│              │                   │                      │
│              └───────────────────┘                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🎯 How It Works

### 🔴 THEM Button (Red)
Press it → red LED turns on → stays on for **30 minutes** → auto-off.
Every on/off event is logged with a timestamp.

### 🟡 ME Button (Yellow)
Press it → yellow LED turns on → stays on for **30 minutes** → auto-off.
Every on/off event is logged with a timestamp.

### 🔴🟡 Both Buttons Together
Press both within 1 second → **both LEDs turn off**, both timers cancel.
Logged as `BOTH_CANCEL`.

### ⏰ Independent Timers
Both LEDs can be active at the same time, each with its own 30-minute countdown.
Pressing a button that's already active restarts its 30-minute timer.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        HARDWARE LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ESP32 DevKit v1                                                │
│  ├── GPIO 13 ← BTN_THEM (INPUT_PULLUP, active LOW)             │
│  ├── GPIO 15 ← BTN_ME   (INPUT_PULLUP, active LOW)             │
│  ├── GPIO 16 → LED_THEM (red)                                  │
│  ├── GPIO 17 → LED_ME   (yellow)                                │
│  └── USB Serial @ 115200 baud                                  │
│                                                                 │
│  Protocol:                                                      │
│  ┌──────────────────────────────────────────────┐               │
│  │  ESP32 → Pi:  "T\n"  (THEM pressed)         │               │
│  │               "M\n"  (ME pressed)            │               │
│  │               "DUOCLOCK\n" (device ready)    │               │
│  │                                              │               │
│  │  Pi → ESP32:  "T1\n" (THEM LED on)           │               │
│  │               "T0\n" (THEM LED off)          │               │
│  │               "M1\n" (ME LED on)             │               │
│  │               "M0\n" (ME LED off)            │               │
│  └──────────────────────────────────────────────┘               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                        SOFTWARE LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Pi Zero W ("clockradio.belairmoon.au")                         │
│  ├── duoclock_monitor.py  → systemd service (always running)    │
│  │   ├── Reads serial for button presses                        │
│  │   ├── Sends LED commands back to ESP32                       │
│  │   ├── Manages independent 30-min timers per channel          │
│  │   ├── Detects both-pressed (within 1s window)                │
│  │   └── Writes all events to /var/log/duoclock.log             │
│  │                                                              │
│  ├── duoclock_web.py      → systemd service (port 8080)         │
│  │   ├── Reads /var/log/duoclock.log                            │
│  │   ├── Computes 7-day daily totals per channel                │
│  │   ├── Renders bar graph + table + recent events              │
│  │   └── Auto-refreshes every 60 seconds                        │
│  │                                                              │
│  └── /var/log/duoclock.log  → append-only event log             │
│      ├── THEM_ON                                                │
│      ├── THEM_OFF_TIMEOUT                                       │
│      ├── ME_ON                                                  │
│      ├── ME_OFF_TIMEOUT                                         │
│      └── BOTH_CANCEL                                            │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                      INFRASTRUCTURE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Terraform (Cloudflare)                                         │
│  └── DNS: duoclock.belairmoon.au → device IP                    │
│                                                                 │
│  ESPHome (alternative firmware)                                 │
│  └── esphome/duoclock.yaml → OTA-capable, Home Assistant ready  │
│                                                                 │
│  PlatformIO (primary firmware)                                  │
│  └── src/main.cpp → Arduino framework, bare-metal serial        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📝 Event Log Format

The log file at `/var/log/duoclock.log` uses a simple, machine-readable, line-based format:

```
2026-03-17 09:15:00 THEM_ON
2026-03-17 09:45:00 THEM_OFF_TIMEOUT
2026-03-17 10:02:00 ME_ON
2026-03-17 10:05:30 BOTH_CANCEL
2026-03-17 14:00:00 ME_ON
2026-03-17 14:30:00 ME_OFF_TIMEOUT
```

### 📋 Event Reference

| Event | Meaning | Trigger |
|-------|---------|---------|
| `THEM_ON` | 🔴 Red/THEM LED activated | THEM button pressed |
| `THEM_OFF_TIMEOUT` | 🔴 Red/THEM LED auto-off | 30-minute timer expired |
| `ME_ON` | 🟡 Yellow/ME LED activated | ME button pressed |
| `ME_OFF_TIMEOUT` | 🟡 Yellow/ME LED auto-off | 30-minute timer expired |
| `BOTH_CANCEL` | ⛔ Both LEDs cancelled | Both buttons within 1 second |

---

## 🌐 Web Dashboard

**URL:** `http://clockradio.belairmoon.au:8080/`

The dashboard is a single self-contained HTML page (no JS frameworks, no external
dependencies) served by Python's built-in HTTP server. It shows:

- 📊 **Bar graph** — 7-day view with red (THEM) and yellow (ME) bars
- 📋 **Daily table** — hours and minutes per channel per day, today bolded
- 📜 **Recent events** — last 20 log entries in reverse chronological order
- 🔄 **Auto-refresh** — page reloads every 60 seconds

The dashboard is designed with a dark theme and works well on both desktop and mobile.

---

## 📂 Repository Structure

```
mikes.timer/
│
├── 📄 README.md                  ← You are here
├── 📄 platformio.ini             ← PlatformIO build config (ESP32)
├── 📄 serial_read.py             ← Windows-side serial debug tool
│
├── 📁 src/                       ← ESP32 firmware (PlatformIO/Arduino)
│   └── main.cpp                  ← Button reader + LED controller
│
├── 📁 esphome/                   ← Alternative ESPHome firmware
│   └── duoclock.yaml             ← Full ESPHome config (OTA + HA)
│
├── 📁 pi/                        ← Everything that runs on the Pi Zero
│   ├── duoclock_monitor.py       ← 🧠 Core daemon — serial + timers + logging
│   ├── duoclock_web.py           ← 🌐 Web dashboard — HTTP server + graphs
│   ├── duoclock.conf             ← ⚙️ Configuration file
│   ├── duoclock-monitor.service  ← 🔧 systemd unit for monitor
│   ├── duoclock-web.service      ← 🔧 systemd unit for web
│   ├── install_duoclock.sh       ← 📦 Install/update script (run as root)
│   ├── deploy.sh                 ← 🚀 One-command deploy from dev machine
│   ├── led_test.py               ← 🧪 Interactive LED/button test tool
│   └── serial_diag.py            ← 🔍 Serial diagnostic tool
│
├── 📁 terraform/                 ← Infrastructure as code
│   ├── main.tf                   ← Cloudflare DNS record
│   ├── variables.tf              ← Variable definitions
│   └── terraform.tfvars.example  ← Example variable values
│
├── 📁 include/                   ← PlatformIO headers (empty)
├── 📁 lib/                       ← PlatformIO libraries (empty)
└── 📁 test/                      ← PlatformIO tests (empty)
```

---

## 🚀 Deployment

### 🔥 Quick Deploy (from Windows dev machine)

```bash
# One-command deploy: commits, pushes, SSHs to Pi, pulls, installs
cd pi
bash deploy.sh
```

### 🔧 Manual Deploy

```bash
# On the Pi (SSH in first)
cd ~/mikes.timer && git pull
cd pi
sudo bash install_duoclock.sh
```

### 📦 What install_duoclock.sh Does

1. 📁 Creates `/opt/duoclock/` directory
2. 📋 Copies `duoclock_monitor.py` and `duoclock_web.py` into place
3. 📋 Copies systemd service files to `/etc/systemd/system/`
4. ⚙️ Creates `/etc/duoclock.conf` (only if it doesn't exist)
5. 📝 Creates `/var/log/duoclock.log` with correct permissions
6. 📦 Installs `pyserial` if not present
7. 🔄 Enables and restarts both services

---

## ⚙️ Configuration

Config file: `/etc/duoclock.conf`

```ini
[duoclock]
# ⏱️ LED on-duration in seconds (1800 = 30 minutes)
led_duration = 1800

# 🔌 Serial device: "auto" scans /dev/ttyUSB*, or set explicit path
serial_device = auto

# 📡 Baud rate (must match ESP32 firmware)
baud_rate = 115200

# 📝 Log file for button press events
log_file = /var/log/duoclock.log
```

> ⚠️ **Note:** The install script does NOT overwrite an existing config.
> To apply new defaults, delete `/etc/duoclock.conf` and reinstall,
> or edit it manually.

---

## 🔌 Hardware Setup

### 🛒 Parts List

| Part | Description |
|------|-------------|
| ESP32 DevKit v1 | Microcontroller board |
| 2x Momentary push buttons | THEM (red) and ME (yellow) |
| 2x LEDs + resistors | Red LED on GPIO 16, Yellow LED on GPIO 17 |
| Pi Zero W | Always-on host running the timer logic |
| USB cable | ESP32 to Pi Zero (power + serial) |

### 📌 ESP32 Pin Map

```
ESP32 DevKit v1
┌────────────────────┐
│                    │
│  GPIO 13 ◄── BTN_THEM (to GND, internal pullup)
│  GPIO 15 ◄── BTN_ME   (to GND, internal pullup)
│  GPIO 16 ──► LED_THEM (red, through resistor to GND)
│  GPIO 17 ──► LED_ME   (yellow, through resistor to GND)
│                    │
│  USB ─────────────── to Pi Zero W
│                    │
└────────────────────┘
```

Buttons connect between GPIO and GND (internal pull-up resistors are enabled).
LEDs connect from GPIO through a current-limiting resistor (~220Ω) to GND.

---

## 🧪 Diagnostic Tools

### 🔍 serial_diag.py — Raw Serial Diagnostic

Run on the Pi to send test LED commands and read raw serial output:

```bash
cd ~/mikes.timer/pi
python3 serial_diag.py
```

Sends T1→T0→M1→M0 sequence, then listens for 15 seconds. Useful for verifying
the ESP32 is responding to commands.

### 💡 led_test.py — Interactive Button + LED Test

Run on the Pi for a continuous button→LED feedback loop:

```bash
cd ~/mikes.timer/pi
python3 led_test.py
```

Waits for the device, then lights the corresponding LED for 1 second on each
button press. Useful for verifying buttons and LEDs are wired correctly.

### 📡 serial_read.py — Windows Serial Reader

Run on the Windows dev machine to read raw serial from the ESP32:

```bash
python serial_read.py
```

Reads for 15 seconds. Useful during firmware development.

---

## 🔧 Service Management

```bash
# 📊 Check status
systemctl status duoclock-monitor
systemctl status duoclock-web

# 📋 View live logs (monitor)
journalctl -u duoclock-monitor -f

# 📋 View live logs (web)
journalctl -u duoclock-web -f

# 🔄 Restart services
sudo systemctl restart duoclock-monitor
sudo systemctl restart duoclock-web

# 📝 View event log
tail -f /var/log/duoclock.log
```

---

## 🌍 Infrastructure (Terraform)

The `terraform/` directory manages a Cloudflare DNS A record pointing
`duoclock.belairmoon.au` to the device's IP address.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your Cloudflare token and device IP
terraform init
terraform apply
```

---

## 🧭 Firmware Options

This project supports two firmware approaches for the ESP32:

### 1️⃣ PlatformIO + Arduino (Primary — `src/main.cpp`)

Minimal firmware that acts as a "dumb" serial button box. All timer logic
runs on the Pi. This is the currently deployed firmware.

- ✅ Simple, reliable, fast boot
- ✅ All intelligence on the Pi (easy to update)
- ❌ Requires Pi connection for any functionality

### 2️⃣ ESPHome (Alternative — `esphome/duoclock.yaml`)

Full-featured firmware with WiFi, OTA updates, and Home Assistant integration.
Timer logic runs on the ESP32 itself.

- ✅ Standalone operation (no Pi needed)
- ✅ OTA firmware updates over WiFi
- ✅ Home Assistant integration
- ❌ More complex, timer logic harder to update

---

## 🗺️ Roadmap

### ✅ Milestone 1 — Core Timer + Dashboard (COMPLETE)

- [x] 🔴🟡 Independent 30-minute timers per channel
- [x] ⛔ Both-button cancel
- [x] 📝 Structured event logging
- [x] 🌐 7-day web dashboard with bar graph
- [x] 🚀 Automated deployment pipeline
- [x] 📖 Full documentation

### 🔮 Milestone 2 — Outlook Calendar Integration (PLANNED)

- [ ] 🔑 Entra ID app registration with Graph API permissions
- [ ] 📅 Push timer events to Outlook calendar
- [ ] 🔐 Client credentials flow via Azure Key Vault / HashiCorp Vault
- [ ] 📊 Calendar events as coloured blocks (red/yellow)

---

## 🏠 Network Details

| Host | Address | Purpose |
|------|---------|---------|
| Pi Zero W | `clockradio.belairmoon.au` | Timer host |
| Dashboard | `http://clockradio.belairmoon.au:8080/` | Web UI |
| ESP32 (WiFi) | `10.10.10.235` | OTA updates (ESPHome only) |

---

## 📄 License

Private project — Belair Moon Pty Ltd.
