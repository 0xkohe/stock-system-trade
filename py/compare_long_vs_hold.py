"""AGG long-only と buy-and-hold を比較する。"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import CandleStick, CandleSticks, load_csv
from backtester.strategy import PullbackStrategy


class Pos:
    def __init__(self) -> None:
        self.entry = 0.0

    def flat(self) -> bool:
        return self.entry == 0.0

    def open(self, price: float) -> None:
        self.entry = price

    def close(self) -> None:
        self.entry = 0.0


def pct_return(entry: float, exit_price: float) -> float:
    return exit_price / entry - 1


def prev_bar_exit(entry: float, prev: CandleStick, today: CandleStick) -> tuple[float, bool]:
    stop = prev.low
    if today.open <= stop:
        return pct_return(entry, today.open), True
    if today.low <= stop:
        return pct_return(entry, stop), True
    return 0.0, False


def early_entry(today: CandleStick, prev: CandleStick, band: float = 0.005) -> float | None:
    trigger = prev.close * (1 + band)
    if today.high < trigger:
        return None
    return trigger if today.open <= trigger else today.open


def long_only_trades(cs: CandleSticks, start_date: datetime.date, end_date: datetime.date) -> tuple[list[float], int]:
    strategy = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=7)
    pos = Pos()
    skip = 60
    returns: list[float] = []
    holding_days = 0

    for i in range(len(cs)):
        today = cs[i]
        if skip > 0 or today.date < start_date:
            skip -= 1
            continue
        if today.date >= end_date:
            break
        if i < 2:
            continue
        prev = cs[i - 1]

        if not pos.flat():
            holding_days += 1
            rr, ok = prev_bar_exit(pos.entry, prev, today)
            if ok:
                returns.append(rr)
                pos.close()
            continue

        buy_sig, _ = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = early_entry(today, prev)
            if p is not None:
                pos.open(p)

    return returns, holding_days


def summarize_trade_returns(returns: list[float], one_way_cost: float) -> tuple[float, float, float, int]:
    rs = [r - one_way_cost * 2 for r in returns]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    total = sum(rs)
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0.0
    cum = peak = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return total, pf, dd, len(rs)


def buy_hold(cs: CandleSticks, start_date: datetime.date, end_date: datetime.date, one_way_cost: float) -> tuple[float, float]:
    first = None
    last = None
    closes = []
    for i in range(len(cs)):
        c = cs[i]
        if c.date < start_date:
            continue
        if c.date >= end_date:
            break
        if first is None:
            first = c
        last = c
        closes.append(c.close)
    if first is None or last is None:
        return 0.0, 0.0

    ret = last.close / first.open - 1 - one_way_cost * 2
    peak = closes[0]
    dd = 0.0
    for price in closes:
        peak = max(peak, price)
        if peak > 0:
            dd = max(dd, (peak - price) / peak)
    return ret, dd


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    tickers = ["8306", "6103"]
    start = datetime.date(2020, 1, 1)
    end = datetime.date(2027, 1, 1)
    cost = 0.001

    print("=" * 104)
    print("  AGG long-only vs buy-and-hold (OOS 2020-2026, one-way cost 0.10%)")
    print("=" * 104)
    print(f"  {'ticker':<6} {'AGG Ret':>8} {'AGG PF':>7} {'AGG DD':>8} {'AGG N':>6} {'HoldDays':>9}  {'B&H Ret':>8} {'B&H DD':>8}")
    print("  " + "-" * 98)

    for ticker in tickers:
        cs = load_csv([base_dir / "data" / ticker / f"{ticker}.T.csv"])
        returns, holding_days = long_only_trades(cs, start, end)
        agg_ret, agg_pf, agg_dd, agg_n = summarize_trade_returns(returns, cost)
        hold_ret, hold_dd = buy_hold(cs, start, end, cost)
        print(
            f"  {ticker:<6} {agg_ret*100:>+7.1f}% {agg_pf:>7.2f} {agg_dd*100:>+7.1f}% {agg_n:>6} {holding_days:>9}  "
            f"{hold_ret*100:>+7.1f}% {hold_dd*100:>+7.1f}%"
        )


if __name__ == "__main__":
    main()
