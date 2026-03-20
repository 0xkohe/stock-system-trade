"""8306 最有力ルールの勝ち/負けトレードを別チャートで出力する。"""
from __future__ import annotations

import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]

from backtester.candle import CandleStick, CandleSticks, load_csv
from backtester.strategy import PullbackStrategy


class SimplePosition:
    def __init__(self) -> None:
        self.side = ""
        self.entry_price = 0.0

    def is_long(self) -> bool:
        return self.side == "BUY"

    def is_short(self) -> bool:
        return self.side == "SELL"

    def flat(self) -> bool:
        return self.side == ""

    def open(self, side: str, price: float) -> None:
        self.side = side
        self.entry_price = price

    def close(self) -> None:
        self.side = ""
        self.entry_price = 0.0


def pct_return(side: str, entry_price: float, exit_price: float) -> float:
    if side == "BUY":
        return exit_price / entry_price - 1
    return entry_price / exit_price - 1


def prev_bar_exit(pos: SimplePosition, prev_candle: CandleStick, candle: CandleStick) -> tuple[float, float, bool]:
    entry = pos.entry_price
    if pos.is_long():
        stop_price = prev_candle.low
        if candle.open <= stop_price:
            return candle.open, pct_return("BUY", entry, candle.open), True
        if candle.low <= stop_price:
            return stop_price, pct_return("BUY", entry, stop_price), True
    else:
        stop_price = prev_candle.high
        if candle.open >= stop_price:
            return candle.open, pct_return("SELL", entry, candle.open), True
        if candle.high >= stop_price:
            return stop_price, pct_return("SELL", entry, stop_price), True
    return 0.0, 0.0, False


def early_entry_price(side: str, today: CandleStick, yesterday: CandleStick, band: float = 0.005) -> float | None:
    if side == "BUY":
        trigger = yesterday.close * (1 + band)
        if today.high < trigger:
            return None
        return trigger if today.open <= trigger else today.open
    trigger = yesterday.close * (1 - band)
    if today.low > trigger:
        return None
    return trigger if today.open >= trigger else today.open


def run_backtest_with_trades(cs: CandleSticks, start_date: datetime.date) -> list[dict]:
    strategy = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=7)
    pos = SimplePosition()
    skip = 60
    trades: list[dict] = []
    entry_info: dict | None = None

    for i in range(len(cs)):
        today = cs[i]
        if skip > 0 or today.date < start_date:
            skip -= 1
            continue
        if i < 2:
            continue

        yesterday = cs[i - 1]

        if pos.is_long() or pos.is_short():
            exit_price, per, ok = prev_bar_exit(pos, yesterday, today)
            if ok and entry_info:
                entry_info["exit_date"] = today.date
                entry_info["exit_price"] = exit_price
                entry_info["pct_return"] = per
                trades.append(entry_info)
                entry_info = None
                pos.close()
            continue

        buy_sig, bp = strategy.check_buy_signal(cs, i)
        if buy_sig:
            price = early_entry_price("BUY", today, yesterday)
            if price is not None:
                pos.open("BUY", price)
                entry_info = {"type": "BUY", "entry_date": today.date, "entry_price": price, "dma_period": bp}
                continue

        sell_sig, sp = strategy.check_sell_signal(cs, i)
        if sell_sig:
            price = early_entry_price("SELL", today, yesterday)
            if price is not None:
                pos.open("SELL", price)
                entry_info = {"type": "SELL", "entry_date": today.date, "entry_price": price, "dma_period": sp}
                continue

    return trades


