from __future__ import annotations

from backtester.candle import CandleSticks


class PullbackStrategy:
    """DMAの傾きと下落段数による押し目/戻し戦略。

    買い: DMAが上向き + 直近lookback本中にdown_steps本以上の下落足 + 反転確認
    売り: DMAが下向き + 直近lookback本中にdown_steps本以上の上昇足 + 反転確認

    下落足 = 終値 < 前日終値
    上昇足 = 終値 > 前日終値
    """

    def __init__(
        self,
        dma_periods: list[int] | None = None,
        down_steps: int = 3,
        lookback: int = 5,
        trend_filter_period: int | None = None,
        min_bars: int | None = None,
        max_bars: int | None = None,
    ) -> None:
        if min_bars is not None:
            down_steps = min_bars
        if max_bars is not None:
            lookback = max_bars
        self.dma_periods = dma_periods or [10, 25]
        self.down_steps = down_steps
        self.lookback = lookback
        self.trend_filter_period = trend_filter_period
        # 旧API互換
        self.min_bars = down_steps
        self.max_bars = lookback

    def _count_down_bars(self, cs: CandleSticks, end_index: int) -> int:
        """直近lookback本中、下落足(終値<前日終値)の数を数える。"""
        count = 0
        start = max(1, end_index - self.lookback + 1)
        for j in range(start, end_index + 1):
            if cs[j].close < cs[j - 1].close:
                count += 1
        return count

    def _count_up_bars(self, cs: CandleSticks, end_index: int) -> int:
        """直近lookback本中、上昇足(終値>前日終値)の数を数える。"""
        count = 0
        start = max(1, end_index - self.lookback + 1)
        for j in range(start, end_index + 1):
            if cs[j].close > cs[j - 1].close:
                count += 1
        return count

    # 旧比較スクリプト互換
    def _count_bars_below_dma(self, cs: CandleSticks, period: int, end_index: int) -> int:
        count = 0
        for j in range(end_index, -1, -1):
            if j < period:
                break
            if cs[j].close < cs.dma(period, j):
                count += 1
            else:
                break
        return count

    def _count_bars_above_dma(self, cs: CandleSticks, period: int, end_index: int) -> int:
        count = 0
        for j in range(end_index, -1, -1):
            if j < period:
                break
            if cs[j].close > cs.dma(period, j):
                count += 1
            else:
                break
        return count

    def _dma_is_up(self, cs: CandleSticks, period: int, index: int) -> bool:
        return cs.dma(period, index) > cs.dma(period, index - 1)

    def _dma_is_down(self, cs: CandleSticks, period: int, index: int) -> bool:
        return cs.dma(period, index) < cs.dma(period, index - 1)

    def _passes_buy_trend_filter(self, cs: CandleSticks, i: int) -> bool:
        if self.trend_filter_period is None:
            return True
        period = self.trend_filter_period
        if i < period + 2:
            return False
        return self._dma_is_up(cs, period, i - 1)

    def _passes_sell_trend_filter(self, cs: CandleSticks, i: int) -> bool:
        if self.trend_filter_period is None:
            return True
        period = self.trend_filter_period
        if i < period + 2:
            return False
        return self._dma_is_down(cs, period, i - 1)

    def check_buy_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        """押し目買いシグナル判定。(シグナル有無, トリガーしたDMA期間)"""
        yesterday = cs[i - 1]
        today = cs[i]

        if not self._passes_buy_trend_filter(cs, i):
            return False, 0

        for period in self.dma_periods:
            if i < period + self.lookback + 2:
                continue

            # DMAが上向き
            if not self._dma_is_up(cs, period, i - 1):
                continue

            # 直近lookback本中に下落足がdown_steps本以上
            downs = self._count_down_bars(cs, i - 1)
            if downs < self.down_steps:
                continue

            # 反転確認: 当日高値 >= 前日高値
            if today.high >= yesterday.high:
                return True, period

        return False, 0

    def check_sell_signal(self, cs: CandleSticks, i: int) -> tuple[bool, int]:
        """戻し売りシグナル判定。(シグナル有無, トリガーしたDMA期間)"""
        yesterday = cs[i - 1]
        today = cs[i]

        if not self._passes_sell_trend_filter(cs, i):
            return False, 0

        for period in self.dma_periods:
            if i < period + self.lookback + 2:
                continue

            # DMAが下向き
            if not self._dma_is_down(cs, period, i - 1):
                continue

            # 直近lookback本中に上昇足がdown_steps本以上
            ups = self._count_up_bars(cs, i - 1)
            if ups < self.down_steps:
                continue

            # 反転確認: 当日安値 <= 前日安値
            if today.low <= yesterday.low:
                return True, period

        return False, 0
