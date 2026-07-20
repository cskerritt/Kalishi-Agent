# Kalshi Trading Agent — working notes for Claude

## The discipline (Chris's standing instructions)

1. **Every live bet goes in the journal** — `execute --live` records
   automatically; manual `client.create_order` calls must call
   `journal.record_bet` with thesis + model snapshot.
2. **After settlements** (`settle` command), every LOST bet gets a written
   post-mortem in its journal entry: what the model believed, what happened,
   and whether the loss was variance (thesis sound, dice bad) or model error
   (fix something). Never skip this.
3. **Every model improvement updates this file** — add a changelog line and
   revise the "Current model" section so the next session starts from the
   real state, not an old one.
4. **Feasible-edge policy** (see RESEARCH.md): net edge ≥ 8c after taker fee,
   ≥ 2c per day of capital lockup, sigma-robust, explainable counterparty.
5. **Bankroll $800** (prod, when unblocked): high conviction ≈ 3% ($24),
   moderate ≈ 1% ($8), practice ≈ 1%. Hard caps in `.env`: $25/order,
   $80/day. Dry-run is the default everywhere; `--live` is explicit.

## Daily workflow

```bash
python -m kalshi_agent weather --min-edge 10   # temperature edges vs NWS
python -m kalshi_agent scan --hours 30         # liquid snapshot (prod prices)
# analyst (Claude in-session) writes picks.json -> Chris picks numbers
python -m kalshi_agent execute 1 3 --live      # place through risk rails
python -m kalshi_agent settle                  # pull results into journal
python -m kalshi_agent journal                 # track record + stats
```

Sports: compare vs devigged book lines (ESPN scoreboard API,
`site.api.espn.com/.../scoreboard?dates=YYYYMMDD`, `details` = favorite's ML).
Liquid winners are pinned to books — only thin markets or line-drift are
tradable (RESEARCH.md).

## Current model (2026-07-19)

- **Weather fair value**: normal forecast-error model on NWS point forecasts
  (`api.weather.gov`); sigma by horizon {0d: 2.0, 1d: 2.8, 2d: 3.5, 3d: 4.2,
  4d: 4.8, 5d: 5.4, 6d: 5.9}°F. Continuity-corrected at half-degrees.
  Low-temp series use overnight periods attributed to the morning they end on.
- **Known weakness**: sigma is generic, not per-city/per-regime. The market
  prices ATM bands with sigma ≈ 1.5°F; our band flags against the modal band
  are usually artifacts. TRUST: threshold strikes far from forecast, cheap
  YES on bands at/adjacent to the NWS number. DISTRUST: buy-NO-on-modal-band.
- **Fees**: taker fee = 7% × P × (1−P) per contract, netted in the scanner.
- **Sports**: no in-house model; devig consensus is the benchmark.

## API gotchas (hard-won)

- Order placement is v2: `POST /portfolio/events/orders`, YES-leg bid/ask
  model (NO mirrors to 100−price), dollar-string prices, `time_in_force`
  required. Legacy `POST /portfolio/orders` returns 410. Cancel:
  `DELETE /portfolio/events/orders/{id}`.
- Market list fields are `*_dollars` / `*_fp` strings; `normalize_market()`
  backfills legacy integer-cent names. Don't read `yes_bid` on raw API data.
- Public endpoints (status/events/markets/orderbook) need no key
  (`signed=False`); portfolio/order endpoints RSA-sign per request.
- Rate limit: 429s on fast paging; client retries with backoff — still
  throttle sweeps to ~2 req/s.
- Env-scoped creds: `KALSHI_DEMO_*` / `KALSHI_PROD_*` in `.env`,
  `KALSHI_ENV` selects. Prod .pem currently MISSING (key id parked in .env).
- Demo quirks: orderbooks near-empty (orders rest unfilled); some demo
  market mirrors are broken and silently drop accepted orders
  (KXMLBGAME-26JUL202210STLLAA did this — not our bug).
- Weather resolution stations: airport vs downtown differ by several °F —
  station map lives in `weather.py` STATIONS; verify `rules_primary` before
  adding a series.

## Model changelog

- 2026-07-19: v1 — normal-sigma weather model vs NWS; taker-fee netting;
  edge-per-day scoring; 7-day horizon; low-temp series fixed to overnight
  lows (was comparing against daytime highs — caught before any bet).
- 2026-07-19: journal + settle commands; every live pick auto-journaled
  with thesis and model snapshot; losses require post-mortems.
