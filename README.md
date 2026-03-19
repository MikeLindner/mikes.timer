# DuoClock Firmware (mikes.timer)

This repository now contains the ESP32 firmware and hardware-facing tooling for DuoClock.

Pi runtime code (monitor daemon, web dashboard, systemd units, install/update scripts)
was moved to the bm_clockradio repository under duoclock/.

## Current responsibility split

- mikes.timer: ESP32 device firmware and local firmware tooling
- bm_clockradio/duoclock: Pi services, logging, dashboard, deployment

## What is in this repo

- src/main.cpp: ESP32 button/LED serial bridge firmware (dumb I/O device)
- platformio.ini: PlatformIO build/upload config
- esphome/duoclock.yaml: alternate ESPHome firmware variant
- serial_read.py: serial monitor helper for development
- terraform/: Cloudflare DNS helpers
- pi/deploy.sh: compatibility shim that forwards deploy to bm_clockradio/deploy.sh

## What moved out

The following Pi-side runtime files are no longer hosted in this repo:

- duoclock_monitor.py
- duoclock_web.py
- duoclock-monitor.service
- duoclock-web.service
- duoclock.conf
- install_duoclock.sh
- serial_diag.py
- led_test.py

These now live in bm_clockradio/duoclock.

## Deploying DuoClock now

From bm_clockradio:

```bash
./deploy.sh
```

That script updates both LCD and DuoClock services on clockradio.belairmoon.au,
and includes a tar-stream fallback if remote git pull auth fails.

## Firmware behavior summary

The ESP32 firmware in src/main.cpp:

- reads two buttons (THEM and ME)
- sends button press events over USB serial (T, M)
- receives LED commands over serial (T1/T0, M1/M0)
- does not implement timer or logging logic

All timing logic and event logging are executed on the Pi runtime in
bm_clockradio/duoclock.
