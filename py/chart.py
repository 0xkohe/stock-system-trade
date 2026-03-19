"""チャート + DMA + エントリーポイント表示"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 日本語フォント設定
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]

from backtester.candle import CandleSticks, CandleStick, load_csv
from backtester.position import Position, PositionType
from backtester.strategy import PullbackStrategy


# ── backtest してエントリー/エグジット情報を返す ──────────────
def run_backtest_with_signals(
    cs: CandleSticks,
    start_date: datetime.date,
    end_date: datetime.date | None,
    lc: float, lp: float, tick: float,
    min_bars: int, max_bars: int,
    dma_periods: list[int],
) -> list[dict]:
    strategy = PullbackStrategy(dma_periods=dma_periods, min_bars=min_bars, max_bars=max_bars)
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    signals: list[dict] = []
    entry_info: dict | None = None

    for i in range(len(cs)):
        v = cs[i]
        if skip > 0 or v.date < start_date:
            skip -= 1
            continue
        if end_date and v.date > end_date:
            break
        if i < 1:
            continue

        if pos.is_buying():
            _, per, ok = pos.try_sell(v)
            if ok and entry_info:
                entry_info["exit_date"] = v.date
                entry_info["exit_price"] = v.close
                entry_info["pct_return"] = per
                signals.append(entry_info)
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok and entry_info:
                entry_info["exit_date"] = v.date
                entry_info["exit_price"] = v.close
                entry_info["pct_return"] = per
                signals.append(entry_info)
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

    return signals


# ── チャート描画 ─────────────────────────────────────────────
def draw_chart(
    cs: CandleSticks,
    signals: list[dict],
    start_date: datetime.date,
    end_date: datetime.date,
    out_path: Path,
    title: str = "6103 オークマ",
) -> None:
    # データ抽出
    dates, opens, highs, lows, closes = [], [], [], [], []
    for i in range(len(cs)):
        c = cs[i]
        if c.date < start_date or c.date > end_date:
            continue
        dates.append(c.date)
        opens.append(c.open)
        highs.append(c.high)
        lows.append(c.low)
        closes.append(c.close)

    if not dates:
        print("表示期間にデータがありません")
        return

    # DMA計算
    dma10_dates, dma10_vals = [], []
    dma25_dates, dma25_vals = [], []
    for i in range(len(cs)):
        c = cs[i]
        if c.date < start_date or c.date > end_date:
            continue
        if i >= 10:
            dma10_dates.append(c.date)
            dma10_vals.append(cs.dma(10, i))
        if i >= 25:
            dma25_dates.append(c.date)
            dma25_vals.append(cs.dma(25, i))

    # 描画
    fig, ax = plt.subplots(figsize=(20, 8))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    # ローソク足
    width = 0.6
    for j in range(len(dates)):
        d = mdates.date2num(dates[j])
        o, h, l, c = opens[j], highs[j], lows[j], closes[j]
        if c >= o:
            color = "#ef4444"  # 陽線 (赤)
            body_color = "#ef4444"
        else:
            color = "#3b82f6"  # 陰線 (青)
            body_color = "#3b82f6"

        # ヒゲ
        ax.plot([d, d], [l, h], color=color, linewidth=0.8, zorder=1)
        # 実体
        body_bottom = min(o, c)
        body_height = abs(c - o)
        if body_height < 1:
            body_height = 1
        ax.bar(d, body_height, bottom=body_bottom, width=width,
               color=body_color, edgecolor=color, linewidth=0.5, zorder=2)

    # DMA
    ax.plot([mdates.date2num(d) for d in dma10_dates], dma10_vals,
            color="#fbbf24", linewidth=1.5, label="10 DMA", zorder=3, alpha=0.9)
    ax.plot([mdates.date2num(d) for d in dma25_dates], dma25_vals,
            color="#a78bfa", linewidth=1.5, label="25 DMA", zorder=3, alpha=0.9)

    # エントリー/エグジットポイント
    for sig in signals:
        ed = sig["entry_date"]
        if ed < start_date or ed > end_date:
            continue

        entry_x = mdates.date2num(ed)
        entry_y = sig["entry_price"]
        is_buy = sig["type"] == "BUY"
        is_win = sig.get("pct_return", 0) > 0

        # エントリーマーカー
        marker = "^" if is_buy else "v"
        color = "#22c55e" if is_buy else "#f97316"
        ax.scatter(entry_x, entry_y, marker=marker, color=color, s=120,
                   zorder=5, edgecolors="white", linewidths=0.8)

        # ラベル
        dma_p = sig.get("dma_period", "")
        ret_str = f"{sig.get('pct_return', 0)*100:+.1f}%" if "pct_return" in sig else ""
        label_color = "#22c55e" if is_win else "#ef4444"
        offset_y = -0.025 * (max(highs) - min(lows)) if is_buy else 0.025 * (max(highs) - min(lows))
        ax.annotate(
            f"{'B' if is_buy else 'S'}{dma_p} {ret_str}",
            xy=(entry_x, entry_y),
            xytext=(entry_x, entry_y + offset_y * 2),
            fontsize=7, color=label_color, fontweight="bold",
            ha="center", va="center",
            zorder=6,
        )

        # エグジットマーカー
        if "exit_date" in sig and sig["exit_date"]:
            ex_d = sig["exit_date"]
            if start_date <= ex_d <= end_date:
                exit_x = mdates.date2num(ex_d)
                exit_color = "#22c55e" if is_win else "#ef4444"
                ax.scatter(exit_x, sig["exit_price"], marker="x", color=exit_color,
                           s=80, zorder=5, linewidths=1.5)

    # 軸設定
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_title(f"{title}  ({start_date} ~ {end_date})", color="white", fontsize=14, pad=15)
    ax.set_ylabel("Price (JPY)", color="white")
    ax.tick_params(colors="white")
    ax.grid(True, alpha=0.15, color="white")
    ax.legend(loc="upper left", facecolor="#16213e", edgecolor="gray",
              labelcolor="white", fontsize=10)

    for spine in ax.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"保存: {out_path}")


# ── エクイティカーブ描画 ─────────────────────────────────────
def draw_equity_curve(signals: list[dict], out_path: Path) -> None:
    if not signals:
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), height_ratios=[3, 1])
    fig.patch.set_facecolor("#1a1a2e")

    # エクイティカーブ
    cum = [0.0]
    dates = [signals[0]["entry_date"]]
    for sig in signals:
        r = sig.get("pct_return", 0)
        cum.append(cum[-1] + r)
        dates.append(sig.get("exit_date", sig["entry_date"]))

    ax1.set_facecolor("#16213e")
    ax1.fill_between(dates, cum, 0, where=[c >= 0 for c in cum], color="#22c55e", alpha=0.3)
    ax1.fill_between(dates, cum, 0, where=[c < 0 for c in cum], color="#ef4444", alpha=0.3)
    ax1.plot(dates, cum, color="white", linewidth=1.5, zorder=3)
    ax1.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
    ax1.set_title("Equity Curve (累計リターン)", color="white", fontsize=13)
    ax1.set_ylabel("Cumulative Return", color="white")
    ax1.tick_params(colors="white")
    ax1.grid(True, alpha=0.15, color="white")
    for spine in ax1.spines.values():
        spine.set_color("#333")

    # トレード別リターン (棒グラフ)
    ax2.set_facecolor("#16213e")
    trade_dates = [sig.get("exit_date", sig["entry_date"]) for sig in signals]
    returns = [sig.get("pct_return", 0) * 100 for sig in signals]
    colors = ["#22c55e" if r > 0 else "#ef4444" for r in returns]
    ax2.bar(trade_dates, returns, color=colors, width=2, alpha=0.8)
    ax2.axhline(y=0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_ylabel("Trade Return (%)", color="white")
    ax2.tick_params(colors="white")
    ax2.grid(True, alpha=0.15, color="white")
    for spine in ax2.spines.values():
        spine.set_color("#333")

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"保存: {out_path}")


# ── Main ──────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Chart with entry/exit points")
    parser.add_argument("--tdir", required=True)
    parser.add_argument("--lc", type=float, default=0.03)
    parser.add_argument("--lp", type=float, default=0.06)
    parser.add_argument("--tick", type=float, default=5)
    parser.add_argument("--min-bars", type=int, default=3)
    parser.add_argument("--max-bars", type=int, default=5)
    parser.add_argument("--start", default=None, help="表示開始日 (YYYY/MM/DD)")
    parser.add_argument("--end", default=None, help="表示終了日 (YYYY/MM/DD)")
    parser.add_argument("--out-dir", default="charts", help="出力ディレクトリ")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / args.tdir
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)

    data_start = cs[0].date
    data_end = cs[len(cs) - 1].date

    # 全期間でシグナル計算
    signals = run_backtest_with_signals(
        cs, datetime.date(2000, 1, 1), None,
        args.lc, args.lp, args.tick, args.min_bars, args.max_bars, [10, 25],
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 表示期間の決定
    if args.start and args.end:
        # ユーザ指定期間
        sp = args.start.split("/")
        ep = args.end.split("/")
        chart_start = datetime.date(int(sp[0]), int(sp[1]), int(sp[2]))
        chart_end = datetime.date(int(ep[0]), int(ep[1]), int(ep[2]))
        draw_chart(cs, signals, chart_start, chart_end,
                   out_dir / f"chart_{chart_start}_{chart_end}.png",
                   f"6103 オークマ")
    else:
        # デフォルト: 直近1年 + 直近3ヶ月拡大 + 全期間エクイティ
        # 直近1年
        y1_start = datetime.date(data_end.year - 1, data_end.month, data_end.day)
        draw_chart(cs, signals, y1_start, data_end,
                   out_dir / "chart_1year.png",
                   "6103 オークマ (直近1年)")

        # 直近3ヶ月
        m3_start = datetime.date(data_end.year, data_end.month - 3, data_end.day) if data_end.month > 3 else \
                   datetime.date(data_end.year - 1, data_end.month + 9, data_end.day)
        draw_chart(cs, signals, m3_start, data_end,
                   out_dir / "chart_3months.png",
                   "6103 オークマ (直近3ヶ月)")

        # 2024年
        draw_chart(cs, signals, datetime.date(2024, 1, 1), datetime.date(2024, 12, 31),
                   out_dir / "chart_2024.png",
                   "6103 オークマ (2024年)")

        # 2025年
        draw_chart(cs, signals, datetime.date(2025, 1, 1), data_end,
                   out_dir / "chart_2025.png",
                   "6103 オークマ (2025年〜)")

    # エクイティカーブ (全期間)
    draw_equity_curve(signals, out_dir / "equity_curve.png")

    print(f"\n全 {len(signals)} トレード")
    wins = sum(1 for s in signals if s.get("pct_return", 0) > 0)
    print(f"勝ち: {wins} / 負け: {len(signals) - wins}")


if __name__ == "__main__":
    main()
