#!/bin/bash
# TradeLog daily auto-deploy
# Triggered by launchd at 7:30 AM
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$APP_DIR/logs/auto_deploy.log"

echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting auto-deploy" >> "$LOG"

cd "$APP_DIR"

# 1. Generate briefing + build briefings.json
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running build.py..." >> "$LOG"
python3 build.py >> "$LOG" 2>&1

# 2. Stage and commit if anything changed
git add briefings.json
if git diff --cached --quiet; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes to deploy" >> "$LOG"
else
    COMMIT_MSG="Auto briefing $(date '+%Y-%m-%d')"
    git commit -m "$COMMIT_MSG" >> "$LOG" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Committed: $COMMIT_MSG" >> "$LOG"

    # 3. Push → triggers Vercel/Netlify auto-deploy
    git push >> "$LOG" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pushed to remote" >> "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"
