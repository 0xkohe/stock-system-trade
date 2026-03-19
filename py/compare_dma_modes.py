"""DMA判定方式の比較: 独立判定 vs 両方上向き必須"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import CandleSticks, load_csv
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


class BothDMAUpStrategy(PullbackStrategy):
    """10 DMA と 25 DMA の両方が上向きの場合のみエントリー"""

    def check_buy_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        yesterday = cs[i - 1]
        today = cs[i]

        if i < 25 + self.max_bars + 2:
            return False, 0

        # 両方上向きチェック
        if not self._dma_is_up(cs, 10, i - 1):
            return False, 0
        if not self._dma_is_up(cs, 25, i - 1):
            return False, 0

        # どちらかのDMAで押し目が発生しているか
        for period in self.dma_periods:
            bars_below = self._count_bars_below_dma(cs, period, i - 1)
            if bars_below < self.min_bars or bars_below > self.max_bars:
                continue
            if today.high >= yesterday.high:
                return True, period

        return False, 0

    def check_sell_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        yesterday = cs[i - 1]
        today = cs[i]

        if i < 25 + self.max_bars + 2:
            return False, 0

        # 両方下向きチェック
        if not self._dma_is_down(cs, 10, i - 1):
            return False, 0
        if not self._dma_is_down(cs, 25, i - 1):
            return False, 0

        for period in self.dma_periods:
            bars_above = self._count_bars_above_dma(cs, period, i - 1)
            if bars_above < self.min_bars or bars_above > self.max_bars:
                continue
            if today.low <= yesterday.low:
                return True, period

        return False, 0


class DMA10OnlyTriggerStrategy(PullbackStrategy):
    """25 DMAが上向きなら、10 DMAの押し目でエントリー (25はフィルターのみ)"""

    def check_buy_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        yesterday = cs[i - 1]
        today = cs[i]

        if i < 25 + self.max_bars + 2:
            return False, 0

        # 25 DMA上向き = 大きなトレンドが上
        if not self._dma_is_up(cs, 25, i - 1):
            return False, 0

        # 10 DMAでの押し目を検出（10 DMA自体は上でも下でもOK）
        bars_below = self._count_bars_below_dma(cs, 10, i - 1)
        if bars_below < self.min_bars or bars_below > self.max_bars:
            return False, 0
        if today.high >= yesterday.high:
            return True, 10

        return False, 0

    def check_sell_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        yesterday = cs[i - 1]
        today = cs[i]

        if i < 25 + self.max_bars + 2:
            return False, 0

        if not self._dma_is_down(cs, 25, i - 1):
            return False, 0

        bars_above = self._count_bars_above_dma(cs, 10, i - 1)
        if bars_above < self.min_bars or bars_above > self.max_bars:
            return False, 0
        if today.low <= yesterday.low:
            return True, 10

        return False, 0


def analyze(name, trades):
    n = len(trades)
    if n == 0:
        print(f"  {name:<30} トレードなし")
        return
    wins = [t for t in trades if t[3] > 0]
    ret = sum(t[3] for t in trades)
    wr = len(wins) / n * 100
    buy_trades = [t for t in trades if t[1] == "BUY"]
    sell_trades = [t for t in trades if t[1] == "SELL"]
    buy_ret = sum(t[3] for t in buy_trades)
    sell_ret = sum(t[3] for t in sell_trades)
    buy_wr = len([t for t in buy_trades if t[3] > 0]) / len(buy_trades) * 100 if buy_trades else 0
    sell_wr = len([t for t in sell_trades if t[3] > 0]) / len(sell_trades) * 100 if sell_trades else 0

    losses = [t for t in trades if t[3] <= 0]
    pf = sum(t[3] for t in wins) / abs(sum(t[3] for t in losses)) if losses and sum(t[3] for t in losses) != 0 else 0

    # max DD
    cum = 0
    peak = 0
    dd = 0
    for t in trades:
        cum += t[3]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)

    print(f"  {name}")
    print(f"    リターン: {ret*100:+.2f}%  勝率: {wr:.1f}%  PF: {pf:.2f}  MaxDD: {dd*100:.1f}%  トレード: {n}")
    print(f"    ロング:  {len(buy_trades)}回 {buy_ret*100:+.2f}% 勝率{buy_wr:.0f}%  |  ショート: {len(sell_trades)}回 {sell_ret*100:+.2f}% 勝率{sell_wr:.0f}%")


def main():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / "6103_latest"
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    strategies = {
        "A) 現状: 独立判定 (10 or 25)": PullbackStrategy(dma_periods=[10, 25], min_bars=3, max_bars=5),
        "B) 両方上向き必須 (10 AND 25)": BothDMAUpStrategy(dma_periods=[10, 25], min_bars=3, max_bars=5),
        "C) 25上向き + 10で押し目検出": DMA10OnlyTriggerStrategy(dma_periods=[10, 25], min_bars=3, max_bars=5),
        "D) 10 DMAのみ": PullbackStrategy(dma_periods=[10], min_bars=3, max_bars=5),
        "E) 25 DMAのみ": PullbackStrategy(dma_periods=[25], min_bars=3, max_bars=5),
    }

    print("=" * 70)
    print("  DMA判定方式の比較 (6103 オークマ, 2013〜)")
    print("=" * 70)

    for name, strategy in strategies.items():
        print()
        trades = run_backtest(cs, start, lc, lp, tick, strategy)
        analyze(name, trades)

    # ロングオンリーも比較
    print("\n" + "=" * 70)
    print("  ロングオンリー版")
    print("=" * 70)

    for name, strategy in strategies.items():
        print()
        trades = run_backtest(cs, start, lc, lp, tick, strategy)
        long_only = [t for t in trades if t[1] == "BUY"]
        # ロングオンリーで再集計
        analyze(f"{name} [ロングのみ]", long_only)


if __name__ == "__main__":
    main()
