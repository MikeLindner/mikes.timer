import serial
import time

s = serial.Serial('COM8', 115200, timeout=1)
s.dtr = False
time.sleep(0.1)
s.dtr = True
time.sleep(0.5)

start = time.time()
while time.time() - start < 15:
    line = s.readline()
    if line and line.strip():
        print(line.decode('utf-8', errors='replace').strip())

s.close()
