# Market Research Playbook

How to research each Kalshi market category, what data actually moves each
market, and where a small bankroll can find real edge. Written 2026-07-19
from a full-exchange survey (see `.survey.json` / `.events_categories.json`).

Edge ratings are for a retail-scale bankroll (~$800) with public data:
- **A** — systematic, automatable edge worth building tooling for
- **B** — situational edge; needs judgment per trade
- **C** — occasionally tradable; mostly efficient
- **D** — avoid; you are the liquidity for someone sharper

## Climate & Weather — rating A (our best category)

**Markets:** daily high/low temperature ladders for ~10 cities, rain,
hurricanes, temperature records.
**What resolves them:** one NWS station observation (the exact station is in
the market rules — airport vs downtown differs by several °F).
**Research stack (all free):**
- `api.weather.gov` point forecast for the station (the `weather` CLI command
  automates this across all mapped series)
- NWS NBM/hourly guidance for tighter same-day distributions
- Station climatology for sanity checks
**Where the edge is:** threshold strikes several degrees from the current
forecast that still trade at 15-25c (retail flow anchors to round numbers and
citywide vibes, not the resolution station). LAX marine-layer days are the
classic: downtown reads 85°F, LAX reads 75°F, and "81°+" still trades ~20c.
**Where the edge is NOT:** at-the-money band strikes. Calibrated weather
traders price those off hourly model guidance with sigma ~1.5°F; our generic
±2.8°F model overstates band edges. Trust the scanner's threshold flags,
be skeptical of its band flags.
**Cadence:** scan morning (forecast update ~4-5am local) and early afternoon.

## Sports — rating C on winners, B on the thin tail

**Markets:** game winners (MLB/NFL/WNBA/MLS), tennis matches, UFC fights,
plus enormous auto-generated parlay/combo series (most of the exchange's
market count, near-zero volume).
**What resolves them:** the game result.
**Research stack:** ESPN scoreboard API for consensus lines (free),
devig the moneyline (divide each implied probability by their sum).
**Reality check (verified 2026-07-19):** Kalshi MLB winners track devigged
DraftKings within ~1c on every game; tennis matches match book prices too.
Bots keep the liquid markets pinned to the books.
**Where edge can exist:**
- morning line drift — Kalshi lags books for ~minutes after lineup/injury
  news; needs fast reaction, not deep analysis
- thin markets (MLS, UFC undercards, tennis qualifiers) where spreads are
  wide and bots are absent — but wide spreads eat most of the theoretical edge
- never pay the spread on a liquid winner expecting to beat the book number
**Cadence:** scan at lineup-announcement windows (MLB ~3-5h before first pitch).

## Entertainment — rating B

**Markets:** Netflix daily/weekly rank ladders (top show/movie, runner-up,
global variants), Rotten Tomatoes scores, box office, music charts.
**What resolves them:** published charts (Netflix Tudum daily Top 10, RT, etc.).
**Research stack:** persistence — today's chart is the single best predictor of
tomorrow's; press coverage (Deadline/Variety) for weekly momentum; release
calendars for what debuts tomorrow. FlixPatrol blocks scrapers; Tudum is the
official source.
**Where the edge is:** day-over-day persistence is stronger than casual money
prices in, especially for runner-up slots; new-release debuts are where the
market guesses worst.
**Caveat:** resolution is the chart *published* the next morning (viewing-day
lag) — read the rules on every market.

## Economics — rating C

**Markets:** CPI, Fed funds, jobless claims, GDP prints.
**Research stack:** Cleveland Fed inflation nowcast, CME FedWatch,
consensus surveys. All public; the market generally sits on consensus.
**Edge:** only when a nowcast diverges from stale consensus between survey
dates. Rare but clean when it happens. Small size — these markets are watched
by finance professionals.

## Financials / Crypto / Commodities — rating D

**Markets:** BTC/ETH hourly-daily ladders, S&P/Nasdaq ranges, oil/gold.
**Reality:** market makers arbitrage against spot/options in real time; the
ladder is a repriced options chain. Retail public data offers zero edge.
Use them only to hedge or for defined-risk fun, never as "picks."

## Politics / Elections — rating C (long-dated), B (event-driven)

**Markets:** thousands of election series (most far-dated, thin), approval,
legislation, nominations.
**Research stack:** polling aggregates, primary calendars, court dockets —
plus patience; capital locks up until resolution.
**Edge:** longshot bias (thin far-dated markets overprice 5-15c longshots —
selling them is the systematic play but ties up capital); fast-moving dockets
if you follow a case closely. Watch fee drag on near-50c churn.

## Mentions / "Will X say Y" — rating D

Speech-mention and announcement markets (Trump-say ladders, LeBron-announce).
Resolution hinges on exact phrasing caught by monitors; insiders/superfans
with livestream muscle win these. Skip.

## Science & Tech — rating B (niche, underrated)

**Markets:** AI model rankings (LMArena-based ladders), SpaceX launches,
tech-company events.
**Research stack:** the actual leaderboards (LMArena updates publicly), FAA
launch licenses/road closures for Starship, company event calendars.
**Edge:** few sharps, verifiable public data, and domain knowledge matters.
AI-ranking markets especially — if you follow the model-release cycle, you
know release cadences and eval deltas better than casual money.

---

## Feasible-edge policy (any horizon)

A candidate is only a pick when ALL of these hold:

1. **Net edge ≥ 8c** after the taker fee (7% x P x (1-P) per contract,
   ~1.75c at 50c) and after paying the ask — raw edge on paper is not edge.
2. **Edge rate ≥ 2c per day of capital lockup.** A 10c edge resolving
   tomorrow (10c/day) beats a 20c edge resolving in a month (0.7c/day) —
   the bankroll can only be deployed once at a time. Far-dated picks must be
   large-edge to justify tying up the $800.
3. **The edge survives a skeptical sigma.** If the flag disappears when the
   uncertainty model is tightened to what a sharp would use, it's a model
   artifact, not a market error (weather band strikes near the forecast are
   the canonical trap; threshold strikes far from forecast survive).
4. **Explainable mispricing.** Best trades come with a story for who is on
   the other side and why they're wrong (retail anchoring to downtown temps,
   stale prices after a forecast update, longshot bias in thin books).

## Standing workflow

1. **Morning scan** (best): `weather` command for temperature edges +
   sports slate vs fresh book lines + any Netflix/AI-ranking dislocations.
2. Numbered picks with conviction (high ≈ 3% of bankroll, moderate ≈ 1%,
   practice ≈ 1%) written to `picks.json`.
3. Chris picks numbers → `execute <n> --live`.
4. Risk rails in `.env`: $25/order, $80/day, dry-run default.
