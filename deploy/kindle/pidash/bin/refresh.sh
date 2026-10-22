#!/bin/sh
# KUAL's "Refresh now" / "Next app": wait for KUAL to close and the home screen
# to finish drawing, then draw, so the Kindle UI doesn't paint over it.
# refresh.sh next = show the next app instead of the current one.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cmd="$DIR/bin/fetch.sh"
[ "$1" = "next" ] && cmd="$DIR/bin/next.sh"
if command -v setsid >/dev/null 2>&1; then
  setsid sh -c "sleep 5; '$cmd'" </dev/null >/dev/null 2>&1 &
else
  (sleep 5; "$cmd") </dev/null >/dev/null 2>&1 &
fi
