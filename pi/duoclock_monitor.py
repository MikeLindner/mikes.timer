#!/usr/bin/env python3
"""
DuoClock Monitor — listens for button presses from the ESP32 DuoClock box
over USB serial, controls LEDs with independent 30-minute timers, and logs
all events to a file for consumption by other systems.

Protocol:
  ESP32 → Pi:  "T\n" (THEM pressed)  "M\n" (ME pressed)
  Pi → ESP32:  "T1\n" "T0\n" "M1\n" "M0\n" (LED control)

Timer behaviour:
  - T pressed: red/THEM LED on, 30-min timer starts, logged
  - M pressed: yellow/ME LED on, 30-min timer starts, logged
  - Both can be active independently with separate timers
  - If both buttons arrive within 1s of each other: cancel both, all off
  - Timer expiry turns the individual LED off and logs it
"""

import configparser
import glob
import logging
import os
import signal
import sys
import threading
import time

import serial

CONFIG_PATH = "/etc/duoclock.conf"

# Defaults (overridden by config file)
LED_DURATION = 1800  # 30 minutes
SERIAL_DEVICE = "auto"
BAUD_RATE = 115200
LOG_FILE = "/var/log/duoclock.log"
BOTH_WINDOW = 1.0  # seconds — if both buttons within this window, cancel both

running = True


def load_config():
    global LED_DURATION, SERIAL_DEVICE, BAUD_RATE, LOG_FILE
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH)
        s = cfg["duoclock"] if "duoclock" in cfg else {}
        LED_DURATION = int(s.get("led_duration", LED_DURATION))
        SERIAL_DEVICE = s.get("serial_device", SERIAL_DEVICE)
        BAUD_RATE = int(s.get("baud_rate", BAUD_RATE))
        LOG_FILE = s.get("log_file", LOG_FILE)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("duoclock")


def find_device():
    """Auto-detect CH340/CP2102 USB-serial device."""
    for path in sorted(glob.glob("/dev/ttyUSB*")):
        return path
    return None


def signal_handler(signum, _frame):
    global running
    running = False


def log_event(press_log, event):
    """Write a timestamped line to the event log file."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    press_log.write(f"{ts} {event}\n")


def main():
    load_config()
    log = setup_logging()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    log.info("DuoClock monitor starting (led_duration=%ds)", LED_DURATION)

    press_log = open(LOG_FILE, "a", buffering=1)

    # Independent state per channel
    timers = {"T": None, "M": None}       # threading.Timer
    active = {"T": False, "M": False}     # is LED currently on?
    last_press = {"T": 0.0, "M": 0.0}     # monotonic timestamp of last press
    labels = {"T": "THEM", "M": "ME"}

    def turn_off(ser, channel):
        """Called by timer expiry — turn off one LED."""
        try:
            ser.write(f"{channel}0\n".encode())
        except Exception:
            pass
        active[channel] = False
        timers[channel] = None
        event = f"{labels[channel]}_OFF_TIMEOUT"
        log.info(event)
        log_event(press_log, event)

    def cancel_all(ser):
        """Cancel both timers, turn off both LEDs."""
        for ch in ("T", "M"):
            if timers[ch] is not None:
                timers[ch].cancel()
                timers[ch] = None
            active[ch] = False
            try:
                ser.write(f"{ch}0\n".encode())
            except Exception:
                pass
        log.info("BOTH_CANCEL")
        log_event(press_log, "BOTH_CANCEL")

    def activate(ser, channel):
        """Turn on one LED, start its 30-min timer."""
        # Cancel existing timer for this channel if any
        if timers[channel] is not None:
            timers[channel].cancel()

        try:
            ser.write(f"{channel}1\n".encode())
        except Exception:
            pass
        active[channel] = True

        event = f"{labels[channel]}_ON"
        log.info(event)
        log_event(press_log, event)

        t = threading.Timer(LED_DURATION, turn_off, args=[ser, channel])
        t.daemon = True
        t.start()
        timers[channel] = t

    while running:
        device = SERIAL_DEVICE
        if device == "auto":
            device = find_device()
        if device is None:
            log.debug("No device found, waiting...")
            time.sleep(2)
            continue

        try:
            ser = serial.Serial(device, BAUD_RATE, timeout=1)
            log.info("Connected to %s", device)
        except Exception as e:
            log.warning("Cannot open %s: %s", device, e)
            time.sleep(2)
            continue

        try:
            while running:
                line = ser.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue

                if line == "DUOCLOCK":
                    log.info("Device identified: DuoClock")
                    continue

                if line not in ("T", "M"):
                    continue

                now = time.monotonic()
                other = "M" if line == "T" else "T"

                # Detect both-pressed: other button was pressed within window
                if now - last_press[other] < BOTH_WINDOW:
                    cancel_all(ser)
                    last_press["T"] = 0.0
                    last_press["M"] = 0.0
                    continue

                last_press[line] = now
                activate(ser, line)

        except serial.SerialException:
            log.warning("Device disconnected")
        except Exception as e:
            log.error("Error: %s", e)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            for ch in ("T", "M"):
                if timers[ch] is not None:
                    timers[ch].cancel()

        log.info("Reconnecting in 2s...")
        time.sleep(2)

    press_log.close()
    log.info("DuoClock monitor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
