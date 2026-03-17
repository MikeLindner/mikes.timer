#!/usr/bin/env python3
"""Continuous button+LED test for DuoClock on Pi."""
import sys, serial, glob, time

def log(msg):
    print(msg)
    sys.stdout.flush()

log("--- Waiting for USB device... plug in the duoclock ---")
dev = None
while dev is None:
    devs = sorted(glob.glob("/dev/ttyUSB*"))
    if devs:
        dev = devs[0]
    else:
        time.sleep(1)

log(f"Found {dev}, connecting...")
time.sleep(1)
s = serial.Serial(dev, 115200, timeout=0.1)
time.sleep(2)
while s.in_waiting:
    s.read(s.in_waiting)
log("--- CONTINUOUS BUTTON+LED TEST - press buttons (Ctrl+C to stop) ---")
count = 0
while True:
    line = s.readline()
    if line and line.strip():
        txt = line.decode("utf-8", errors="replace").strip()
        count += 1
        if txt == "T":
            s.write(b"T1\n")
            log(f"#{count} THEM pressed -> LED on")
            time.sleep(1)
            s.write(b"T0\n")
        elif txt == "M":
            s.write(b"M1\n")
            log(f"#{count} ME pressed -> LED on")
            time.sleep(1)
            s.write(b"M0\n")
        else:
            log(f"#{count} Got: {txt}")
