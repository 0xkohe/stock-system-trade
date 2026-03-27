"""新ルール: 下落段数ベースの押し目買い パラメータ比較"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position, PositionType
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


def analyze_line(trades, label):
    n = len(trades)
    if n == 0:
        print(f"  {label:<35} トレードなし")
        return
    wins = [t for t in trades if t[3] > 0]
    losses = [t for t in trades if t[3] <= 0]
    ret = sum(t[3] for t in trades)
    wr = len(wins) / n * 100
    pf = sum(t[3] for t in wins) / abs(sum(t[3] for t in losses)) if losses and sum(t[3] for t in losses) != 0 else 0

    cum = peak = dd = 0.0
    for t in trades:
        cum += t[3]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)

    buy_t = [t for t in trades if t[1] == "BUY"]
    sell_t = [t for t in trades if t[1] == "SELL"]
    buy_ret = sum(t[3] for t in buy_t)
    sell_ret = sum(t[3] for t in sell_t)

    print(f"  {label:<35} Ret:{ret*100:>+7.1f}%  WR:{wr:>4.0f}%  PF:{pf:>5.2f}  DD:{dd*100:>5.1f}%  N:{n:>3}  L:{buy_ret*100:>+6.1f}% S:{sell_ret*100:>+6.1f}%")


def main():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "6103_latest"
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    print("=" * 100)
    print("  下落段数ベースの押し目戦略 パラメータ比較 (6103 オークマ, 2013〜)")
    print("  ルール: DMA上向き + 直近lookback本中にdown_steps本以上の下落足 + 反転確認")
    print("=" * 100)

    # down_steps x lookback グリッド
    print("\n■ down_steps × lookback (DMA=[10,25], ロング+ショート)")
    print(f"  {'パラメータ':<35} {'Ret':>8}  {'WR':>4}  {'PF':>5}  {'DD':>5}  {'N':>3}  {'Long':>7} {'Short':>7}")
    print("  " + "-" * 95)

    for lookback in [3, 5, 7, 10]:
        for down_steps in [2, 3, 4, 5]:
            if down_steps > lookback:
                continue
            s = PullbackStrategy(dma_periods=[10, 25], down_steps=down_steps, lookback=lookback)
            trades = run_backtest(cs, start, lc, lp, tick, s)
            analyze_line(trades, f"steps={down_steps} lookback={lookback}")
        print()

    # ロングオンリー版
    print("\n■ ロングオンリー版")
    print(f"  {'パラメータ':<35} {'Ret':>8}  {'WR':>4}  {'PF':>5}  {'DD':>5}  {'N':>3}  {'Long':>7} {'Short':>7}")
    print("  " + "-" * 95)

    for lookback in [3, 5, 7, 10]:
        for down_steps in [2, 3, 4, 5]:
            if down_steps > lookback:
                continue
            s = PullbackStrategy(dma_periods=[10, 25], down_steps=down_steps, lookback=lookback)
            trades = run_backtest(cs, start, lc, lp, tick, s)
            long_only = [t for t in trades if t[1] == "BUY"]
            analyze_line(long_only, f"steps={down_steps} lookback={lookback}")
        print()

    # DMA別
    print("\n■ DMA別比較 (ロングオンリー, steps=3)")
    print(f"  {'パラメータ':<35} {'Ret':>8}  {'WR':>4}  {'PF':>5}  {'DD':>5}  {'N':>3}  {'Long':>7} {'Short':>7}")
    print("  " + "-" * 95)

    for lookback in [5, 7]:
        for dma in [[10], [25], [10, 25]]:
            s = PullbackStrategy(dma_periods=dma, down_steps=3, lookback=lookback)
            trades = run_backtest(cs, start, lc, lp, tick, s)
            long_only = [t for t in trades if t[1] == "BUY"]
            dma_label = "+".join(str(d) for d in dma)
            analyze_line(long_only, f"DMA={dma_label} lb={lookback}")
        print()


if __name__ == "__main__":
    main()
