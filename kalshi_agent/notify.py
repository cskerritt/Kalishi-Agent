"""Push notifications via ntfy.sh (zero-signup topic-based push).

Subscribe on the ntfy mobile app (or https://ntfy.sh/<topic>) to receive.
Topic comes from NTFY_TOPIC; if unset, notifications just log to stdout.
"""

from __future__ import annotations

import os

import requests


def notify(title: str, message: str, priority: str = "default") -> None:
    print(f"[notify] {title}: {message}", flush=True)
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode(),
            headers={"Title": title, "Priority": priority},
            timeout=15,
        )
    except Exception as e:  # notifications must never crash the scheduler
        print(f"[notify] failed: {e}", flush=True)
