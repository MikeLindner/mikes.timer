#!/usr/bin/env python3
"""
DuoClock Monitor — listens for button presses from the ESP32 DuoClock box
over USB serial and controls LEDs. All timer logic lives here on the Pi.

Protocol:
  ESP32 → Pi:  "T\n" (THEM pressed)  "M\n" (ME pressed)
  Pi → ESP32:  "T1\n" "T0\n" "M1\n" "M0\n" (LED control)
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
LED_DURATION = 720
SERIAL_DEVICE = "auto"
BAUD_RATE = 115200
LOG_FILE = "/var/log/duoclock.log"

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


def main():
    load_config()
    log = setup_logging()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    log.info("DuoClock monitor starting (led_duration=%ds)", LED_DURATION)

    # Open press log file
    press_log = open(LOG_FILE, "a", buffering=1)

    led_off_timer = None  # threading.Timer for turning LEDs off
    active_led = None     # "T" or "M" — which LED is currently on

    def turn_off_leds(ser):
        nonlocal active_led
        try:
            ser.write(b"T0\n")
            ser.write(b"M0\n")
            active_led = None
            log.info("LED timeout — all off")
        except Exception:
            pass

    while running:
        # --- find / open device ---
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

        # --- read loop ---
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

                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                label = "THEM" if line == "T" else "ME"
                log.info("Button: %s", label)
                press_log.write(f"{ts} {label}\n")

                # Cancel any pending off-timer
                if led_off_timer is not None:
                    led_off_timer.cancel()

                # Light the pressed LED, turn off the other
                if line == "T":
                    ser.write(b"T1\n")
                    ser.write(b"M0\n")
                else:
                    ser.write(b"M1\n")
                    ser.write(b"T0\n")
                active_led = line

                # Schedule LED off after duration
                led_off_timer = threading.Timer(LED_DURATION, turn_off_leds, args=[ser])
                led_off_timer.daemon = True
                led_off_timer.start()

        except serial.SerialException:
            log.warning("Device disconnected")
        except Exception as e:
            log.error("Error: %s", e)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            if led_off_timer is not None:
                led_off_timer.cancel()

        log.info("Reconnecting in 2s...")
        time.sleep(2)

    # cleanup
    press_log.close()
    log.info("DuoClock monitor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
