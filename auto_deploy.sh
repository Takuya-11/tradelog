#!/bin/bash
# TradeLog daily auto-deploy
# Triggered by launchd at 7:30 AM
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$APP_DIR/logs/auto_deploy.log"
mkdir -p "$APP_DIR/logs"

# Absolute paths (launchd has minimal PATH)
PYTHON=/opt/homebrew/bin/python3
VERCEL=/opt/homebrew/bin/vercel
GIT=/usr/bin/git

VERCEL_TOKEN="${VERCEL_TOKEN:-}"
VERCEL_SCOPE="${VERCEL_SCOPE:-tacucompany}"

echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting auto-deploy" >> "$LOG"

cd "$APP_DIR"

# 1. Generate briefing + build briefings.json
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running build.py..." >> "$LOG"
"$PYTHON" build.py >> "$LOG" 2>&1

# 2. Stage and commit if anything changed
"$GIT" add briefings.json buzz.json
if "$GIT" diff --cached --quiet; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes to deploy" >> "$LOG"
else
    COMMIT_MSG="Auto briefing $(date '+%Y-%m-%d')"
    "$GIT" commit -m "$COMMIT_MSG" >> "$LOG" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Committed: $COMMIT_MSG" >> "$LOG"

    # 3. Push to GitHub
    "$GIT" push >> "$LOG" 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pushed to GitHub" >> "$LOG"

    # 4. Deploy to Vercel
    if [ -n "$VERCEL_TOKEN" ]; then
        "$VERCEL" deploy --prod \
            --token "$VERCEL_TOKEN" \
            --scope "$VERCEL_SCOPE" \
            --cwd "$APP_DIR" >> "$LOG" 2>&1
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deployed to Vercel" >> "$LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] VERCEL_TOKEN not set — skipping deploy" >> "$LOG"
    fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"
