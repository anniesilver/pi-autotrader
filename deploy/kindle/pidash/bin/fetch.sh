#!/bin/sh
# Download the dashboard once and draw it full screen.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
. "$DIR/pidash.conf"
if wget -q -T 30 -O /tmp/pidash.png "$DASH_URL"; then
  eips -f -g /tmp/pidash.png
else
  eips 2 2 "pidash: can't reach $DASH_URL ($(date +%H:%M))"
fi
