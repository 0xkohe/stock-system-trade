"""他銘柄で B と 8306最有力ルールを比較する。"""
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


def fixed_exit(pos: SimplePosition, candle: CandleStick, lc: float = 0.03, lp: float = 0.06) -> tuple[float, bool]:
    entry = pos.entry_price
    if pos.is_long():
        lc_price = entry * (1 - lc)
        tp_price = entry * (1 + lp)
        if candle.open <= lc_price:
            return pct_return("BUY", entry, candle.open), True
        if candle.low <= lc_price:
            return pct_return("BUY", entry, lc_price), True
        if candle.open >= tp_price:
            return pct_return("BUY", entry, candle.open), True
        if candle.high >= tp_price:
            return pct_return("BUY", entry, tp_price), True
    else:
        lc_price = entry * (1 + lc)
        tp_price = entry * (1 - lp)
        if candle.open >= lc_price:
            return pct_return("SELL", entry, candle.open), True
        if candle.high >= lc_price:
            return pct_return("SELL", entry, lc_price), True
        if candle.open <= tp_price:
            return pct_return("SELL", entry, candle.open), True
        if candle.low <= tp_price:
            return pct_return("SELL", entry, tp_price), True
    return 0.0, False


def prev_bar_exit(pos: SimplePosition, prev_candle: CandleStick, candle: CandleStick) -> tuple[float, bool]:
    entry = pos.entry_price
    if pos.is_long():
        stop_price = prev_candle.low
        if candle.open <= stop_price:
            return pct_return("BUY", entry, candle.open), True
        if candle.low <= stop_price:
            return pct_return("BUY", entry, stop_price), True
    else:
        stop_price = prev_candle.high
        if candle.open >= stop_price:
            return pct_return("SELL", entry, candle.open), True
        if candle.high >= stop_price:
            return pct_return("SELL", entry, stop_price), True
    return 0.0, False


def breakout_entry(side: str, today: CandleStick, yesterday: CandleStick) -> float | None:
    if side == "BUY":
        trigger = yesterday.high
        if today.high < trigger:
            return None
        return trigger if today.open <= trigger else today.open
    trigger = yesterday.low
    if today.low > trigger:
        return None
    return trigger if today.open >= trigger else today.open


def early_entry(side: str, today: CandleStick, yesterday: CandleStick) -> float | None:
    band = 0.005
    if side == "BUY":
        trigger = yesterday.close * (1 + band)
        if today.high < trigger:
            return None
        return trigger if today.open <= trigger else today.open
    trigger = yesterday.close * (1 - band)
    if today.low > trigger:
        return None
    return trigger if today.open >= trigger else today.open


def run_b(cs: CandleSticks, start_date: datetime.date) -> list[Trade]:
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
            r, ok = fixed_exit(pos, today)
            if ok and entry_date is not None:
                trades.append(Trade(entry_date=entry_date, side=pos.side, gross_return=r))
                pos.close()
                entry_date = None
            continue

        buy_sig, _ = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = breakout_entry("BUY", today, yesterday)
            if p is not None:
                pos.open("BUY", p)
                entry_date = today.date
                continue

        sell_sig, _ = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = breakout_entry("SELL", today, yesterday)
            if p is not None:
                pos.open("SELL", p)
                entry_date = today.date
                continue

    return trades


def run_aggressive(cs: CandleSticks, start_date: datetime.date) -> list[Trade]:
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
            r, ok = prev_bar_exit(pos, yesterday, today)
            if ok and entry_date is not None:
                trades.append(Trade(entry_date=entry_date, side=pos.side, gross_return=r))
                pos.close()
                entry_date = None
            continue

        buy_sig, _ = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = early_entry("BUY", today, yesterday)
            if p is not None:
                pos.open("BUY", p)
                entry_date = today.date
                continue

        sell_sig, _ = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = early_entry("SELL", today, yesterday)
            if p is not None:
                pos.open("SELL", p)
                entry_date = today.date
                continue

    return trades


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


def costed_returns(trades: list[Trade], one_way_cost: float) -> list[float]:
    return [t.gross_return - one_way_cost * 2 for t in trades]


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_root = base_dir / "data"
    tickers = ["6103", "6135", "6361", "6481", "8306", "8601", "8604"]
    start = datetime.date(2013, 1, 1)
    one_way_cost = 0.001

    rows: list[dict[str, str]] = []

    print("=" * 118)
    print("  他銘柄で B と 0.5%+前日高安 を比較 (片道コスト0.10%)")
    print("=" * 118)
    print(f"  {'ticker':<6} {'B Ret':>8} {'B PF':>6} {'B DD':>7} {'B N':>5}  {'AGG Ret':>8} {'AGG PF':>7} {'AGG DD':>8} {'AGG N':>6}  {'dRet':>8} {'dPF':>6} {'dDD':>7}")
    print("  " + "-" * 112)

    for ticker in tickers:
        csv_files = sorted((data_root / ticker).glob("*.csv"))
        cs = load_csv(csv_files)
        b_trades = run_b(cs, start)
        agg_trades = run_aggressive(cs, start)
        b_ret, b_pf, b_dd, b_n = summarize(costed_returns(b_trades, one_way_cost))
        a_ret, a_pf, a_dd, a_n = summarize(costed_returns(agg_trades, one_way_cost))

        rows.append({
            "ticker": ticker,
            "cost_one_way_pct": f"{one_way_cost*100:.2f}",
            "b_ret": f"{b_ret*100:.1f}",
            "b_pf": f"{b_pf:.2f}",
            "b_dd": f"{b_dd*100:.1f}",
            "b_n": str(b_n),
            "agg_ret": f"{a_ret*100:.1f}",
            "agg_pf": f"{a_pf:.2f}",
            "agg_dd": f"{a_dd*100:.1f}",
            "agg_n": str(a_n),
            "d_ret": f"{(a_ret-b_ret)*100:.1f}",
            "d_pf": f"{(a_pf-b_pf):.2f}",
            "d_dd": f"{(a_dd-b_dd)*100:.1f}",
        })

        print(
            f"  {ticker:<6} {b_ret*100:>+7.1f}% {b_pf:>6.2f} {b_dd*100:>+6.1f}% {b_n:>5}  "
            f"{a_ret*100:>+7.1f}% {a_pf:>7.2f} {a_dd*100:>+7.1f}% {a_n:>6}  "
            f"{(a_ret-b_ret)*100:>+7.1f}% {(a_pf-b_pf):>+6.2f} {(a_dd-b_dd)*100:>+6.1f}%"
        )

    out_csv = Path("results_aggressive_other_tickers.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "cost_one_way_pct",
                "b_ret", "b_pf", "b_dd", "b_n",
                "agg_ret", "agg_pf", "agg_dd", "agg_n",
                "d_ret", "d_pf", "d_dd",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nsaved: {out_csv}")


if __name__ == "__main__":
    main()
