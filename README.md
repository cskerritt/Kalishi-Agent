# Kalshi Trading Agent

A Python agent for placing contract bets (event contracts) on [Kalshi](https://kalshi.com),
the CFTC-regulated prediction market exchange. Includes a signed API client, risk
controls, a CLI, an automated trading loop, and an optional Claude-powered market
analyst.

> **Disclaimer:** Trading event contracts involves real financial risk. This software
> is provided as-is with no warranty. Always start in the demo environment and in
> dry-run mode. You are responsible for every order this agent places.

## Features

- **Kalshi API v2 client** with RSA-PSS request signing (key ID + private key)
- **Market data**: browse events/markets, orderbooks, balance, positions, fills
- **Order placement**: limit and market orders, buy/sell, yes/no sides
- **Risk manager**: max cost per order, max contracts per market, daily spend cap
- **Dry-run by default** — nothing is sent to the exchange until you pass `--live`
- **Demo environment support** — practice with fake money first
- **Claude analyst (optional)** — asks Claude to estimate fair probability for a
  market and suggests a trade only when there's an edge

## Setup

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Credentials

Kalshi API access requires **two** things (create them at
kalshi.com → Account → API Keys, or on demo.kalshi.co for the demo env):

1. **API Key ID** — a UUID
2. **RSA private key** — a `.pem` file downloaded once when you create the key

```bash
cp .env.example .env
# then edit .env:
#   KALSHI_API_KEY_ID=<your key id UUID>
#   KALSHI_PRIVATE_KEY_PATH=/path/to/kalshi-private-key.pem
#   KALSHI_ENV=demo            # or "prod" when you're ready
```

Never commit `.env` or your `.pem` file (both are gitignored).

For the Claude analyst, also set `ANTHROPIC_API_KEY`.

## Usage

```bash
# Exchange status & your balance
python -m kalshi_agent status
python -m kalshi_agent balance

# Browse markets
python -m kalshi_agent markets --status open --limit 20
python -m kalshi_agent market KXHIGHNY-25JUL21-B85    # detail + orderbook

# Positions and orders
python -m kalshi_agent positions
python -m kalshi_agent orders

# Place a bet: buy 10 YES contracts at 45 cents (dry run — prints, doesn't send)
python -m kalshi_agent buy KXHIGHNY-25JUL21-B85 --side yes --count 10 --price 45

# Actually send it
python -m kalshi_agent buy KXHIGHNY-25JUL21-B85 --side yes --count 10 --price 45 --live

# Sell / close
python -m kalshi_agent sell KXHIGHNY-25JUL21-B85 --side yes --count 10 --price 60 --live

# Cancel an order
python -m kalshi_agent cancel <order_id> --live

# Ask Claude to analyze a market (no order placed)
python -m kalshi_agent analyze KXHIGHNY-25JUL21-B85

# Automated loop: analyze a series of markets and trade when there's an edge
python -m kalshi_agent run --series KXHIGHNY --interval 300          # dry run
python -m kalshi_agent run --series KXHIGHNY --interval 300 --live   # real orders
```

## Safety model

| Layer | Default | Override |
|---|---|---|
| Dry-run | On — orders are printed, never sent | `--live` |
| Environment | `demo` | `KALSHI_ENV=prod` |
| Max cost per order | $25.00 | `MAX_ORDER_COST_CENTS` |
| Max contracts per market | 100 | `MAX_POSITION_CONTRACTS` |
| Max daily spend | $100.00 | `MAX_DAILY_SPEND_CENTS` |
| Claude edge threshold | 10 percentage points | `MIN_EDGE_CENTS` |

## Project layout

```
kalshi_agent/
  auth.py       RSA-PSS request signing
  client.py     Kalshi trade API v2 client
  config.py     env-based configuration
  risk.py       order-level and daily risk limits
  analyst.py    Claude-powered market analysis (optional)
  agent.py      automated analyze-and-trade loop
  cli.py        command-line interface
tests/          unit tests (signing, risk limits)
```
