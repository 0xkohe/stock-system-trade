"""8306 最有力ルールのコスト込み再計算。"""
from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass
from pathlib import Path

from backtester.candle import CandleStick, CandleSticks, load_csv
from backtester.strategy import PullbackStrategy


@dataclass
class Trade:
    entry_date: datetime.date
    exit_date: datetime.date
    side: str
    gross_return: float


class SimplePosition:
    def __init__(self) -> None:
        self.side = ""
        self.entry_price = 0.0

    def is_long(self) -> bool:
        return self.side == "BUY"

    def is_short(self) -> bool:
        return self.side == "SELL"

    def flat(self) -> bool:
        return self.side == ""

    def open(self, side: str, price: float) -> None:
        self.side = side
        self.entry_price = price

    def close(self) -> None:
        self.side = ""
        self.entry_price = 0.0


def pct_return(side: str, entry_price: float, exit_price: float) -> float:
    if side == "BUY":
        return exit_price / entry_price - 1
    return entry_price / exit_price - 1


def prev_bar_exit(pos: SimplePosition, prev_candle: CandleStick, candle: CandleStick) -> tuple[float, float, bool]:
    entry = pos.entry_price
    if pos.is_long():
        stop_price = prev_candle.low
        if candle.open <= stop_price:
            return candle.open, pct_return("BUY", entry, candle.open), True
        if candle.low <= stop_price:
            return stop_price, pct_return("BUY", entry, stop_price), True
    else:
        stop_price = prev_candle.high
        if candle.open >= stop_price:
            return candle.open, pct_return("SELL", entry, candle.open), True
        if candle.high >= stop_price:
            return stop_price, pct_return("SELL", entry, stop_price), True
    return 0.0, 0.0, False


def early_entry_price(side: str, today: CandleStick, yesterday: CandleStick, band: float = 0.005) -> float | None:
    if side == "BUY":
        trigger = yesterday.close * (1 + band)
        if today.high < trigger:
            return None
        return trigger if today.open <= trigger else today.open
    trigger = yesterday.close * (1 - band)
    if today.low > trigger:
        return None
    return trigger if today.open >= trigger else today.open


def run_backtest_with_trades(cs: CandleSticks, start_date: datetime.date) -> list[Trade]:
    strategy = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=7)
    pos = SimplePosition()
    skip = 60
    trades: list[Trade] = []
    entry_date: datetime.date | None = None

    for i in range(len(cs)):
        today = cs[i]
        if skip > 0 or today.date < start_date:
            skip -= 1
            continue
        if i < 2:
            continue

        yesterday = cs[i - 1]

        if pos.is_long() or pos.is_short():
            _, per, ok = prev_bar_exit(pos, yesterday, today)
            if ok and entry_date is not None:
                trades.append(Trade(entry_date=entry_date, exit_date=today.date, side=pos.side, gross_return=per))
                pos.close()
                entry_date = None
            continue

        buy_sig, _ = strategy.check_buy_signal(cs, i)
        if buy_sig:
            price = early_entry_price("BUY", today, yesterday)
            if price is not None:
                pos.open("BUY", price)
                entry_date = today.date
                continue

        sell_sig, _ = strategy.check_sell_signal(cs, i)
        if sell_sig:
            price = early_entry_price("SELL", today, yesterday)
            if price is not None:
                pos.open("SELL", price)
                entry_date = today.date
                continue

    return trades


def apply_cost(trade: Trade, one_way_cost: float, short_extra: float = 0.0) -> float:
    total_cost = one_way_cost * 2
    if trade.side == "SELL":
        total_cost += short_extra
    return trade.gross_return - total_cost


def summarize(returns: list[float]) -> tuple[float, float, float, int]:
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    total = sum(returns)
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else 0.0
    cum = peak = dd = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return total, pf, dd, len(returns)


def period_returns(trades: list[Trade], start: datetime.date, end: datetime.date, one_way_cost: float) -> list[float]:
    return [
        apply_cost(t, one_way_cost)
        for t in trades
        if start <= t.entry_date < end
    ]


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    cs = load_csv(sorted((base_dir / "data" / "8306").glob("*.csv")))
    trades = run_backtest_with_trades(cs, datetime.date(2013, 1, 1))

    scenarios = [
        ("gross", 0.0000),
        ("one_way_0.10pct", 0.0010),
        ("one_way_0.20pct", 0.0020),
    ]

    is_start = datetime.date(2013, 1, 1)
    oos_start = datetime.date(2020, 1, 1)
    end = datetime.date(2027, 1, 1)

    rows: list[dict[str, str]] = []
    for name, one_way_cost in scenarios:
        is_returns = period_returns(trades, is_start, oos_start, one_way_cost)
        oos_returns = period_returns(trades, oos_start, end, one_way_cost)
        is_total, is_pf, is_dd, is_n = summarize(is_returns)
        oos_total, oos_pf, oos_dd, oos_n = summarize(oos_returns)
        rows.append({
            "scenario": name,
            "one_way_cost_pct": f"{one_way_cost*100:.2f}",
            "is_ret": f"{is_total*100:.1f}",
            "is_pf": f"{is_pf:.2f}",
            "is_dd": f"{is_dd*100:.1f}",
            "is_n": str(is_n),
            "oos_ret": f"{oos_total*100:.1f}",
            "oos_pf": f"{oos_pf:.2f}",
            "oos_dd": f"{oos_dd*100:.1f}",
            "oos_n": str(oos_n),
        })

    out_csv = Path("results_8306_aggressive_costs.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario", "one_way_cost_pct",
                "is_ret", "is_pf", "is_dd", "is_n",
                "oos_ret", "oos_pf", "oos_dd", "oos_n",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(
            f"{row['scenario']}: "
            f"IS {row['is_ret']}% PF {row['is_pf']} DD {row['is_dd']}% N {row['is_n']} | "
            f"OOS {row['oos_ret']}% PF {row['oos_pf']} DD {row['oos_dd']}% N {row['oos_n']}"
        )
    print(f"saved: {out_csv}")


if __name__ == "__main__":
    main()
