#!/bin/sh
# Launch loop.sh detached from KUAL. KUAL runs inside the lab126_gui job, and
# `stop lab126_gui` signals that whole process group, so the loop needs its own
# session or it dies the moment it stops the UI.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
[ -f /tmp/pidash.pid ] && kill -9 "$(cat /tmp/pidash.pid)" 2>/dev/null
if command -v setsid >/dev/null 2>&1; then
  setsid "$DIR/bin/loop.sh" </dev/null >/tmp/pidash.log 2>&1 &
elif command -v start-stop-daemon >/dev/null 2>&1; then
  start-stop-daemon -S -b -x "$DIR/bin/loop.sh"
else
  nohup "$DIR/bin/loop.sh" </dev/null >/tmp/pidash.log 2>&1 &
fi
