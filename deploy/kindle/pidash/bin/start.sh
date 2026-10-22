#!/bin/sh
DIR="$(cd "$(dirname "$0")/.." && pwd)"
[ -f /tmp/pidash.pid ] && kill "$(cat /tmp/pidash.pid)" 2>/dev/null
nohup "$DIR/bin/loop.sh" >/tmp/pidash.log 2>&1 &
echo $! > /tmp/pidash.pid
