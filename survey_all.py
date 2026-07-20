"""One-shot full-market survey: sweep every open prod market, group by series."""

import json
import time
from collections import defaultdict

from kalshi_agent.client import KalshiClient
from kalshi_agent.config import Config

c = KalshiClient(Config(env="prod"))
markets, cursor, pages = [], None, 0
while True:
    d = c.get_markets(status="open", limit=200, cursor=cursor)
    batch = d.get("markets", [])
    markets.extend(batch)
    cursor = d.get("cursor")
    pages += 1
    if pages % 10 == 0:
        print(f"  page {pages}, {len(markets)} markets...", flush=True)
    if not cursor or not batch:
        break
    time.sleep(0.5)

series = defaultdict(lambda: {"n": 0, "vol": 0, "vol24": 0, "sample_title": "",
                              "nearest_close": "9999", "priced": 0})
for m in markets:
    s = m["ticker"].split("-")[0]
    e = series[s]
    e["n"] += 1
    e["vol"] += m.get("volume") or 0
    e["vol24"] += m.get("volume_24h") or 0
    if m.get("yes_bid") and m.get("yes_ask"):
        e["priced"] += 1
    if not e["sample_title"]:
        e["sample_title"] = m.get("title") or ""
    ct = m.get("close_time") or "9999"
    if ct < e["nearest_close"]:
        e["nearest_close"] = ct

out = {
    "swept_at": int(time.time()),
    "total_markets": len(markets),
    "total_series": len(series),
    "series": {s: e for s, e in sorted(series.items(), key=lambda kv: -kv[1]["vol24"])},
}
with open(".survey.json", "w") as f:
    json.dump(out, f, indent=1)
print(f"DONE: {len(markets)} open markets across {len(series)} series -> .survey.json")
