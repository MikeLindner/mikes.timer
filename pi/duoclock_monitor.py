#!/usr/bin/env python3
"""
==============================================================================
 🧠 DuoClock Monitor — Core Timer Daemon
==============================================================================

 This is the brain of DuoClock. It runs as a systemd service on the Pi Zero W
 and handles ALL timer logic. The ESP32 is just a dumb button/LED box.

 ┌──────────────────────────────────────────────────────────────────────┐
 │                        DATA FLOW                                     │
 │                                                                      │
 │  ESP32 ──── USB Serial ────► Pi Zero W                               │
 │                                                                      │
 │  Button press on ESP32:                                              │
 │    ESP32 sends "T\n" or "M\n" over serial                           │
 │                                                                      │
 │  This daemon receives it and:                                        │
 │    1. Checks for both-button cancel (within 1s window)               │
 │    2. Turns on the corresponding LED via serial command              │
 │    3. Starts a 30-minute timer for that channel                      │
 │    4. Logs the event to /var/log/duoclock.log                        │
 │                                                                      │
 │  When timer expires:                                                 │
 │    1. Sends LED-off command to ESP32                                 │
 │    2. Logs the timeout event                                         │
 │                                                                      │
 │  Serial Protocol:                                                    │
 │    ESP32 → Pi:  "T\n"  = THEM pressed                               │
 │                 "M\n"  = ME pressed                                  │
 │                 "DUOCLOCK\n" = device ready                          │
 │    Pi → ESP32:  "T1\n" = THEM LED on                                │
 │                 "T0\n" = THEM LED off                                │
 │                 "M1\n" = ME LED on                                   │
 │                 "M0\n" = ME LED off                                  │
 └──────────────────────────────────────────────────────────────────────┘

 Timer Behaviour:
   🔴 T pressed → red/THEM LED on, 30-min timer starts, logged
   🟡 M pressed → yellow/ME LED on, 30-min timer starts, logged
   🔴🟡 Both pressed within 1s → cancel both, all off, logged
   ⏰ Timer expires → individual LED off, logged

 Log Events:
   THEM_ON           — red button pressed, LED activated
   THEM_OFF_TIMEOUT  — 30 minutes elapsed, red LED auto-off
   ME_ON             — yellow button pressed, LED activated
   ME_OFF_TIMEOUT    — 30 minutes elapsed, yellow LED auto-off
   BOTH_CANCEL       — both buttons pressed, everything cancelled

 Config: /etc/duoclock.conf
 Log:    /var/log/duoclock.log
 Service: duoclock-monitor.service
==============================================================================
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

# ===========================================================================
# 📁 Configuration
# ===========================================================================
# The config file lives at /etc/duoclock.conf and is created by the install
# script. If it doesn't exist, these defaults are used instead.
# ===========================================================================

CONFIG_PATH = "/etc/duoclock.conf"

# ---------------------------------------------------------------------------
# Default values — overridden by config file if present
# ---------------------------------------------------------------------------
LED_DURATION = 1800    # ⏱️ 30 minutes in seconds
SERIAL_DEVICE = "auto" # 🔌 "auto" scans /dev/ttyUSB*, or set explicit path
BAUD_RATE = 115200     # 📡 Must match ESP32 firmware (Serial.begin)
LOG_FILE = "/var/log/duoclock.log"  # 📝 Event log (read by web dashboard)

# ---------------------------------------------------------------------------
# Both-button cancel detection window
# ---------------------------------------------------------------------------
# If both T and M arrive within this many seconds of each other, it's
# treated as a "cancel both" gesture rather than two separate activations.
# ---------------------------------------------------------------------------
BOTH_WINDOW = 1.0

# ---------------------------------------------------------------------------
# Global running flag — set to False by SIGTERM/SIGINT signal handler
# to allow clean shutdown when systemd stops the service.
# ---------------------------------------------------------------------------
running = True


def load_config():
    """
    📂 Load configuration from /etc/duoclock.conf
    
    Uses Python's configparser to read an INI-style config file.
    Only overrides globals if the file exists and has values.
    The install script creates a default config, but we gracefully
    handle the case where it's missing.
    """
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
    """
    📋 Set up Python logging to stdout
    
    We log to stdout because systemd captures it via StandardOutput=journal,
    so all our log lines end up in journalctl. No need for a separate
    log file for operational messages — the event log (/var/log/duoclock.log)
    is separate and machine-readable.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("duoclock")


