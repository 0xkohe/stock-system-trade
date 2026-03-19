from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CandleStick:
    date: datetime.date
    open: float
    high: float
    low: float
    close: float


class CandleSticks:
    def __init__(self, candles: list[CandleStick]) -> None:
        self._candles = sorted(candles, key=lambda c: c.date)

    def __getitem__(self, i: int) -> CandleStick:
        return self._candles[i]

    def __len__(self) -> int:
        return len(self._candles)

    def dma(self, period: int, to: int) -> float:
        total = 0.0
        for i in range(period):
            total += self._candles[to - i].close
        return total / period


def load_csv(paths: list[Path]) -> CandleSticks:
    candles: list[CandleStick] = []
    for path in paths:
        with open(path, encoding="shift_jis", errors="replace") as f:
            reader = csv.reader(f)
            header_skipped = False
            for row in reader:
                if not header_skipped:
                    header_skipped = True
                    continue
                if len(row) < 5:
                    continue
                date_str = row[0].strip().strip('"')
                # 2023/9/8 形式
                parts = date_str.split("/")
                if len(parts) == 3:
                    dt = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                else:
                    # 2017-01-04 形式のフォールバック
                    parts = date_str.split("-")
                    dt = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))

                o = float(row[1].strip().strip('"'))
                h = float(row[2].strip().strip('"'))
                l = float(row[3].strip().strip('"'))
                c = float(row[4].strip().strip('"'))
                candles.append(CandleStick(date=dt, open=o, high=h, low=l, close=c))

    return CandleSticks(candles)
