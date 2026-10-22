#!/bin/sh
# The loop ignores TERM (so stopping the UI can't kill it), hence KILL here.
[ -f /tmp/pidash.pid ] && kill -9 "$(cat /tmp/pidash.pid)" 2>/dev/null
rm -f /tmp/pidash.pid
lipc-set-prop com.lab126.powerd preventScreenSaver 0
start lab126_gui 2>/dev/null
