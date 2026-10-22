#!/usr/bin/env bash
# One-time setup on a fresh Raspberry Pi OS (64-bit). Run from the repo root:
#   bash deploy/setup_pi.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"

echo "== packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git curl fonts-dejavu-core fonts-noto-cjk

if ! command -v docker >/dev/null; then
  echo "== docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER_NAME"
fi

echo "== python venv"
python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --upgrade pip
"$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"

echo "== config files"
[ -f "$REPO/.env" ] || cp "$REPO/.env.example" "$REPO/.env"
[ -f "$REPO/deploy/gateway.env" ] || cp "$REPO/deploy/gateway.env.example" "$REPO/deploy/gateway.env"
chmod 600 "$REPO/deploy/gateway.env" "$REPO/.env"
mkdir -p "$REPO/deploy/tws_settings" "$REPO/state"

echo "== systemd timer"
for f in pi-autotrader.service pi-autotrader.timer pi-autotrader-dash.service pi-autotrader-dash.timer \
         pi-autotrader-web.service; do
  sed -e "s#__USER__#$USER_NAME#g" -e "s#__REPO__#$REPO#g" "$REPO/deploy/systemd/$f" \
    | sudo tee "/etc/systemd/system/$f" >/dev/null
done
sudo systemctl daemon-reload

cat <<MSG

Done. Next:
  1. Put your PAPER login in deploy/gateway.env
  2. sudo docker compose -f deploy/docker-compose.yml up -d     (start IB Gateway)
  3. .venv/bin/python -m autotrader.run                          (dry run, sends nothing)
  4. sudo systemctl enable --now pi-autotrader.timer             (daily 15:45 ET, still dry run)
  5. sudo systemctl enable --now pi-autotrader-dash.timer pi-autotrader-web.service   (Kindle dashboard)
See docs/PI_SETUP.md for details. Log out and back in once so docker works without sudo.
MSG
