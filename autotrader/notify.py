"""Push notifications through ntfy.sh (free, no account; install the ntfy app and subscribe to the topic)."""

import logging
import urllib.request

log = logging.getLogger(__name__)


def notify(topic: str, title: str, message: str, priority: str = "default"):
    if not topic:
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode(),
        headers={"Title": title, "Priority": priority},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # a failed notification must never stop the bot
        log.warning("ntfy failed: %s", e)
