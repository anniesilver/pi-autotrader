# Kindle Voyage dashboard

![demo](dashboard-demo.png)

Every 15 minutes the Pi renders `state/status.json` and the trade journal into a 1072×1448 grayscale PNG and serves it on port 8080. The Kindle fetches the image over WiFi and draws it full screen with `eips`.

The dashboard shows:

- Mode (PAPER, DRY RUN or LIVE) and the last run's result. The result is shown inverted when something needs attention, or when there has been no run for 4 days.
- Equity, SPY, VIX, and leverage, with a gauge marking the 1.5x high-VIX limit.
- Shares, cash, and open calls with their distance from SPY.
- The next dip-buy price, an equity sparkline, the last run's orders, and the month-end date.

## Pi side

`deploy/setup_pi.sh` installs the units. Enable them with:

```bash
sudo systemctl enable --now pi-autotrader-dash.timer pi-autotrader-web.service
curl -sI http://localhost:8080/dashboard.png      # 200 OK
hostname -I                                        # the Pi's IP, for the Kindle
```

To preview the layout without any data, run `python -m autotrader.dashboard --demo`.

The image server is reachable by anything on your home network, and the picture shows account numbers. Don't forward port 8080 on the router. If you want the Pi's IP to stay fixed, give it a DHCP reservation in the router.

## Kindle side

The Kindle needs to be jailbroken first, with KUAL installed (WatchThis for firmware 5.13.6).

1. Edit `deploy/kindle/pidash/pidash.conf` and set `SERVER` to `http://<pi-ip>:8080`.
2. Connect the Kindle over USB and copy the whole `deploy/kindle/pidash` folder to `extensions/pidash` on the Kindle drive.
3. Eject the Kindle, open **KUAL → Pi Dashboard → Start (trading dashboard)**.

The Kindle's own UI stops and the dashboard appears. It refreshes every `INTERVAL` seconds (default 900).

## Several apps, tap to switch

The Kindle can show more than one page. Each "app" is a PNG the server renders, listed in `APPS` in `pidash.conf` (default `dashboard tasks`); app `name` is fetched from `$SERVER/name.png`. Adding an app means rendering one more PNG into `state/dash/` and adding its name to `APPS`.

- **Tap anywhere on the screen** to show the next app (with `STOP_UI=1` and `TAP_SWITCH=1`). The page changes within a couple of seconds, after the full-screen flash.
- **KUAL → Start (task list)** starts on a given app.
- **From the server**, put `app tasks` in `kindle-control.txt`. The Kindle switches within a minute, once per change of the file, so taps still work afterwards.

Tap switching reads the touchscreen directly (`bin/touch.sh`), which only works while the Kindle UI is stopped. The device is found in `/proc/bus/input/devices`; the one it picked, and the full device list, are saved to `pidash-input.txt` on the Kindle's USB drive. If taps don't switch, set `TOUCH_DEV` in `pidash.conf` from that file.

### Task list

`python -m autotrader.tasks_page` renders `state/tasks.json` (the 下周任务清单 artifact's tasks: `title`, `due`, `progress`, `order`) or, failing that, a plain `state/tasks.txt` into `state/dash/tasks.png`. The `pi-autotrader-dash` service renders it with the dashboard. Chinese text needs `fonts-noto-cjk` (installed by `setup_pi.sh`); on Windows it uses Microsoft YaHei.

### Getting the normal Kindle back

With `STOP_UI=1`, KUAL stops along with the rest of the Kindle UI, so its **Stop** item can't be reached while the dashboard is up. To exit, tell the Kindle from the Pi:

```bash
echo stop > state/dash/kindle-control.txt   # within a minute the Kindle UI comes back
rm state/dash/kindle-control.txt            # clear it, or the next Start stops right away
```

If the Pi isn't reachable, hold the Kindle's power button for about 20 seconds to force a reboot. The dashboard doesn't auto-start, so it comes back as a normal Kindle.

With `STOP_UI=0` the Kindle UI keeps running and the KUAL menu items work (use **Next app** to switch, since taps go to the Kindle UI), but the UI may now and then draw over the dashboard until the next refresh. **Refresh now** redraws once, about 5 seconds after KUAL closes.

Keep the Kindle plugged in, ideally into one of the Pi's USB ports. The loop keeps WiFi on and the screensaver off, so the battery would run down in a few days otherwise.

If the screen shows `pidash: can't reach ...`, check the IP in `pidash.conf`, check that the Kindle is on the same WiFi, and run `systemctl status pi-autotrader-web` on the Pi.
