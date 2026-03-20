"""8306向け候補の live リスク検証。"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from backtester.candle import CandleStick, CandleSticks, load_csv
from backtester.strategy import PullbackStrategy


@dataclass(frozen=True)
class Candidate:
    name: str
    dma: int = 10
    steps: int = 3
    lookback: int = 7
    entry_mode: str = "breakout"   # breakout, early
    exit_mode: str = "fixed"       # fixed, prev_bar
    entry_band: float = 0.005


@dataclass
class Trade:
    entry_date: datetime.date
    exit_date: datetime.date
    side: str
    gross_return: float


class Pos:
    def __init__(self) -> None:
        self.side = ""
        self.entry = 0.0

    def flat(self) -> bool:
        return self.side == ""

    def is_long(self) -> bool:
        return self.side == "BUY"

    def is_short(self) -> bool:
        return self.side == "SELL"

    def open(self, side: str, entry: float) -> None:
        self.side = side
        self.entry = entry

    def close(self) -> None:
        self.side = ""
        self.entry = 0.0


def pct_return(side: str, entry: float, exit_price: float) -> float:
    if side == "BUY":
        return exit_price / entry - 1
    return entry / exit_price - 1


def fixed_exit(pos: Pos, today: CandleStick, lc: float = 0.03, lp: float = 0.06) -> tuple[float, bool]:
    e = pos.entry
    if pos.is_long():
        lc_p = e * (1 - lc)
        tp_p = e * (1 + lp)
        if today.open <= lc_p:
            return pct_return("BUY", e, today.open), True
        if today.low <= lc_p:
            return pct_return("BUY", e, lc_p), True
        if today.open >= tp_p:
            return pct_return("BUY", e, today.open), True
        if today.high >= tp_p:
            return pct_return("BUY", e, tp_p), True
    else:
        lc_p = e * (1 + lc)
        tp_p = e * (1 - lp)
        if today.open >= lc_p:
            return pct_return("SELL", e, today.open), True
        if today.high >= lc_p:
            return pct_return("SELL", e, lc_p), True
        if today.open <= tp_p:
            return pct_return("SELL", e, today.open), True
        if today.low <= tp_p:
            return pct_return("SELL", e, tp_p), True
    return 0.0, False


def prev_bar_exit(pos: Pos, prev: CandleStick, today: CandleStick) -> tuple[float, bool]:
    e = pos.entry
    if pos.is_long():
        stop = prev.low
        if today.open <= stop:
            return pct_return("BUY", e, today.open), True
        if today.low <= stop:
            return pct_return("BUY", e, stop), True
    else:
        stop = prev.high
        if today.open >= stop:
            return pct_return("SELL", e, today.open), True
        if today.high >= stop:
            return pct_return("SELL", e, stop), True
    return 0.0, False


def breakout_entry(side: str, today: CandleStick, prev: CandleStick) -> float | None:
    if side == "BUY":
        trig = prev.high
        if today.high < trig:
            return None
        return trig if today.open <= trig else today.open
    trig = prev.low
    if today.low > trig:
        return None
    return trig if today.open >= trig else today.open


def early_entry(side: str, today: CandleStick, prev: CandleStick, band: float) -> float | None:
    if side == "BUY":
        trig = prev.close * (1 + band)
        if today.high < trig:
            return None
        return trig if today.open <= trig else today.open
    trig = prev.close * (1 - band)
    if today.low > trig:
        return None
    return trig if today.open >= trig else today.open


def same_day_adverse_return(candidate: Candidate, side: str, entry_price: float, prev: CandleStick, today: CandleStick) -> float | None:
    if candidate.exit_mode == "fixed":
        if side == "BUY":
            stop = entry_price * (1 - 0.03)
            if today.low <= stop:
                return pct_return("BUY", entry_price, stop)
        else:
            stop = entry_price * (1 + 0.03)
            if today.high >= stop:
                return pct_return("SELL", entry_price, stop)
        return None

    if side == "BUY":
        stop = prev.low
        if today.low <= stop:
            return pct_return("BUY", entry_price, stop)
    else:
        stop = prev.high
        if today.high >= stop:
            return pct_return("SELL", entry_price, stop)
    return None


def run_candidate(
    cs: CandleSticks,
    candidate: Candidate,
    start_date: datetime.date,
    end_date: datetime.date | None,
    conservative: bool = False,
) -> list[Trade]:
    strategy = PullbackStrategy(dma_periods=[candidate.dma], down_steps=candidate.steps, lookback=candidate.lookback)
    pos = Pos()
    skip = 60
    trades: list[Trade] = []
    entry_date: datetime.date | None = None

    for i in range(len(cs)):
        today = cs[i]
        if skip > 0 or today.date < start_date:
            skip -= 1
            continue
        if end_date and today.date >= end_date:
            break
        if i < 2:
            continue
        prev = cs[i - 1]

        if not pos.flat():
            if candidate.exit_mode == "fixed":
                rr, ok = fixed_exit(pos, today)
            else:
                rr, ok = prev_bar_exit(pos, prev, today)
            if ok and entry_date is not None:
                trades.append(Trade(entry_date=entry_date, exit_date=today.date, side=pos.side, gross_return=rr))
                pos.close()
                entry_date = None
            continue

        buy_sig, _ = strategy.check_buy_signal(cs, i)
        sell_sig, _ = strategy.check_sell_signal(cs, i)

        if candidate.entry_mode == "breakout":
            buy_entry = breakout_entry("BUY", today, prev) if buy_sig else None
            sell_entry = breakout_entry("SELL", today, prev) if sell_sig else None
        else:
            buy_entry = early_entry("BUY", today, prev, candidate.entry_band) if buy_sig else None
            sell_entry = early_entry("SELL", today, prev, candidate.entry_band) if sell_sig else None

        if conservative and buy_entry is not None and sell_entry is not None:
            continue

        if buy_entry is not None:
            if conservative:
                rr = same_day_adverse_return(candidate, "BUY", buy_entry, prev, today)
                if rr is not None:
                    trades.append(Trade(entry_date=today.date, exit_date=today.date, side="BUY", gross_return=rr))
                    continue
            pos.open("BUY", buy_entry)
            entry_date = today.date
            continue

        if sell_entry is not None:
            if conservative:
                rr = same_day_adverse_return(candidate, "SELL", sell_entry, prev, today)
                if rr is not None:
                    trades.append(Trade(entry_date=today.date, exit_date=today.date, side="SELL", gross_return=rr))
                    continue
            pos.open("SELL", sell_entry)
            entry_date = today.date
            continue

    return trades


def summarize(trades: list[Trade], one_way_cost: float = 0.0, side_filter: str | None = None) -> tuple[float, float, float, int]:
    rs = []
    for t in trades:
        if side_filter and t.side != side_filter:
            continue
        rs.append(t.gross_return - one_way_cost * 2)
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


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    cs = load_csv([base_dir / "data" / "8306" / "8306.T.csv"])
    is_start = datetime.date(2013, 1, 1)
    oos_start = datetime.date(2020, 1, 1)
    end = datetime.date(2027, 1, 1)

    candidates = [
        Candidate("B", entry_mode="breakout", exit_mode="fixed"),
        Candidate("Entry 0.5", entry_mode="early", exit_mode="fixed", entry_band=0.005),
        Candidate("Prev bar exit", entry_mode="breakout", exit_mode="prev_bar"),
        Candidate("AGG", entry_mode="early", exit_mode="prev_bar", entry_band=0.005),
    ]

    print("=" * 118)
    print("  1) 同一コスト前提で候補群を比較 (片道0.10%)")
    print("=" * 118)
    print(f"  {'candidate':<16} {'IS Ret':>8} {'IS PF':>6} {'IS DD':>7} {'IS N':>5}  {'OOS Ret':>8} {'OOS PF':>7} {'OOS DD':>8} {'OOS N':>6}")
    print("  " + "-" * 112)
    for c in candidates:
        is_t = run_candidate(cs, c, is_start, oos_start)
        oos_t = run_candidate(cs, c, oos_start, end)
        is_s = summarize(is_t, one_way_cost=0.001)
        oos_s = summarize(oos_t, one_way_cost=0.001)
        print(f"  {c.name:<16} {is_s[0]*100:>+7.1f}% {is_s[1]:>6.2f} {is_s[2]*100:>+6.1f}% {is_s[3]:>5}  {oos_s[0]*100:>+7.1f}% {oos_s[1]:>7.2f} {oos_s[2]*100:>+7.1f}% {oos_s[3]:>6}")

    print("\n" + "=" * 118)
    print("  2) AGG の long / short 分解 (片道0.10%)")
    print("=" * 118)
    agg_oos = run_candidate(cs, Candidate("AGG", entry_mode="early", exit_mode="prev_bar", entry_band=0.005), oos_start, end)
    for side in [None, "BUY", "SELL"]:
        label = "both" if side is None else side
        s = summarize(agg_oos, one_way_cost=0.001, side_filter=side)
        print(f"  {label:<5} Ret {s[0]*100:+7.1f}% PF {s[1]:.2f} DD {s[2]*100:6.1f}% N {s[3]}")

    print("\n" + "=" * 118)
    print("  3) 保守的約定モデルで AGG を再評価")
    print("     同日 buy/sell 両ヒット日は見送り、当日中に stop 到達なら同日負けで処理。")
    print("=" * 118)
    oos_normal = summarize(run_candidate(cs, Candidate("AGG", entry_mode="early", exit_mode="prev_bar", entry_band=0.005), oos_start, end), one_way_cost=0.001)
    oos_cons = summarize(run_candidate(cs, Candidate("AGG", entry_mode="early", exit_mode="prev_bar", entry_band=0.005), oos_start, end, conservative=True), one_way_cost=0.001)
    print(f"  normal       Ret {oos_normal[0]*100:+7.1f}% PF {oos_normal[1]:.2f} DD {oos_normal[2]*100:6.1f}% N {oos_normal[3]}")
    print(f"  conservative Ret {oos_cons[0]*100:+7.1f}% PF {oos_cons[1]:.2f} DD {oos_cons[2]*100:6.1f}% N {oos_cons[3]}")

    print("\n" + "=" * 118)
    print("  4) 近傍安定性 (AGG 周辺, OOS, 片道0.10%)")
    print("=" * 118)
    print(f"  {'rule':<18} {'Ret':>8} {'PF':>6} {'DD':>7} {'N':>5}")
    print("  " + "-" * 44)
    stable_count = 0
    total_count = 0
    for band in [0.004, 0.005, 0.006]:
        for dma in [8, 10, 12]:
            for lb in [6, 7, 8]:
                c = Candidate(
                    name=f"e{band*100:.1f} d{dma} lb{lb}",
                    dma=dma,
                    steps=3,
                    lookback=lb,
                    entry_mode="early",
                    exit_mode="prev_bar",
                    entry_band=band,
                )
                s = summarize(run_candidate(cs, c, oos_start, end), one_way_cost=0.001)
                total_count += 1
                if s[0] > 0 and s[1] >= 1.2:
                    stable_count += 1
                print(f"  {c.name:<18} {s[0]*100:>+7.1f}% {s[1]:>6.2f} {s[2]*100:>+6.1f}% {s[3]:>5}")
    print(f"\n  OOSで Ret>0 かつ PF>=1.2 の近傍: {stable_count}/{total_count}")


if __name__ == "__main__":
    main()
