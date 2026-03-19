"""8306専用の小規模ルール探索。

過学習を避けるため、候補集合は小さく保ち、
2013-2019 を IS、2020-2026 を OOS として比較する。
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position
from backtester.strategy import PullbackStrategy


Trade = tuple[datetime.date, str, int, float]


@dataclass(frozen=True)
class Rule:
    dma: int
    down_steps: int
    lookback: int
    trend_filter: int | None
    mode: str  # both, long, short

    def label(self) -> str:
        filt = f"+tf{self.trend_filter}" if self.trend_filter else ""
        return f"dma{self.dma} s{self.down_steps} lb{self.lookback}{filt} {self.mode}"


def run_backtest(
    cs,
    start_date: datetime.date,
    end_date: datetime.date | None,
    lc: float,
    lp: float,
    tick: float,
    strategy: PullbackStrategy,
    mode: str,
) -> list[Trade]:
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades: list[Trade] = []
    entry_info = None

    for i in range(len(cs)):
        v = cs[i]
        if skip > 0 or v.date < start_date:
            skip -= 1
            continue
        if end_date and v.date >= end_date:
            break
        if i < 1:
            continue

        if pos.is_buying():
            _, per, ok = pos.try_sell(v)
            if ok and entry_info:
                trades.append((*entry_info, per))
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok and entry_info:
                trades.append((*entry_info, per))
                entry_info = None
            continue

        yesterday = cs[i - 1]
        if mode in {"both", "long"}:
            buy_sig, buy_period = strategy.check_buy_signal(cs, i)
            if buy_sig:
                p = yesterday.high if v.open <= yesterday.high else v.open
                pos.buy(p, v)
                entry_info = (v.date, "BUY", buy_period)
                continue

        if mode in {"both", "short"}:
            sell_sig, sell_period = strategy.check_sell_signal(cs, i)
            if sell_sig:
                p = yesterday.low if v.open >= yesterday.low else v.open
                pos.short_sell(p, v)
                entry_info = (v.date, "SELL", sell_period)
                continue

    return trades


def stats(trades: list[Trade]) -> tuple[float, float, float, float, int]:
    n = len(trades)
    wins = [t for t in trades if t[3] > 0]
    losses = [t for t in trades if t[3] <= 0]
    ret = sum(t[3] for t in trades)
    wr = len(wins) / n * 100 if n else 0.0
    pf = sum(t[3] for t in wins) / abs(sum(t[3] for t in losses)) if losses and sum(t[3] for t in losses) != 0 else 0.0
    cum = peak = dd = 0.0
    for t in trades:
        cum += t[3]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return ret, wr, pf, dd, n


def score_candidate(ret: float, pf: float, dd: float) -> float:
    return ret + max(0.0, pf - 1.0) * 0.5 - dd * 0.3


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    csv_files = sorted((base_dir / "data" / "8306").glob("*.csv"))
    cs = load_csv(csv_files)

    is_start = datetime.date(2013, 1, 1)
    oos_start = datetime.date(2020, 1, 1)
    oos_end = datetime.date(2027, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    rules: list[Rule] = []
    for dma in [5, 10, 25]:
        for down_steps in [2, 3, 4]:
            for lookback in [5, 7]:
                if down_steps > lookback:
                    continue
                for trend_filter in [None, 25]:
                    for mode in ["both", "long", "short"]:
                        rules.append(Rule(dma, down_steps, lookback, trend_filter, mode))

    results = []
    for rule in rules:
        strategy = PullbackStrategy(
            dma_periods=[rule.dma],
            down_steps=rule.down_steps,
            lookback=rule.lookback,
            trend_filter_period=rule.trend_filter,
        )
        is_trades = run_backtest(cs, is_start, oos_start, lc, lp, tick, strategy, rule.mode)
        oos_trades = run_backtest(cs, oos_start, oos_end, lc, lp, tick, strategy, rule.mode)
        is_ret, is_wr, is_pf, is_dd, is_n = stats(is_trades)
        oos_ret, oos_wr, oos_pf, oos_dd, oos_n = stats(oos_trades)
        results.append(
            (
                rule,
                is_ret,
                is_wr,
                is_pf,
                is_dd,
                is_n,
                oos_ret,
                oos_wr,
                oos_pf,
                oos_dd,
                oos_n,
                score_candidate(is_ret, is_pf, is_dd),
            )
        )

    top = sorted(
        results,
        key=lambda r: (r[11], r[6], r[8]),
        reverse=True,
    )[:15]

    print("=" * 118)
    print("  8306 小規模探索 (IS=2013-2019 / OOS=2020-2026)")
    print("=" * 118)
    print(
        f"  {'rule':<28} {'IS Ret':>8} {'IS PF':>6} {'IS DD':>7} {'IS N':>5}  "
        f"{'OOS Ret':>8} {'OOS PF':>7} {'OOS DD':>8} {'OOS N':>6}"
    )
    print("  " + "-" * 112)

    for row in top:
        rule, is_ret, _, is_pf, is_dd, is_n, oos_ret, _, oos_pf, oos_dd, oos_n, _ = row
        print(
            f"  {rule.label():<28} {is_ret*100:>+7.1f}% {is_pf:>6.2f} {is_dd*100:>+6.1f}% {is_n:>5}  "
            f"{oos_ret*100:>+7.1f}% {oos_pf:>7.2f} {oos_dd*100:>+7.1f}% {oos_n:>6}"
        )

    print("\n  OOSでプラスかつPF>=1.0の候補")
    print("  " + "-" * 112)
    viable = [
        row for row in top
        if row[6] > 0 and row[8] >= 1.0
    ]
    for row in viable:
        rule, is_ret, _, is_pf, is_dd, is_n, oos_ret, _, oos_pf, oos_dd, oos_n, _ = row
        print(
            f"  {rule.label():<28} IS {is_ret*100:+6.1f}% PF{is_pf:>4.2f} DD{is_dd*100:>+5.1f}% N{is_n:<4} | "
            f"OOS {oos_ret*100:+6.1f}% PF{oos_pf:>4.2f} DD{oos_dd*100:>+5.1f}% N{oos_n:<4}"
        )


if __name__ == "__main__":
    main()
