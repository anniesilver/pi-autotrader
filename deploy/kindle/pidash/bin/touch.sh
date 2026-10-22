#!/bin/sh
# Watch the touchscreen and touch /tmp/pidash.tap on every input event.
# loop.sh turns a burst of these into one "next app". Runs only while the
# Kindle UI is stopped, so nothing else is reading the taps.
. "$(dirname "$0")/common.sh"
echo $$ > /tmp/pidash-touch.pid
dev="$TOUCH_DEV"
if [ -z "$dev" ]; then
  dev="$(awk '/^N: Name=/ { name = tolower($0) }
    /^H: Handlers=/ && name ~ /touch|cyttsp|zforce|_mt|elan|cypress/ {
      for (i = 1; i <= NF; i++) if ($i ~ /^event[0-9]+$/) { print "/dev/input/" $i; exit } }' \
    /proc/bus/input/devices 2>/dev/null)"
fi
[ -z "$dev" ] && dev=/dev/input/event1
# Saved for troubleshooting: shows up on the Kindle's USB drive
{ echo "touch device used: $dev"; echo; cat /proc/bus/input/devices; } > /mnt/us/pidash-input.txt 2>/dev/null
echo "touch: $dev"
while true; do
  # 64 bytes holds whole events whether they are 16 or 24 bytes long
  if dd if="$dev" of=/dev/null bs=64 count=1 2>/dev/null; then
    : > /tmp/pidash.tap
  else
    sleep 5
  fi
done
