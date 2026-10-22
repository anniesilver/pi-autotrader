#!/bin/sh
[ -f /tmp/pidash.pid ] && kill "$(cat /tmp/pidash.pid)" 2>/dev/null
rm -f /tmp/pidash.pid
lipc-set-prop com.lab126.powerd preventScreenSaver 0
start lab126_gui 2>/dev/null
