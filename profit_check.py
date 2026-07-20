"""Profit watch: prints ALERT when total Kalshi equity clears the target.

Baseline equity $814.00 at prod go-live (2026-07-20). Target: +$689 profit
=> equity >= $1,503.00. If Chris deposits/withdraws, adjust BASELINE.
"""

from kalshi_agent.client import KalshiClient

BASELINE = 814.00
TARGET_PROFIT = 689.00

c = KalshiClient()
bal = c.get_balance()
equity = float(bal.get("balance_dollars") or 0) + (bal.get("portfolio_value") or 0) / 100
profit = equity - BASELINE
print(f"equity=${equity:.2f} baseline=${BASELINE:.2f} profit=${profit:+.2f} "
      f"target=+${TARGET_PROFIT:.2f}")
if profit >= TARGET_PROFIT:
    print("ALERT: PROFIT TARGET REACHED")
