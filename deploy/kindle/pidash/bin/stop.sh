#!/bin/sh
# The loop ignores TERM (so stopping the UI can't kill it), hence KILL here.
[ -f /tmp/pidash.pid ] && kill -9 "$(cat /tmp/pidash.pid)" 2>/dev/null
[ -f /tmp/pidash-touch.pid ] && kill -9 "$(cat /tmp/pidash-touch.pid)" 2>/dev/null
# A dd blocked on the touchscreen outlives its parent; it exits at the next tap
rm -f /tmp/pidash.pid /tmp/pidash-touch.pid /tmp/pidash.tap
lipc-set-prop com.lab126.powerd preventScreenSaver 0
start lab126_gui 2>/dev/null