def draw_chart(cs: CandleSticks, trades: list[dict], start_date: datetime.date, end_date: datetime.date, out_path: Path, title: str) -> None:
    dates, opens, highs, lows, closes, indices = [], [], [], [], [], []
    for i in range(len(cs)):
        c = cs[i]
        if start_date <= c.date <= end_date:
            indices.append(i)
            dates.append(c.date)
            opens.append(c.open)
            highs.append(c.high)
            lows.append(c.low)
            closes.append(c.close)
    if not dates:
        return

    dma10_dates, dma10_vals = [], []
    for i in indices:
        if i >= 10:
            dma10_dates.append(cs[i].date)
            dma10_vals.append(cs.dma(10, i))

    fig, ax = plt.subplots(figsize=(18, 8))
    fig.patch.set_facecolor("#101826")
    ax.set_facecolor("#0f172a")

    for j, d in enumerate(dates):
        x = mdates.date2num(d)
        o, h, l, c = opens[j], highs[j], lows[j], closes[j]
        color = "#ef4444" if c >= o else "#3b82f6"
        ax.plot([x, x], [l, h], color=color, linewidth=0.8, zorder=1)
        body_bottom = min(o, c)
        body_height = max(abs(c - o), 0.5)
        ax.bar(x, body_height, bottom=body_bottom, width=0.6, color=color, edgecolor=color, linewidth=0.5, zorder=2)

    ax.plot([mdates.date2num(d) for d in dma10_dates], dma10_vals, color="#fbbf24", linewidth=1.5, label="10 DMA", zorder=3)

    y_span = max(highs) - min(lows)
    offset = y_span * 0.03 if y_span else 1
    for trade in trades:
        if not (start_date <= trade["entry_date"] <= end_date):
            continue
        entry_x = mdates.date2num(trade["entry_date"])
        is_buy = trade["type"] == "BUY"
        win = trade["pct_return"] > 0
        entry_marker = "^" if is_buy else "v"
        entry_color = "#22c55e" if is_buy else "#f97316"
        ax.scatter(entry_x, trade["entry_price"], marker=entry_marker, color=entry_color, s=100, zorder=5, edgecolors="white", linewidths=0.8)

        label = f"{trade['type'][0]} {trade['pct_return']*100:+.1f}%"
        label_y = trade["entry_price"] - offset if is_buy else trade["entry_price"] + offset
        ax.annotate(label, (entry_x, trade["entry_price"]), (entry_x, label_y), color="#22c55e" if win else "#ef4444", fontsize=8, ha="center")

        if start_date <= trade["exit_date"] <= end_date:
            exit_x = mdates.date2num(trade["exit_date"])
            exit_color = "#22c55e" if win else "#ef4444"
            ax.scatter(exit_x, trade["exit_price"], marker="x", color=exit_color, s=70, zorder=5, linewidths=1.5)
            ax.plot([entry_x, exit_x], [trade["entry_price"], trade["exit_price"]], color=exit_color, linewidth=0.8, alpha=0.5, zorder=4)

    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax.set_title(title, color="white", fontsize=14, pad=15)
    ax.tick_params(colors="white")
    ax.grid(True, alpha=0.12, color="white")
    ax.legend(loc="upper left", facecolor="#0f172a", edgecolor="gray", labelcolor="white")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    csv_files = [base_dir / "data" / "8306" / "8306.T.csv"]
    cs = load_csv(csv_files)
    trades = run_backtest_with_trades(cs, datetime.date(2013, 1, 1))

    winners = [t for t in trades if t["pct_return"] > 0]
    losers = [t for t in trades if t["pct_return"] <= 0]

    out_dir = Path("charts/8306_aggressive_split")
    out_dir.mkdir(parents=True, exist_ok=True)

    data_end = cs[len(cs) - 1].date
    recent_start = datetime.date(data_end.year - 1, data_end.month, data_end.day)

    draw_chart(cs, winners, recent_start, data_end, out_dir / "chart_winners_1year.png", "8306 勝ちトレード 直近1年")
    draw_chart(cs, losers, recent_start, data_end, out_dir / "chart_losers_1year.png", "8306 負けトレード 直近1年")
    draw_chart(cs, winners, cs[0].date, data_end, out_dir / "chart_winners_all.png", "8306 勝ちトレード 全期間")
    draw_chart(cs, losers, cs[0].date, data_end, out_dir / "chart_losers_all.png", "8306 負けトレード 全期間")
    draw_chart(cs, winners, datetime.date(2016, 1, 1), datetime.date(2016, 12, 31), out_dir / "chart_winners_2016.png", "8306 勝ちトレード 2016")
    draw_chart(cs, losers, datetime.date(2016, 1, 1), datetime.date(2016, 12, 31), out_dir / "chart_losers_2016.png", "8306 負けトレード 2016")

    years = sorted({t["entry_date"].year for t in trades})
    for year in years:
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        draw_chart(cs, winners, year_start, year_end, out_dir / f"chart_winners_{year}.png", f"8306 勝ちトレード {year}")
        draw_chart(cs, losers, year_start, year_end, out_dir / f"chart_losers_{year}.png", f"8306 負けトレード {year}")

    print(f"保存: {out_dir / 'chart_winners_1year.png'}")
    print(f"保存: {out_dir / 'chart_losers_1year.png'}")
    print(f"保存: {out_dir / 'chart_winners_all.png'}")
    print(f"保存: {out_dir / 'chart_losers_all.png'}")
    print(f"保存: {out_dir / 'chart_winners_2016.png'}")
    print(f"保存: {out_dir / 'chart_losers_2016.png'}")
    for year in years:
        print(f"保存: {out_dir / f'chart_winners_{year}.png'}")
        print(f"保存: {out_dir / f'chart_losers_{year}.png'}")


if __name__ == "__main__":
    main()
