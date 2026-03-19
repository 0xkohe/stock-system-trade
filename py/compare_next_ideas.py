"""次の改善候補2案を固定条件で比較する。"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position
from backtester.strategy import PullbackStrategy


Trade = tuple[datetime.date, str, int, float]


def run_backtest(cs, start_date, lc, lp, tick, buy_strategy, sell_strategy) -> list[Trade]:
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades: list[Trade] = []
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

        buy_sig, buy_period = buy_strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = (v.date, "BUY", buy_period)
            continue

        sell_sig, sell_period = sell_strategy.check_sell_signal(cs, i)
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


def print_summary(name: str, trades: list[Trade]) -> None:
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
        f"  ロング  Ret:{long_ret*100:+7.1f}% WR:{long_wr:>4.0f}% PF:{long_pf:>5.2f} N:{long_n:>3}"
    )
    print(
        f"  ショート Ret:{short_ret*100:+7.1f}% WR:{short_wr:>4.0f}% PF:{short_pf:>5.2f} N:{short_n:>3}"
    )


def print_yearly(name: str, trades: list[Trade]) -> None:
    years = sorted(set(t[0].year for t in trades))
    print(f"\n{name} 年別")
    print(f"  {'年':<6} {'全体Ret':>8} {'PF':>5} {'N':>4} {'Long':>8} {'Short':>8}")
    print("  " + "-" * 48)
    for year in years:
        year_trades = [t for t in trades if t[0].year == year]
        year_longs = [t for t in year_trades if t[1] == "BUY"]
        year_shorts = [t for t in year_trades if t[1] == "SELL"]
        ret, _, pf, _, n = stats(year_trades)
        long_ret = sum(t[3] for t in year_longs)
        short_ret = sum(t[3] for t in year_shorts)
        print(f"  {year:<6} {ret*100:>+7.1f}% {pf:>5.2f} {n:>4} {long_ret*100:>+7.1f}% {short_ret*100:>+7.1f}%")


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "6103_latest"
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    baseline = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5)
    directional = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5, trend_filter_period=25)

    # 事前に固定した候補だけを比較する:
    # ロングは安定寄りの 3/5 + 25DMA フィルタ、ショートは既存比較で最良だった 4/7 DMA10。
    split_long = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5, trend_filter_period=25)
    split_short = PullbackStrategy(dma_periods=[10], down_steps=4, lookback=7)

    configs = [
        ("A) 基準: 3/5 DMA10", baseline, baseline),
        ("B) 案1: 25DMA方向 + 10DMAタイミング", directional, directional),
        ("C) 案2: ロング/ショート分離", split_long, split_short),
    ]

    print("=" * 76)
    print("  次の改善候補2案の比較 (6103 オークマ, 2013〜)")
    print("=" * 76)
    print("  案1は長期方向=25DMA、タイミング=10DMA。")
    print("  案2はロング=3/5 DMA10 +25DMAフィルタ、ショート=4/7 DMA10。")

    for name, buy_strategy, sell_strategy in configs:
        trades = run_backtest(cs, start, lc, lp, tick, buy_strategy, sell_strategy)
        print_summary(name, trades)

    print("\n" + "=" * 76)
    print("  年別比較")
    print("=" * 76)
    for name, buy_strategy, sell_strategy in configs:
        trades = run_backtest(cs, start, lc, lp, tick, buy_strategy, sell_strategy)
        print_yearly(name, trades)


if __name__ == "__main__":
    main()
