"""
GridMind demo: a REAL moving-average crossover backtest.

No fake random "returns" printed as if they were a result. This synthesises a
deterministic daily price series (a seeded geometric random walk), then runs a
genuine SMA(fast)/SMA(slow) crossover strategy over it: go long when the fast
average crosses above the slow one, exit when it crosses back. Every trade,
the P&L, and the final stats are computed from the actual simulated prices —
and it's benchmarked against simply buying and holding.
"""
import math
import os
import random
import time

random.seed(7)  # deterministic series so the backtest is reproducible

DAYS = 1000          # ~4 trading years
FAST = 20            # fast simple-moving-average window
SLOW = 50            # slow simple-moving-average window
START_CASH = 100_000.0


def synth_prices(days):
    """Seeded geometric random walk with a slight upward drift + volatility."""
    price = 100.0
    series = [price]
    drift, vol = 0.0004, 0.012
    for _ in range(days - 1):
        shock = random.gauss(drift, vol)
        price *= math.exp(shock)
        series.append(price)
    return series


def sma(series, end_idx, window):
    """Simple moving average of the `window` days ending at end_idx (inclusive)."""
    if end_idx + 1 < window:
        return None
    return sum(series[end_idx - window + 1 : end_idx + 1]) / window


def main():
    chunk = os.environ.get("GRIDMIND_CHUNK_INDEX")
    if chunk is not None:
        print(f"(running as parallel chunk {int(chunk) + 1})", flush=True)

    print(f"Synthesising {DAYS} days of price data (seeded random walk)...", flush=True)
    prices = synth_prices(DAYS)
    print(f"Strategy: SMA({FAST}) / SMA({SLOW}) crossover · start cash ${START_CASH:,.0f}\n", flush=True)

    t0 = time.time()
    cash = START_CASH
    shares = 0.0
    in_position = False
    trades = []          # (entry_price, exit_price)
    entry_price = 0.0
    prev_fast = prev_slow = None

    for i in range(len(prices)):
        fast = sma(prices, i, FAST)
        slow = sma(prices, i, SLOW)
        if fast is None or slow is None:
            continue  # not enough history for both averages yet
        if prev_fast is None or prev_slow is None:
            prev_fast, prev_slow = fast, slow  # seed once both exist
            continue

        crossed_up = prev_fast <= prev_slow and fast > slow
        crossed_down = prev_fast >= prev_slow and fast < slow
        price = prices[i]

        if crossed_up and not in_position:
            shares = cash / price          # go all-in long
            cash = 0.0
            in_position = True
            entry_price = price
        elif crossed_down and in_position:
            cash = shares * price          # exit to cash
            shares = 0.0
            in_position = False
            trades.append((entry_price, price))

        prev_fast, prev_slow = fast, slow

    # mark-to-market any open position at the last price
    final_equity = cash + shares * prices[-1]
    if in_position:
        trades.append((entry_price, prices[-1]))

    # ── Results (all computed, none invented) ───────────────────────────────────
    wins = sum(1 for e, x in trades if x > e)
    strat_ret = (final_equity / START_CASH - 1) * 100
    bh_ret = (prices[-1] / prices[0] - 1) * 100   # buy-and-hold benchmark

    print(f"Executed {len(trades)} round-trip trades:", flush=True)
    for n, (e, x) in enumerate(trades, 1):
        pnl = (x / e - 1) * 100
        print(f"  trade {n:2d}: entry ${e:7.2f} -> exit ${x:7.2f}  ({pnl:+6.2f}%)", flush=True)

    win_rate = (100.0 * wins / len(trades)) if trades else 0.0
    print(f"\nBacktest finished in {time.time() - t0:.2f}s.", flush=True)
    print(f"Final equity:     ${final_equity:,.2f}  ({strat_ret:+.2f}%)", flush=True)
    print(f"Win rate:         {win_rate:.1f}%  ({wins}/{len(trades)} trades)", flush=True)
    print(f"Buy-and-hold ref: {bh_ret:+.2f}%   ->  strategy {'beat' if strat_ret > bh_ret else 'trailed'} buy-and-hold", flush=True)


if __name__ == "__main__":
    main()
