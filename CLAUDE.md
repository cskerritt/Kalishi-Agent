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
5. **Profit target watch**: Chris wants to be told when total prod equity
   (cash + portfolio) reaches **$1,503.00** = +$689 over the $814.00
   go-live baseline (2026-07-20). Run `profit_check.py` whenever running
   settle/journal and alert him the moment it trips. Adjust BASELINE in
   profit_check.py if he deposits or withdraws.
6. **Bankroll $800** (prod): high conviction ≈ 3% ($24),
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

## OPERATING MODE: PASSIVE (Chris, 2026-07-20 ~9am ET)

No active agent: all scheduled jobs cancelled, Railway deployment taken
DOWN (service config/vars/volume preserved — `railway up` revives it).
Open weather positions ride to settlement untouched. When Chris asks how
it went: run `settle`, write post-mortems for losses, report the outcome.
Do NOT re-arm schedulers or place new bets without Chris asking.

## Railway deployment (continuous operation — currently DOWN, see above)

Project **kalshi-agent** (85d3a357-6e80-4d3d-bf0a-7ac0f9b7ccf3), service
**kalshi-agent**, deployed from this repo via `railway up` (respects
.railwayignore — secrets and local state are NEVER uploaded). Runs
`scheduler.py`: 08:11 ET weather scan, 14:07 ET sports drift, 20:19 ET
settle, Mon 09:04 ET profit check vs +$689 target. Push notifications via
ntfy.sh topic in NTFY_TOPIC var (also in local `.ntfy_topic`) — Chris
subscribes in the ntfy app.

- State lives on the /data volume (journal.json, .daily_spend.json) —
  `railway ssh "cat /data/journal.json"` to read it when resuming locally;
  local and Railway journals are SEPARATE — reconcile when switching.
- **AUTO_TRADE=false by default** (notify-only). `railway variables --set
  AUTO_TRADE=true` enables unattended placement: cheap weather tails +
  devig sports only, $8 stakes, max 3/day, never adds to a position,
  RiskManager caps enforced. Flip only on Chris's say-so.
- KALSHI_PRIVATE_KEY_PEM env var holds the signing key (config.py writes
  it to a temp file at boot). Redeploy: `railway up --detach` from repo.

## Combo (parlay) bets

Supported via `client.create_combo_market(legs)` — POST the chosen legs to a
multivariate event collection, Kalshi mints/returns a combo market ticker,
then trade it with a normal order. Verified end-to-end on demo 2026-07-19
(create -> resting order -> cancel). Collections: KXMVESPORTSMULTIGAMEEXTENDED-R
(cross-game sports), KXMVECROSSCATEGORY-R (mixed categories),
KXMVENBASINGLEGAME-* (same-game). Caps: 10 rate tokens/creation, 5000/week.
EV caution: on prod these are quoted by Kalshi's parlay market maker with a
wider effective spread than the legs; a combo is only worth it when several
legs are independently +EV (edges multiply, but so does variance) or when the
MM prices correlated legs as independent. Demo combo books are empty.
Prod flow (verified 2026-07-20): mint combo -> book is empty -> POST
/communications/rfqs {market_ticker, contracts} -> MM posts a real quote
within seconds (2-leg MLB test: ask 40c vs 35.4c independent-multiplication
fair = ~4.6c/13% vig). Cancel RFQ: DELETE /communications/rfqs/{id}.
Combo EV bar: combined leg edge must clear ~5c MM vig + taker fee.

## Model changelog

- 2026-07-20 AM: **obs-gating rule added after first real loss** (LAX 81+
  NO, -$10.44 cut early from -$23.78 max). A point forecast is stale the
  moment live observations contradict its mechanism: LAX was 68F and CLEAR
  pre-dawn (marine layer never formed) while the forecast still said 75F,
  and the market repriced 81+ from 19c to 53c on obs. RULE: before any
  weather bet, pull the station's latest observation
  (api.weather.gov/stations/K{XXX}/observations/latest) and check
  consistency with the forecast mechanism (overnight temp + sky cover).
  Obs-gates applied this morning killed a PHX cool-side add (91F pre-dawn
  => 106F+ day likely) and an NYC add (66F morning leans cool). TODO:
  automate the obs-gate into scan_weather.

- 2026-07-19: v1 — normal-sigma weather model vs NWS; taker-fee netting;
  edge-per-day scoring; 7-day horizon; low-temp series fixed to overnight
  lows (was comparing against daytime highs — caught before any bet).
- 2026-07-19: journal + settle commands; every live pick auto-journaled
  with thesis and model snapshot; losses require post-mortems.
- 2026-07-20: PROD LIVE — original key's pem recovered from
  ~/Downloads/App.txt, auth verified, $814 real balance; 1c canary order
  executed + journaled. Demo positions remain journaled as env=demo.
- 2026-07-20: risk fix — daily spend now tracked per env (demo orders were
  eating the prod $80/day budget and spuriously blocked a real pick).
- 2026-07-20: unified `edges` command — weather + sports devig in one
  fee-netted, edge-per-day-ranked sweep. GOTCHA caught before any bet:
  ESPN's odds `details` is a MONEYLINE for MLB but a POINT SPREAD for WNBA
  ("MIN -10.5"); parsing it as ML inverted favorites and produced fake 70c
  edges. Fix: abs(line) < 100 => spread => normal-model win prob
  (sigma 10.5 WNBA). Any new league needs its details format verified first.
