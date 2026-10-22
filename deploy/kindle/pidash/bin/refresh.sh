#!/bin/sh
# KUAL's "Refresh now": wait for KUAL to close and the home screen to finish
# drawing, then draw the dashboard, so the Kindle UI doesn't paint over it.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
if command -v setsid >/dev/null 2>&1; then
  setsid sh -c "sleep 5; '$DIR/bin/fetch.sh'" </dev/null >/dev/null 2>&1 &
else
  (sleep 5; "$DIR/bin/fetch.sh") </dev/null >/dev/null 2>&1 &
fi
