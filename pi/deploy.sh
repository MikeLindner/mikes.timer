#!/bin/bash
set -e

PI_HOST="clockradio.belairmoon.au"
PI_USER="michael"
REPO_DIR="mikes.timer"

echo "=== DuoClock Deploy ==="

# Step 1: Git push
echo ""
echo "--- Pushing to git ---"
cd "$(dirname "$0")/.."
git add -A
git diff --cached --quiet && echo "Nothing to commit" || git commit -m "deploy: $(date '+%Y-%m-%d %H:%M')"
git push || echo "Push failed or nothing to push"

# Step 2: Deploy to Pi
echo ""
echo "--- Deploying to Pi ---"
ssh "${PI_USER}@${PI_HOST}" bash -s <<'REMOTE'
set -e
cd ~/mikes.timer 2>/dev/null || { git clone https://github.com/MikeLindner/mikes.timer.git ~/mikes.timer && cd ~/mikes.timer; }
git pull
cd pi
sudo bash install_duoclock.sh
echo ""
echo "=== Deploy complete ==="
systemctl status duoclock-monitor --no-pager -l || true
REMOTE
