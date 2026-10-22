# Sourced by the other scripts: config, plus the current-app helpers.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
. "$DIR/pidash.conf"
# Older configs had a single DASH_URL=http://host:8080/dashboard.png
[ -z "$SERVER" ] && [ -n "$DASH_URL" ] && SERVER="${DASH_URL%/*}"
[ -z "$APPS" ] && APPS="dashboard"
APP_FILE=/tmp/pidash.app

current_app() {
  app="$(cat "$APP_FILE" 2>/dev/null)"
  for a in $APPS; do [ "$a" = "$app" ] && { echo "$a"; return; }; done
  set -- $APPS
  echo "$1"
}

# The app after $cur in APPS, wrapping around.
next_app() {
  set -- $APPS
  first="$1"
  while [ $# -gt 0 ]; do
    if [ "$1" = "$cur" ]; then
      [ $# -gt 1 ] && echo "$2" || echo "$first"
      return
    fi
    shift
  done
  echo "$first"
}
