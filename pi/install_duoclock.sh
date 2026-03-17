#!/bin/bash
set -e

if [[ $EUID -ne 0 ]]; then
    echo "Run as root (sudo)" >&2
    exit 1
fi

APP_DIR="/opt/duoclock"

echo "Installing DuoClock monitor..."

# Stop service if running
systemctl is-active --quiet duoclock-monitor.service && systemctl stop duoclock-monitor.service || true

# Install files
mkdir -p "$APP_DIR"
cp duoclock_monitor.py "$APP_DIR/"
chmod 755 "$APP_DIR/duoclock_monitor.py"
cp duoclock_web.py "$APP_DIR/"
chmod 755 "$APP_DIR/duoclock_web.py"

cp duoclock-monitor.service /etc/systemd/system/
chmod 644 /etc/systemd/system/duoclock-monitor.service
cp duoclock-web.service /etc/systemd/system/
chmod 644 /etc/systemd/system/duoclock-web.service

# Default config (don't overwrite if exists)
if [ ! -f /etc/duoclock.conf ]; then
    cp duoclock.conf /etc/duoclock.conf
    chmod 644 /etc/duoclock.conf
    echo "Created /etc/duoclock.conf"
else
    echo "/etc/duoclock.conf already exists, not overwriting"
fi

# Log file
touch /var/log/duoclock.log
chmod 644 /var/log/duoclock.log

# Install pyserial if needed
python3 -c "import serial" 2>/dev/null || pip3 install pyserial

# Enable and start
systemctl daemon-reload
systemctl enable duoclock-monitor.service
systemctl restart duoclock-monitor.service
systemctl enable duoclock-web.service
systemctl restart duoclock-web.service

echo ""
echo "Done! Check status: systemctl status duoclock-monitor"
echo "                    systemctl status duoclock-web"
echo "View log:  tail -f /var/log/duoclock.log"
echo "Dashboard: http://$(hostname).local:8080/"
echo "Config:    /etc/duoclock.conf"
