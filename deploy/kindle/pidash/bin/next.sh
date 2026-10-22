#!/bin/sh
# Show the next app in APPS.
. "$(dirname "$0")/common.sh"
cur="$(current_app)"
next_app > "$APP_FILE"
"$DIR/bin/fetch.sh"
