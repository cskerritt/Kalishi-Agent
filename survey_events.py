"""Sweep open events to map series -> category."""

import json
import time
from collections import Counter

from kalshi_agent.client import KalshiClient
from kalshi_agent.config import Config

c = KalshiClient(Config(env="prod"))
events, cursor, pages = [], None, 0
while True:
    d = c._request("GET", "/events", params={"status": "open", "limit": 200,
                                             **({"cursor": cursor} if cursor else {})},
                   signed=False)
    batch = d.get("events", [])
    events.extend(batch)
    cursor = d.get("cursor")
    pages += 1
    if pages % 10 == 0:
        print(f"  page {pages}, {len(events)} events...", flush=True)
    if not cursor or not batch:
        break
    time.sleep(0.6)

series_cat = {}
cat_counts = Counter()
for e in events:
    s = e.get("series_ticker") or e.get("event_ticker", "").split("-")[0]
    cat = e.get("category") or "?"
    series_cat.setdefault(s, cat)
    cat_counts[cat] += 1

with open(".events_categories.json", "w") as f:
    json.dump({"series_cat": series_cat, "event_counts_by_category": dict(cat_counts)},
              f, indent=1)
print(f"DONE-EVENTS: {len(events)} events, {len(series_cat)} series, "
      f"categories: {dict(cat_counts.most_common())}")
