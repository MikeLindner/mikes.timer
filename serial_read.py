#!/usr/bin/env python3
"""
===========================================================================
 📟 DuoClock Serial Reader — Windows-side serial monitor
===========================================================================

 Quick-and-dirty serial reader for the dev machine (Windows).
 Connects to the ESP32 on COM8, triggers a DTR reset (reboots the
 ESP32), then reads serial output for 15 seconds.

 This is a development/debug tool — not deployed to the Pi.
 The Pi equivalent is pi/serial_diag.py.

 Usage:
   python serial_read.py

 Requires:
   pip install pyserial
===========================================================================
"""
import serial
import time

# ---------------------------------------------------------------------------
# 🔌 Connect to ESP32 on COM8 at 115200 baud
# ---------------------------------------------------------------------------
# timeout=1 means readline() waits up to 1 second for data
s = serial.Serial('COM8', 115200, timeout=1)

# ---------------------------------------------------------------------------
# 🔄 DTR reset — reboots the ESP32 so we see startup messages
# ---------------------------------------------------------------------------
# Toggling DTR triggers the ESP32's auto-reset circuit.
# The 0.1s LOW + 0.5s HIGH gives the bootloader time to start.
s.dtr = False
time.sleep(0.1)
s.dtr = True
time.sleep(0.5)

# ---------------------------------------------------------------------------
# 📖 Read loop — capture 15 seconds of serial output
# ---------------------------------------------------------------------------
start = time.time()
while time.time() - start < 15:
    line = s.readline()
    if line and line.strip():
        print(line.decode('utf-8', errors='replace').strip())

s.close()
