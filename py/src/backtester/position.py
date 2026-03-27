from __future__ import annotations

import math
from enum import IntEnum

from backtester.candle import CandleStick


class PositionType(IntEnum):
    NOTHING = 0
    BUY = 1
    SELL = 2


def _round_to_tick(price: float, tick: float) -> float:
    if tick <= 1:
        return price
    r = math.floor(price)
    tmp = int(r) % int(tick)
    if tmp >= 3:
        tmp = -(int(tick) - 3)
    r -= tmp
    return float(r)


def pct_return(side: PositionType, entry_price: float, exit_price: float) -> float:
    if side == PositionType.BUY:
        return exit_price / entry_price - 1
    return entry_price / exit_price - 1


class Position:
    def __init__(self, lc: float, lp: float, tick: float) -> None:
        self.t = PositionType.NOTHING
        self.price = 0.0
        self.lc = lc
        self.lp = lp
        self.tick = tick

    def is_buying(self) -> bool:
        return self.t == PositionType.BUY

    def is_selling(self) -> bool:
        return self.t == PositionType.SELL

    def is_doing(self) -> bool:
        return self.t != PositionType.NOTHING

    def reset(self) -> None:
        self.t = PositionType.NOTHING
        self.price = 0.0

    def buy(self, price: float, candle: CandleStick) -> None:
        self.t = PositionType.BUY
        self.price = price

    def short_sell(self, price: float, candle: CandleStick) -> None:
        self.t = PositionType.SELL
        self.price = price

    def _loss_cut_price(self) -> float:
        if self.t == PositionType.BUY:
            t = 1 - self.lc
        else:
            t = 1 + self.lc

        if self.tick == 5:
            return _round_to_tick(self.price * t, self.tick)
        return self.price * t

    def _profit_price(self) -> float:
        if self.t == PositionType.BUY:
            t = 1 + self.lp
        else:
            t = 1 - self.lp

        if self.tick == 5:
            return _round_to_tick(self.price * t, self.tick)
        return self.price * t

    def try_sell(self, c: CandleStick) -> tuple[float, float, bool]:
        """ロングポジションのエグジット判定。(差額, 収益率, 決済したか)"""
        lc_price = self._loss_cut_price()
        tp_price = self._profit_price()

        # LC: 始値がLC以下
        if c.open <= lc_price:
            r = -(1.0 - c.open / self.price)
            self.t = PositionType.NOTHING
            return c.open - self.price, r, True

        # LC: 安値がLC以下
        if c.low <= lc_price:
            r = -(1 - lc_price / self.price)
            self.t = PositionType.NOTHING
            return math.ceil(self.price * self.lc), r, True

        # TP: 始値がTP以上
        if c.open >= tp_price:
            r = c.open / self.price - 1
            self.t = PositionType.NOTHING
            return c.open - self.price, r, True

        # TP: 高値がTP以上
        if c.high >= tp_price:
            r = tp_price / self.price - 1
            self.t = PositionType.NOTHING
            return math.ceil(self.price * self.lp), r, True

        return 0, 0.0, False

    def try_buy_back(self, c: CandleStick) -> tuple[float, float, bool]:
        """ショートポジションのエグジット判定。"""
        lc_price = self._loss_cut_price()
        tp_price = self._profit_price()

        # LC: 始値がLC以上
        if c.open >= lc_price:
            r = -(1.0 - self.price / c.open)
            self.t = PositionType.NOTHING
            return -(c.open - self.price), r, True

        # LC: 高値がLC以上
        if c.high >= lc_price:
            r = -(lc_price / self.price - 1)
            self.t = PositionType.NOTHING
            return math.ceil(self.price * self.lc), r, True

        # TP: 始値がTP以下
        if c.open <= tp_price:
            r = self.price / c.open - 1
            self.t = PositionType.NOTHING
            return -(c.open - self.price), r, True

        # TP: 安値がTP以下
        if c.low <= tp_price:
            r = self.price / tp_price - 1
            self.t = PositionType.NOTHING
            return math.ceil(self.price * self.lp), r, True

        return 0, 0.0, False
