#!/bin/sh
# Download the current app's page once and draw it full screen.
# With an argument, switch to that app first: fetch.sh tasks
. "$(dirname "$0")/common.sh"
[ -n "$1" ] && echo "$1" > "$APP_FILE"
app="$(current_app)"
url="$SERVER/$app.png"
if wget -q -T 30 -O /tmp/pidash.png "$url"; then
  eips -f -g /tmp/pidash.png
else
  eips -c
  eips 2 2 "pidash: can't reach $url ($(date +%H:%M))"
fi