def find_device():
    """
    🔍 Auto-detect the USB serial device
    
    The ESP32 shows up as /dev/ttyUSB0 (via CH340 or CP2102 USB-to-serial
    chip). We just grab the first /dev/ttyUSB* device we find.
    
    Returns None if no device is present (e.g., ESP32 not plugged in).
    The main loop handles this by waiting and retrying.
    """
    for path in sorted(glob.glob("/dev/ttyUSB*")):
        return path
    return None


def signal_handler(signum, _frame):
    """
    🛑 Handle SIGTERM/SIGINT for clean shutdown
    
    systemd sends SIGTERM when stopping a service. We set the running
    flag to False so the main loop exits gracefully, closing the serial
    port and flushing the log file.
    """
    global running
    running = False


def log_event(press_log, event):
    """
    📝 Write a timestamped event to the machine-readable log file
    
    Format: "YYYY-MM-DD HH:MM:SS EVENT_NAME\n"
    
    The log file is opened with line buffering (buffering=1) so each
    write is flushed immediately. This ensures the web dashboard always
    sees the latest events, even if the process crashes.
    
    This log is consumed by:
      - duoclock_web.py (web dashboard)
      - Future: Outlook calendar integration (milestone 2)
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    press_log.write(f"{ts} {event}\n")


def main():
    load_config()
    log = setup_logging()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    log.info("DuoClock monitor starting (led_duration=%ds)", LED_DURATION)

    # -----------------------------------------------------------------------
    # 📝 Open the event log file
    # -----------------------------------------------------------------------
    # buffering=1 = line buffering: each write is flushed after the newline.
    # This is critical because the web dashboard reads this file on every
    # HTTP request, and we need events to be visible immediately.
    # -----------------------------------------------------------------------
    press_log = open(LOG_FILE, "a", buffering=1)

    # -----------------------------------------------------------------------
    # 🔄 Per-channel state tracking
    # -----------------------------------------------------------------------
    # Each channel (T=THEM, M=ME) has independent state:
    #   - timers:     threading.Timer that fires turn_off() after LED_DURATION
    #   - active:     whether the LED is currently on
    #   - last_press: monotonic timestamp of most recent button press
    #   - labels:     human-readable names for log events
    # -----------------------------------------------------------------------
    timers = {"T": None, "M": None}
    active = {"T": False, "M": False}
    last_press = {"T": 0.0, "M": 0.0}
    labels = {"T": "THEM", "M": "ME"}

    def turn_off(ser, channel):
        """
        ⏰ Timer expiry callback — turn off one LED
        
        Called by threading.Timer after LED_DURATION seconds.
        Sends the off command to ESP32 and logs the timeout event.
        
        This runs in a separate thread (Timer's thread), but we only
        write to the serial port and the log file, both of which are
        safe for our use case (single writer, line-buffered).
        """
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
        """
        ⛔ Both-button cancel — turn off everything
        
        Called when both buttons are pressed within BOTH_WINDOW seconds.
        Cancels all pending timers, turns off all LEDs, logs BOTH_CANCEL.
        
        This is the "nevermind" gesture — press both buttons to reset.
        """
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
        """
        💡 Activate a channel — turn on LED + start timer
        
        If the channel is already active, this restarts its timer
        (cancel old timer, start fresh 30-minute countdown).
        
        Steps:
          1. Cancel existing timer (if any) for this channel
          2. Send LED-on command to ESP32
          3. Log the activation event
          4. Start a new 30-minute timer
        
        The timer is a daemon thread so it won't prevent process exit.
        """
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

    # =======================================================================
    # 🔄 Main loop — connect, read, react, reconnect
    # =======================================================================
    # The outer loop handles device discovery and reconnection.
    # The inner loop reads serial lines and processes button events.
    # If the device disconnects, we catch the SerialException and
    # loop back to device discovery after a 2-second wait.
    # =======================================================================
    while running:
        # --- 🔌 Find and open serial device ---
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

        # --- 📡 Serial read loop ---
        try:
            while running:
                line = ser.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue

                # ESP32 sends "DUOCLOCK" on boot — just an identification ping
                if line == "DUOCLOCK":
                    log.info("Device identified: DuoClock")
                    continue

                # Only process T (THEM) and M (ME) button events
                if line not in ("T", "M"):
                    continue

                now = time.monotonic()
                other = "M" if line == "T" else "T"

                # -------------------------------------------------------
                # 🔴🟡 Both-button detection
                # -------------------------------------------------------
                # If the OTHER button was pressed less than BOTH_WINDOW
                # seconds ago, treat this as a "cancel both" gesture.
                # We use monotonic time to avoid issues with clock changes.
                # -------------------------------------------------------
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

    # --- 🧹 Clean shutdown ---
    press_log.close()
    log.info("DuoClock monitor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
