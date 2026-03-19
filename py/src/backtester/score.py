from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from backtester.candle import CandleStick
from backtester.position import PositionType


@dataclass
class TradeRecord:
    entry_date: datetime.date
    entry_price: float
    trade_type: PositionType
    exit_date: datetime.date | None = None
    pct_return: float = 0.0


class Score:
    def __init__(self) -> None:
        self.win = 0
        self.lose = 0
        self.total_sum = 0.0
        self.buy_count = 0
        self.short_count = 0
        self.records: list[TradeRecord] = []

    def add_entry(self, candle: CandleStick, price: float, t: PositionType) -> None:
        self.records.append(TradeRecord(
            entry_date=candle.date,
            entry_price=price,
            trade_type=t,
        ))
        if t == PositionType.BUY:
            self.buy_count += 1
        else:
            self.short_count += 1

    def add_exit(self, candle: CandleStick, pct_return: float) -> None:
        self.total_sum += pct_return
        self.records[-1].exit_date = candle.date
        self.records[-1].pct_return = pct_return
        if pct_return > 0:
            self.win += 1
        else:
            self.lose += 1

    def print_results(self) -> None:
        if not self.records:
            print("No trades.")
            return

        current_year = self.records[0].entry_date.year
        win_b = win_s = lose_b = lose_s = 0
        sum_total = sum_b = sum_s = 0.0
        cnt_b = cnt_s = 0

        def flush_year(year: int) -> None:
            nonlocal win_b, win_s, lose_b, lose_s, sum_total, sum_b, sum_s, cnt_b, cnt_s
            print(f"【YEAR】: {year}")
            print(f"win:  {win_b + win_s} (buy: {win_b} shortsell: {win_s})")
            print(f"lose: {lose_b + lose_s} (buy: {lose_b} shortsell: {lose_s})")
            print(f"sum: {sum_total}\n")
            print(f"sum Buy: {sum_b}")
            print(f"sumShortSell: {sum_s}\n")
            print(f"count: Buy: {cnt_b}")
            print(f"count: ShortSell: {cnt_s}")
            win_b = win_s = lose_b = lose_s = 0
            sum_total = sum_b = sum_s = 0.0
            cnt_b = cnt_s = 0

        for rec in self.records:
            if rec.entry_date.year != current_year:
                flush_year(current_year)
                current_year = rec.entry_date.year

            sum_total += rec.pct_return
            is_win = rec.pct_return > 0
            if rec.trade_type == PositionType.BUY:
                cnt_b += 1
                sum_b += rec.pct_return
                if is_win:
                    win_b += 1
                else:
                    lose_b += 1
            else:
                cnt_s += 1
                sum_s += rec.pct_return
                if is_win:
                    win_s += 1
                else:
                    lose_s += 1

        # 最後の年を出力
        flush_year(current_year)

        # TOTAL
        print("==================")
        print(f"TOTAL sum: {self.total_sum}")
        print(f"TOTAL win: {self.win}")
        print(f"TOTAL lose: {self.lose}")
        print(f"TOTAL buy: {self.buy_count}")
        print(f"TOTAL shortSell: {self.short_count}")
        print(f"TOTAL len: {len(self.records)}")
