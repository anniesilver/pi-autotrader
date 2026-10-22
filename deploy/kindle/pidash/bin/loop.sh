#!/bin/sh
# With STOP_UI=1 the Kindle UI (and KUAL with it) is stopped, so the menu can't be
# used. Instead:
#   - a tap anywhere on the screen shows the next app (TAP_SWITCH=1)
#   - once a minute the loop reads kindle-control.txt next to the pages:
#       stop         -> the normal Kindle UI comes back
#       app tasks    -> show that app (acted on when the file changes)
trap '' TERM HUP
echo $$ > /tmp/pidash.pid
. "$(dirname "$0")/common.sh"
CONTROL_URL="$SERVER/kindle-control.txt"
TAP=/tmp/pidash.tap
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1
[ "$STOP_UI" = "1" ] && stop lab126_gui 2>/dev/null
sleep 5
rm -f "$TAP"
if [ "$STOP_UI" = "1" ] && [ "$TAP_SWITCH" = "1" ]; then
  "$DIR/bin/touch.sh" </dev/null >>/tmp/pidash.log 2>&1 &
fi
elapsed=$INTERVAL
since_control=60
last_control=""
while true; do
  if [ -f "$TAP" ]; then
    # One tap is a burst of events: wait until it has been quiet for a second
    while [ -f "$TAP" ]; do rm -f "$TAP"; sleep 1; done
    "$DIR/bin/next.sh"
    rm -f "$TAP"
    elapsed=0
  fi
  if [ "$elapsed" -ge "$INTERVAL" ]; then
    "$DIR/bin/fetch.sh"
    elapsed=0
  fi
  if [ "$since_control" -ge 60 ]; then
    since_control=0
    control="$(wget -q -T 10 -O - "$CONTROL_URL" 2>/dev/null)"
    if echo "$control" | grep -q stop; then
      eips -c
      rm -f /tmp/pidash.pid
      "$DIR/bin/stop.sh"
      exit 0
    fi
    if [ "$control" != "$last_control" ]; then
      app="$(echo "$control" | sed -n 's/^app[[:space:]]*\([A-Za-z0-9_-]*\).*/\1/p' | head -n 1)"
      if [ -n "$app" ]; then
        "$DIR/bin/fetch.sh" "$app"
        elapsed=0
      fi
      last_control="$control"
    fi
  fi
  sleep 1
  elapsed=$((elapsed + 1))
  since_control=$((since_control + 1))
done
