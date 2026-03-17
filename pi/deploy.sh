#!/bin/bash
# ===========================================================================
# 🚀 DuoClock Deploy — One-command deployment from dev machine to Pi
# ===========================================================================
#
# This script does everything needed to deploy changes:
#   1. Commits and pushes any local changes to GitHub
#   2. SSHs into the Pi Zero W
#   3. Pulls the latest code from GitHub
#   4. Runs the install script to update services
#
# Usage (from the pi/ directory or repo root):
#   bash pi/deploy.sh
#
# Prerequisites:
#   - SSH key auth configured for michael@clockradio.belairmoon.au
#   - Git remote set up and authenticated
#
# ===========================================================================
set -e

# ---------------------------------------------------------------------------
# 🏠 Target Pi connection details
# ---------------------------------------------------------------------------
PI_HOST="clockradio.belairmoon.au"
PI_USER="michael"
REPO_DIR="mikes.timer"

echo "=== DuoClock Deploy ==="

# ---------------------------------------------------------------------------
# 📤 Step 1: Commit and push any pending changes
# ---------------------------------------------------------------------------
# We commit everything with a timestamped message. If there's nothing to
# commit, we just push (in case there are unpushed commits).
# ---------------------------------------------------------------------------
echo ""
echo "--- Pushing to git ---"
cd "$(dirname "$0")/.."
git add -A
git diff --cached --quiet && echo "Nothing to commit" || git commit -m "deploy: $(date '+%Y-%m-%d %H:%M')"
git push || echo "Push failed or nothing to push"

# ---------------------------------------------------------------------------
# 📥 Step 2: SSH into Pi, pull latest, install
# ---------------------------------------------------------------------------
# The remote script:
#   - Clones the repo if it doesn't exist yet (first-time setup)
#   - Pulls latest changes
#   - Runs install_duoclock.sh which handles file copying + service restart
# ---------------------------------------------------------------------------
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
