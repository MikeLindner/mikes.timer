#!/usr/bin/env python3
"""
===========================================================================
 🔍 DuoClock Serial Diagnostic Tool
===========================================================================

 Quick diagnostic for verifying ESP32 ↔ Pi serial communication.

 What it does:
   1. Opens /dev/ttyUSB0 at 115200 baud
   2. Sends LED test sequence: T1 → T0 → M1 → M0
   3. Listens for 15 seconds, printing any serial data received

 Usage (on the Pi):
   python3 serial_diag.py

 Expected output:
   - LEDs should flash during the test sequence
   - "DUOCLOCK" identification string on connect
   - Button presses show as "T" or "M"

 ⚠️ Stop duoclock-monitor first to avoid port conflicts:
   sudo systemctl stop duoclock-monitor
===========================================================================
"""
import sys, serial, time

dev = "/dev/ttyUSB0"
print(f"Opening {dev}...", flush=True)
s = serial.Serial(dev, 115200, timeout=0.5)
time.sleep(1)

# Flush any stale data
while s.in_waiting:
    s.read(s.in_waiting)

# Send LED commands to see if device responds
print("Sending T1...", flush=True)
s.write(b"T1\n")
time.sleep(1)
print("Sending T0...", flush=True)
s.write(b"T0\n")
time.sleep(0.5)
print("Sending M1...", flush=True)
s.write(b"M1\n")
time.sleep(1)
print("Sending M0...", flush=True)
s.write(b"M0\n")
time.sleep(0.5)

print("Now reading for 15 seconds (press buttons!)...", flush=True)
end = time.time() + 15
while time.time() < end:
    line = s.readline()
    if line:
        print(f"  RAW: {repr(line)}", flush=True)
print("Done.", flush=True)
s.close()
