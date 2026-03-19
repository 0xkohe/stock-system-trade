"""8306 B案のエントリー/手仕舞い付きチャートを出力する。"""
from __future__ import annotations

import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]

from backtester.candle import CandleSticks, load_csv
from backtester.position import Position
from backtester.strategy import PullbackStrategy


def compute_exit_price(entry_price: float, trade_type: str, pct_return: float) -> float:
    if trade_type == "BUY":
        return entry_price * (1 + pct_return)
    return entry_price / (1 + pct_return)


def run_backtest_with_trades(
    cs: CandleSticks,
    start_date: datetime.date,
    lc: float,
    lp: float,
    tick: float,
    strategy: PullbackStrategy,
) -> list[dict]:
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades: list[dict] = []
    entry_info: dict | None = None

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
                entry_info["exit_date"] = v.date
                entry_info["pct_return"] = per
                entry_info["exit_price"] = compute_exit_price(entry_info["entry_price"], entry_info["type"], per)
                trades.append(entry_info)
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok and entry_info:
                entry_info["exit_date"] = v.date
                entry_info["pct_return"] = per
                entry_info["exit_price"] = compute_exit_price(entry_info["entry_price"], entry_info["type"], per)
                trades.append(entry_info)
                entry_info = None
            continue

        yesterday = cs[i - 1]
        buy_sig, bp = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = {"type": "BUY", "entry_date": v.date, "entry_price": p, "dma_period": bp}
            continue

        sell_sig, sp = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = yesterday.low if v.open >= yesterday.low else v.open
            pos.short_sell(p, v)
            entry_info = {"type": "SELL", "entry_date": v.date, "entry_price": p, "dma_period": sp}
            continue

    return trades


def draw_chart(
    cs: CandleSticks,
    trades: list[dict],
    start_date: datetime.date,
    end_date: datetime.date,
    out_path: Path,
    title: str,
) -> None:
    dates, opens, highs, lows, closes = [], [], [], [], []
    indices = []
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

    width = 0.6
    for j, d in enumerate(dates):
        x = mdates.date2num(d)
        o, h, l, c = opens[j], highs[j], lows[j], closes[j]
        color = "#ef4444" if c >= o else "#3b82f6"
        ax.plot([x, x], [l, h], color=color, linewidth=0.8, zorder=1)
        body_bottom = min(o, c)
        body_height = max(abs(c - o), 0.5)
        ax.bar(x, body_height, bottom=body_bottom, width=width, color=color, edgecolor=color, linewidth=0.5, zorder=2)

    ax.plot([mdates.date2num(d) for d in dma10_dates], dma10_vals, color="#fbbf24", linewidth=1.5, label="10 DMA", zorder=3)

    y_span = max(highs) - min(lows)
    offset = y_span * 0.03 if y_span else 1
    for trade in trades:
        if not (start_date <= trade["entry_date"] <= end_date):
            continue
        entry_x = mdates.date2num(trade["entry_date"])
        exit_in_range = start_date <= trade["exit_date"] <= end_date
        exit_x = mdates.date2num(trade["exit_date"]) if exit_in_range else None
        is_buy = trade["type"] == "BUY"
        win = trade["pct_return"] > 0

        entry_marker = "^" if is_buy else "v"
        entry_color = "#22c55e" if is_buy else "#f97316"
        ax.scatter(entry_x, trade["entry_price"], marker=entry_marker, color=entry_color, s=100, zorder=5, edgecolors="white", linewidths=0.8)

        label = f"{trade['type'][0]} {trade['pct_return']*100:+.1f}%"
        label_y = trade["entry_price"] - offset if is_buy else trade["entry_price"] + offset
        ax.annotate(label, (entry_x, trade["entry_price"]), (entry_x, label_y), color="#22c55e" if win else "#ef4444", fontsize=8, ha="center")

        if exit_in_range:
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
    csv_files = sorted((base_dir / "data" / "8306").glob("*.csv"))
    cs = load_csv(csv_files)
    strategy = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=7)
    trades = run_backtest_with_trades(cs, datetime.date(2013, 1, 1), 0.03, 0.06, 5, strategy)

    out_dir = Path("charts/8306_b")
    out_dir.mkdir(parents=True, exist_ok=True)

    data_end = cs[len(cs) - 1].date
    recent_start = datetime.date(data_end.year - 1, data_end.month, data_end.day)

    periods = [
        (recent_start, data_end, "8306 B案 直近1年", out_dir / "chart_1year.png"),
        (datetime.date(2016, 1, 1), datetime.date(2016, 12, 31), "8306 B案 2016", out_dir / "chart_2016.png"),
        (datetime.date(2018, 1, 1), datetime.date(2018, 12, 31), "8306 B案 2018", out_dir / "chart_2018.png"),
        (datetime.date(2025, 1, 1), datetime.date(2025, 12, 31), "8306 B案 2025", out_dir / "chart_2025.png"),
    ]

    for start_date, end_date, title, out_path in periods:
        draw_chart(cs, trades, start_date, end_date, out_path, title)
        print(f"保存: {out_path}")


if __name__ == "__main__":
    main()
