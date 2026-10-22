# Raspberry Pi setup

Target: Raspberry Pi 5 (8 GB recommended, 4 GB works) or Pi 4 with 4 GB or more, running Raspberry Pi OS Lite 64-bit. IB Gateway runs in Docker ([gnzsnz/ib-gateway](https://github.com/gnzsnz/ib-gateway-docker), which ships arm64 images and has IBC built in for automatic login). The bot runs from a Python venv on a systemd timer.

## 1. Before you start: IB paper account

In IBKR Client Portal, open **Settings → Paper Trading Account**:

- Note the **paper username** (it's different from your live one) and reset its password if needed.
- Turn on **Share real-time market data with paper account**. Without it, the bot only sees delayed prices, and option quotes need your OPRA subscription.

Paper logins normally don't ask for two-factor authentication, which is what lets the Pi log in by itself.

## 2. Flash the SD card

1. In Raspberry Pi Imager, choose **Raspberry Pi OS Lite (64-bit)**.
2. Under the gear/edit settings, set the hostname (e.g. `autotrader`), a user and password, WiFi, and **enable SSH**.
3. Boot the Pi and connect with `ssh <user>@autotrader.local`.

Optional but nice: an active cooler on a Pi 5, and wired Ethernet if the router is close.

## 3. Get the code

The repo is private, so log in to GitHub on the Pi first:

```bash
sudo apt-get install -y gh && gh auth login        # choose HTTPS, log in via browser code
gh repo clone anniesilver/pi-autotrader && cd pi-autotrader
bash deploy/setup_pi.sh
```

`setup_pi.sh` installs Docker and Python, creates `.venv`, copies `.env` and `deploy/gateway.env` from their examples (mode 600, never committed), and installs the systemd timer without enabling it. Log out and back in once afterwards.

## 4. Start IB Gateway

```bash
nano deploy/gateway.env                   # TWS_USERID / TWS_PASSWORD = the PAPER login
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml logs -f   # wait for "Login has completed"
```

The API listens on `127.0.0.1:4002` only. If login gets stuck, set `VNC_SERVER_PASSWORD`, restart the container, run `ssh -L 5900:localhost:5900 <user>@autotrader.local` from your computer, and open a VNC viewer on `localhost:5900` to see the Gateway window.

## 5. Check the connection

```bash
.venv/bin/python -m autotrader.run --check
```

You should see the `DU…` account, `"paper": true`, live SPY and VIX numbers, cash, and the month's last trading day. If prices come back empty, re-check the market data sharing from step 1.

## 6. Dry runs, then paper orders

```bash
.venv/bin/python -m autotrader.run            # dry run: decides and reports, sends nothing
sudo systemctl enable --now pi-autotrader.timer
systemctl list-timers pi-autotrader.timer     # next run: 15:45 New York time, Mon-Fri
```

The timer runs `autotrader.run` with whatever `.env` says, and `DRY_RUN=1` is the default. After a few dry runs that look right (check `state/status.json` and `state/bot.log`), set `DRY_RUN=0` in `.env` and the next 15:45 run places real **paper** orders.

## Day to day

| What | How |
|---|---|
| Stop all trading now | `touch state/STOP` (remove the file to resume) |
| Latest result | `cat state/status.json` |
| Every run and order | `state/journal.jsonl` |
| Bot log | `state/bot.log`, or `journalctl -u pi-autotrader` |
| Gateway log | `docker compose -f deploy/docker-compose.yml logs --tail 100` |
| Phone alerts | set `NTFY_TOPIC` in `.env`, subscribe in the ntfy app |
| Update the code | `git pull && .venv/bin/pip install -r requirements.txt` |

The Pi's own time zone doesn't matter: the timer and the bot both use New York time.
