#!/bin/sh
DIR="$(cd "$(dirname "$0")/.." && pwd)"
. "$DIR/pidash.conf"
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1
[ "$STOP_UI" = "1" ] && stop lab126_gui 2>/dev/null
sleep 5
while true; do
  "$DIR/bin/fetch.sh"
  sleep "$INTERVAL"
done
