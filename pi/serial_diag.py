#!/usr/bin/env python3
"""Quick serial diagnostic - reads output and sends test commands."""
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
