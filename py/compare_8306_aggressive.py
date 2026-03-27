"""8306向け: B案に対するアグレッシブ変更の個別検証。"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from backtester.candle import CandleSticks, CandleStick, load_csv
from backtester.strategy import PullbackStrategy


Trade = tuple[datetime.date, str, float]


@dataclass(frozen=True)
class RuleConfig:
    name: str
    entry_mode: str = "breakout"  # breakout, close_band_005, close_band_010
    pullback_mode: str = "3of7"   # 3of7, consecutive2
    exit_mode: str = "fixed"      # fixed, prev_bar


class SimplePosition:
    def __init__(self) -> None:
        self.side = ""
        self.entry_price = 0.0
        self.entry_candle: CandleStick | None = None

    def is_long(self) -> bool:
        return self.side == "BUY"

    def is_short(self) -> bool:
        return self.side == "SELL"

    def flat(self) -> bool:
        return self.side == ""

    def open(self, side: str, price: float, candle: CandleStick) -> None:
        self.side = side
        self.entry_price = price
        self.entry_candle = candle

    def close(self) -> None:
        self.side = ""
        self.entry_price = 0.0
        self.entry_candle = None


def pct_return(side: str, entry_price: float, exit_price: float) -> float:
    if side == "BUY":
        return exit_price / entry_price - 1
    return entry_price / exit_price - 1


def fixed_exit(pos: SimplePosition, candle: CandleStick, lc: float, lp: float) -> tuple[float, bool]:
    assert pos.entry_candle is not None
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


def has_two_consecutive_down(cs: CandleSticks, end_index: int) -> bool:
    if end_index < 2:
        return False
    return cs[end_index].close < cs[end_index - 1].close and cs[end_index - 1].close < cs[end_index - 2].close


def has_two_consecutive_up(cs: CandleSticks, end_index: int) -> bool:
    if end_index < 2:
        return False
    return cs[end_index].close > cs[end_index - 1].close and cs[end_index - 1].close > cs[end_index - 2].close


def entry_price_from_mode(mode: str, side: str, today: CandleStick, yesterday: CandleStick) -> float | None:
    if mode == "breakout":
        if side == "BUY":
            trigger = yesterday.high
            if today.high < trigger:
                return None
            return trigger if today.open <= trigger else today.open
        trigger = yesterday.low
        if today.low > trigger:
            return None
        return trigger if today.open >= trigger else today.open

    if mode == "close_band_005":
        band = 0.005
    elif mode == "close_band_010":
        band = 0.010
    else:
        raise ValueError(mode)

    if side == "BUY":
        trigger = yesterday.close * (1 + band)
        if today.high < trigger:
            return None
        return trigger if today.open <= trigger else today.open
    trigger = yesterday.close * (1 - band)
    if today.low > trigger:
        return None
    return trigger if today.open >= trigger else today.open


def run_backtest(
    cs: CandleSticks,
    start_date: datetime.date,
    end_date: datetime.date | None,
    lc: float,
    lp: float,
    strategy: PullbackStrategy,
    config: RuleConfig,
) -> list[Trade]:
    pos = SimplePosition()
    skip = 60
    trades: list[Trade] = []

    for i in range(len(cs)):
        today = cs[i]
        if skip > 0 or today.date < start_date:
            skip -= 1
            continue
        if end_date and today.date >= end_date:
            break
        if i < 2:
            continue

        yesterday = cs[i - 1]

        if pos.is_long() or pos.is_short():
            if config.exit_mode == "fixed":
                ret, ok = fixed_exit(pos, today, lc, lp)
            else:
                ret, ok = prev_bar_exit(pos, yesterday, today)
            if ok:
                trades.append((today.date, pos.side, ret))
                pos.close()
            continue

        buy_signal, _ = strategy.check_buy_signal(cs, i)
        sell_signal, _ = strategy.check_sell_signal(cs, i)

        if config.pullback_mode == "consecutive2":
            buy_signal = buy_signal and has_two_consecutive_down(cs, i - 1)
            sell_signal = sell_signal and has_two_consecutive_up(cs, i - 1)

        if buy_signal:
            price = entry_price_from_mode(config.entry_mode, "BUY", today, yesterday)
            if price is not None:
                pos.open("BUY", price, today)
                continue

        if sell_signal:
            price = entry_price_from_mode(config.entry_mode, "SELL", today, yesterday)
            if price is not None:
                pos.open("SELL", price, today)
                continue

    return trades


def stats(trades: list[Trade]) -> tuple[float, float, float, int]:
    wins = [t for t in trades if t[2] > 0]
    losses = [t for t in trades if t[2] <= 0]
    ret = sum(t[2] for t in trades)
    pf = sum(t[2] for t in wins) / abs(sum(t[2] for t in losses)) if losses and sum(t[2] for t in losses) != 0 else 0.0
    cum = peak = dd = 0.0
    for _, _, r in trades:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return ret, pf, dd, len(trades)


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    cs = load_csv(sorted((base_dir / "data" / "8306").glob("*.csv")))
    start = datetime.date(2013, 1, 1)
    is_end = datetime.date(2020, 1, 1)
    oos_end = datetime.date(2027, 1, 1)

    base_strategy = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=7)
    rules = [
        RuleConfig("B現在"),
        RuleConfig("Entry 0.5%", entry_mode="close_band_005"),
        RuleConfig("Entry 1.0%", entry_mode="close_band_010"),
        RuleConfig("2連続調整", pullback_mode="consecutive2"),
        RuleConfig("前日高安手仕舞い", exit_mode="prev_bar"),
        RuleConfig("0.5% + 前日高安", entry_mode="close_band_005", exit_mode="prev_bar"),
    ]

    print("=" * 112)
    print("  8306 B案に対するアグレッシブ変更の比較")
    print("  close_band は前日終値から ±0.5% / ±1.0% をトリガー価格にする近似。")
    print("=" * 112)
    print(f"  {'rule':<18} {'IS Ret':>8} {'IS PF':>6} {'IS DD':>7} {'IS N':>5}  {'OOS Ret':>8} {'OOS PF':>7} {'OOS DD':>8} {'OOS N':>6}")
    print("  " + "-" * 106)

    for rule in rules:
        is_trades = run_backtest(cs, start, is_end, 0.03, 0.06, base_strategy, rule)
        oos_trades = run_backtest(cs, is_end, oos_end, 0.03, 0.06, base_strategy, rule)
        is_ret, is_pf, is_dd, is_n = stats(is_trades)
        oos_ret, oos_pf, oos_dd, oos_n = stats(oos_trades)
        print(
            f"  {rule.name:<18} {is_ret*100:>+7.1f}% {is_pf:>6.2f} {is_dd*100:>+6.1f}% {is_n:>5}  "
            f"{oos_ret*100:>+7.1f}% {oos_pf:>7.2f} {oos_dd*100:>+7.1f}% {oos_n:>6}"
        )


if __name__ == "__main__":
    main()
