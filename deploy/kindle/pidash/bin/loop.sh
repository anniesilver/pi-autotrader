#!/bin/sh
# With STOP_UI=1 the Kindle UI (and KUAL with it) is stopped, so the menu can't be
# used to exit. Instead the loop polls a control file next to the image once a
# minute: when it says "stop", the normal UI comes back. On the Pi:
#   echo stop > state/dash/kindle-control.txt     (remove the file afterwards)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
. "$DIR/pidash.conf"
CONTROL_URL="${DASH_URL%/*}/kindle-control.txt"
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1
[ "$STOP_UI" = "1" ] && stop lab126_gui 2>/dev/null
sleep 5
elapsed=$INTERVAL
while true; do
  if [ "$elapsed" -ge "$INTERVAL" ]; then
    "$DIR/bin/fetch.sh"
    elapsed=0
  fi
  if wget -q -T 10 -O - "$CONTROL_URL" 2>/dev/null | grep -q stop; then
    eips -c
    exec "$DIR/bin/stop.sh"
  fi
  sleep 60
  elapsed=$((elapsed + 60))
done
