from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from backtester.candle import CandleSticks, load_csv
from backtester.position import Position, PositionType
from backtester.score import Score
from backtester.strategy import PullbackStrategy


def find_csv_files(data_dir: Path) -> list[Path]:
    return sorted(data_dir.glob("*.csv"))


def trade(
    cs: CandleSticks,
    start_date: datetime.date,
    lc: float,
    lp: float,
    tick: float,
    strategy: PullbackStrategy,
) -> Score:
    score = Score()
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60

    for i in range(len(cs)):
        v = cs[i]

        if skip > 0 or v.date < start_date:
            skip -= 1
            continue

        if i < 1:
            continue

        # ロングポジション保有中 → エグジット判定
        if pos.is_buying():
            _, per, ok = pos.try_sell(v)
            if ok:
                score.add_exit(v, per)
                print(per)
            continue

        # ショートポジション保有中 → エグジット判定
        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok:
                score.add_exit(v, per)
                print(per)
            continue

        # ポジションなし → シグナル判定
        yesterday = cs[i - 1]

        # 押し目買い
        buy_signal, buy_period = strategy.check_buy_signal(cs, i)
        if buy_signal:
            p = yesterday.high
            if v.open > yesterday.high:
                p = v.open
            pos.buy(p, v)
            score.add_entry(v, p, PositionType.BUY)
            continue

        # 戻し売り
        sell_signal, sell_period = strategy.check_sell_signal(cs, i)
        if sell_signal:
            p = yesterday.low
            if v.open < yesterday.low:
                p = v.open
            pos.short_sell(p, v)
            score.add_entry(v, p, PositionType.SELL)
            continue

    return score


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock backtester with DMA pullback strategy")
    parser.add_argument("--tdir", required=True, help="Target ticker folder name")
    parser.add_argument("--lc", type=float, default=0.03, help="Loss cut %% (default: 0.03)")
    parser.add_argument("--lp", type=float, default=0.06, help="Limit profit %% (default: 0.06)")
    parser.add_argument("--tick", type=float, default=5, help="Tick size (default: 5)")
    parser.add_argument("--start-date", default="2013/01/01", help="Start date (YYYY/MM/DD)")
    parser.add_argument("--down-steps", type=int, default=3, help="下落段数 (default: 3)")
    parser.add_argument("--lookback", type=int, default=5, help="直近何本中を見るか (default: 5)")
    args = parser.parse_args()

    # data/ は py/ の親ディレクトリ（stock/data/）を参照
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = base_dir / "data" / args.tdir
    if not data_dir.exists():
        print(f"Error: data directory not found: {data_dir}")
        return

    csv_files = find_csv_files(data_dir)
    if not csv_files:
        print(f"Error: no CSV files found in {data_dir}")
        return

    cs = load_csv(csv_files)

    parts = args.start_date.split("/")
    start_date = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))

    strategy = PullbackStrategy(
        dma_periods=[10, 25],
        down_steps=args.down_steps,
        lookback=args.lookback,
    )

    score = trade(cs, start_date, args.lc, args.lp, args.tick, strategy)
    score.print_results()

    # 当日シグナル表示
    last = len(cs) - 1
    if last > 0:
        buy_signal, _ = strategy.check_buy_signal(cs, last)
        sell_signal, _ = strategy.check_sell_signal(cs, last)
        if buy_signal:
            print(f"\n{cs[last].date}")
            print("[BUY SET TIMING!!!]")
        if sell_signal:
            print(f"\n{cs[last].date}")
            print("[SHORTSELL SET TIMING!!!]")


if __name__ == "__main__":
    main()
