"""新ルール: 下落段数ベース 詳細比較 (年別リターン + ロング/ショート分離)"""
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


def detailed_report(trades, label):
    if not trades:
        print(f"\n  {label}: トレードなし")
        return

    all_t = trades
    buy_t = [t for t in trades if t[1] == "BUY"]
    sell_t = [t for t in trades if t[1] == "SELL"]

    years = sorted(set(t[0].year for t in all_t))

    def stats(ts):
        if not ts:
            return 0, 0, 0.0, 0
        w = [t for t in ts if t[3] > 0]
        l = [t for t in ts if t[3] <= 0]
        ret = sum(t[3] for t in ts)
        wr = len(w) / len(ts) * 100
        pf = sum(t[3] for t in w) / abs(sum(t[3] for t in l)) if l and sum(t[3] for t in l) != 0 else 0
        return ret, wr, pf, len(ts)

    print(f"\n{'='*120}")
    print(f"  {label}")
    print(f"{'='*120}")

    # 全体サマリー
    for name, ts in [("全体", all_t), ("ロング", buy_t), ("ショート", sell_t)]:
        ret, wr, pf, n = stats(ts)
        cum = peak = dd = 0.0
        for t in ts:
            cum += t[3]
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
        print(f"  {name:<8} Ret:{ret*100:>+7.1f}%  勝率:{wr:>4.0f}%  PF:{pf:>5.2f}  MaxDD:{dd*100:>5.1f}%  N:{n:>3}")

    # 年別テーブル
    print(f"\n  {'年':<6}", end="")
    print(f"{'--- 全体 ---':^28}  {'--- ロング ---':^28}  {'--- ショート ---':^28}")
    print(f"  {'':6}", end="")
    for _ in range(3):
        print(f"{'Ret':>8} {'WR':>5} {'PF':>5} {'N':>3}  ", end="")
    print()
    print("  " + "-" * 114)

    for year in years:
        yt_all = [t for t in all_t if t[0].year == year]
        yt_buy = [t for t in buy_t if t[0].year == year]
        yt_sell = [t for t in sell_t if t[0].year == year]

        print(f"  {year:<6}", end="")
        for ts in [yt_all, yt_buy, yt_sell]:
            ret, wr, pf, n = stats(ts)
            if n > 0:
                print(f"{ret*100:>+7.1f}% {wr:>4.0f}% {pf:>5.2f} {n:>3}  ", end="")
            else:
                print(f"{'---':>8} {'':>5} {'':>5} {0:>3}  ", end="")
        print()

    print("  " + "-" * 114)
    # 合計行
    print(f"  {'合計':<6}", end="")
    for ts in [all_t, buy_t, sell_t]:
        ret, wr, pf, n = stats(ts)
        print(f"{ret*100:>+7.1f}% {wr:>4.0f}% {pf:>5.2f} {n:>3}  ", end="")
    print()


def main():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "6103_latest"
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    configs = [
        # DMA単体
        ("steps=3 lb=5 DMA=[10]",       [10],      3, 5),
        ("steps=3 lb=5 DMA=[25]",       [25],      3, 5),
        ("steps=3 lb=5 DMA=[10,25]",    [10, 25],  3, 5),
        ("steps=3 lb=5 DMA=[5]",        [5],       3, 5),
        ("steps=3 lb=5 DMA=[5,10]",     [5, 10],   3, 5),
        ("steps=3 lb=5 DMA=[5,10,25]",  [5, 10, 25], 3, 5),
        # lookback変化
        ("steps=3 lb=7 DMA=[10]",       [10],      3, 7),
        ("steps=3 lb=7 DMA=[25]",       [25],      3, 7),
        ("steps=3 lb=7 DMA=[10,25]",    [10, 25],  3, 7),
        # steps変化
        ("steps=2 lb=5 DMA=[10,25]",    [10, 25],  2, 5),
        ("steps=4 lb=7 DMA=[10,25]",    [10, 25],  4, 7),
        ("steps=4 lb=7 DMA=[10]",       [10],      4, 7),
        ("steps=4 lb=7 DMA=[25]",       [25],      4, 7),
    ]

    for label, dma, steps, lb in configs:
        s = PullbackStrategy(dma_periods=dma, down_steps=steps, lookback=lb)
        trades = run_backtest(cs, start, lc, lp, tick, s)
        detailed_report(trades, label)


if __name__ == "__main__":
    main()
