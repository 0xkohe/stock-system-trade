"""方向フィルタ比較: 基準戦略 vs 25DMA/75DMA フィルタ"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position
from backtester.strategy import PullbackStrategy


def run_backtest(cs, start_date, lc, lp, tick, strategy):
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades = []
    entry_info = None

    for i in range(len(cs)):
        v = cs[i]
        if skip > 0 or v.date < start_date:
            skip -= 1
            continue
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
        buy_sig, bp = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = (v.date, "BUY", bp)
            continue
        sell_sig, sp = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = yesterday.low if v.open >= yesterday.low else v.open
            pos.short_sell(p, v)
            entry_info = (v.date, "SELL", sp)
            continue

    return trades


def stats(trades):
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


def print_summary(name, trades):
    all_ret, all_wr, all_pf, all_dd, all_n = stats(trades)
    longs = [t for t in trades if t[1] == "BUY"]
    shorts = [t for t in trades if t[1] == "SELL"]
    long_ret, long_wr, long_pf, _, long_n = stats(longs)
    short_ret, short_wr, short_pf, _, short_n = stats(shorts)

    print(f"\n{name}")
    print(
        f"  全体    Ret:{all_ret*100:+7.1f}% WR:{all_wr:>4.0f}% PF:{all_pf:>5.2f} "
        f"MaxDD:{all_dd*100:>5.1f}% N:{all_n:>3}"
    )
    print(
        f"  ロング  Ret:{long_ret*100:+7.1f}% WR:{long_wr:>4.0f}% PF:{long_pf:>5.2f} "
        f"N:{long_n:>3}"
    )
    print(
        f"  ショート Ret:{short_ret*100:+7.1f}% WR:{short_wr:>4.0f}% PF:{short_pf:>5.2f} "
        f"N:{short_n:>3}"
    )


def print_yearly(name, trades):
    years = sorted(set(t[0].year for t in trades))
    print(f"\n{name} 年別")
    print(f"  {'年':<6} {'全体Ret':>8} {'PF':>5} {'N':>4} {'Long':>8} {'Short':>8}")
    print("  " + "-" * 48)
    for year in years:
        year_trades = [t for t in trades if t[0].year == year]
        long_trades = [t for t in year_trades if t[1] == "BUY"]
        short_trades = [t for t in year_trades if t[1] == "SELL"]
        ret, _, pf, _, n = stats(year_trades)
        long_ret = sum(t[3] for t in long_trades)
        short_ret = sum(t[3] for t in short_trades)
        print(f"  {year:<6} {ret*100:>+7.1f}% {pf:>5.2f} {n:>4} {long_ret*100:>+7.1f}% {short_ret*100:>+7.1f}%")


def main():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "6103_latest"
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    configs = [
        ("A) 基準 steps=3 lb=5 DMA=10", PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5)),
        ("B) 基準 + 25DMA方向フィルタ", PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5, trend_filter_period=25)),
        ("C) 基準 + 75DMA方向フィルタ", PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5, trend_filter_period=75)),
    ]

    print("=" * 72)
    print("  方向フィルタ比較 (6103 オークマ, 2013〜)")
    print("=" * 72)

    for name, strategy in configs:
        trades = run_backtest(cs, start, lc, lp, tick, strategy)
        print_summary(name, trades)

    print("\n" + "=" * 72)
    print("  年別比較")
    print("=" * 72)
    for name, strategy in configs:
        trades = run_backtest(cs, start, lc, lp, tick, strategy)
        print_yearly(name, trades)


if __name__ == "__main__":
    main()
