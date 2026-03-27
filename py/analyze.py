"""バックテスト結果の詳細分析"""
import datetime
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position, PositionType
from backtester.strategy import PullbackStrategy


def analyze(tdir: str, lc: float, lp: float, tick: float, min_bars: int, max_bars: int):
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / tdir
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)
    start_date = datetime.date(2013, 1, 1)

    strategy = PullbackStrategy(dma_periods=[10, 25], min_bars=min_bars, max_bars=max_bars)
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60

    trades = []  # (entry_date, exit_date, type, pct_return)
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
            if ok:
                trades.append((entry_info[0], v.date, "BUY", per))
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok:
                trades.append((entry_info[0], v.date, "SELL", per))
                entry_info = None
            continue

        yesterday = cs[i - 1]
        buy_signal, _ = strategy.check_buy_signal(cs, i)
        if buy_signal:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = (v.date, p, "BUY")
            continue

        sell_signal, _ = strategy.check_sell_signal(cs, i)
        if sell_signal:
            p = yesterday.low if v.open >= yesterday.low else v.open
            pos.short_sell(p, v)
            entry_info = (v.date, p, "SELL")
            continue

    # 分析
    total = len(trades)
    wins = [t for t in trades if t[3] > 0]
    losses = [t for t in trades if t[3] <= 0]
    buy_trades = [t for t in trades if t[2] == "BUY"]
    sell_trades = [t for t in trades if t[2] == "SELL"]

    print("=" * 60)
    print(f"  オークマ(6103) バックテスト分析結果")
    print(f"  期間: 2013/01/01 ~ 最新 | LC: {lc*100}% | TP: {lp*100}%")
    print(f"  押し目/戻し: {min_bars}〜{max_bars}本")
    print("=" * 60)

    print(f"\n■ 全体サマリー")
    print(f"  総トレード数:  {total}")
    print(f"  勝ち:          {len(wins)} ({len(wins)/total*100:.1f}%)")
    print(f"  負け:          {len(losses)} ({len(losses)/total*100:.1f}%)")
    total_return = sum(t[3] for t in trades)
    print(f"  累計リターン:  {total_return*100:.2f}%")
    avg_return = total_return / total if total else 0
    print(f"  平均リターン:  {avg_return*100:.2f}%")

    if wins:
        avg_win = sum(t[3] for t in wins) / len(wins)
        print(f"  平均利益:      {avg_win*100:.2f}%")
    if losses:
        avg_loss = sum(t[3] for t in losses) / len(losses)
        print(f"  平均損失:      {avg_loss*100:.2f}%")

    if wins and losses:
        avg_win = sum(t[3] for t in wins) / len(wins)
        avg_loss = abs(sum(t[3] for t in losses) / len(losses))
        print(f"  リスクリワード: {avg_win/avg_loss:.2f}")
        print(f"  プロフィットファクター: {sum(t[3] for t in wins)/abs(sum(t[3] for t in losses)):.2f}")

    print(f"\n■ ロング (買い)")
    buy_wins = [t for t in buy_trades if t[3] > 0]
    buy_losses = [t for t in buy_trades if t[3] <= 0]
    print(f"  トレード数: {len(buy_trades)}")
    if buy_trades:
        print(f"  勝率:       {len(buy_wins)/len(buy_trades)*100:.1f}%")
        print(f"  累計:       {sum(t[3] for t in buy_trades)*100:.2f}%")

    print(f"\n■ ショート (売り)")
    sell_wins = [t for t in sell_trades if t[3] > 0]
    sell_losses = [t for t in sell_trades if t[3] <= 0]
    print(f"  トレード数: {len(sell_trades)}")
    if sell_trades:
        print(f"  勝率:       {len(sell_wins)/len(sell_trades)*100:.1f}%")
        print(f"  累計:       {sum(t[3] for t in sell_trades)*100:.2f}%")

    # 年別リターン
    print(f"\n■ 年別リターン")
    years = sorted(set(t[0].year for t in trades))
    for year in years:
        year_trades = [t for t in trades if t[0].year == year]
        yr_wins = [t for t in year_trades if t[3] > 0]
        yr_return = sum(t[3] for t in year_trades)
        wr = len(yr_wins)/len(year_trades)*100 if year_trades else 0
        sign = "+" if yr_return >= 0 else ""
        print(f"  {year}: {sign}{yr_return*100:6.2f}% ({len(year_trades)}回, 勝率{wr:.0f}%)")

    # 最大連敗
    max_losing_streak = 0
    current_streak = 0
    for t in trades:
        if t[3] <= 0:
            current_streak += 1
            max_losing_streak = max(max_losing_streak, current_streak)
        else:
            current_streak = 0

    max_winning_streak = 0
    current_streak = 0
    for t in trades:
        if t[3] > 0:
            current_streak += 1
            max_winning_streak = max(max_winning_streak, current_streak)
        else:
            current_streak = 0

    print(f"\n■ 連勝/連敗")
    print(f"  最大連勝: {max_winning_streak}")
    print(f"  最大連敗: {max_losing_streak}")

    # 最大ドローダウン
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cumulative += t[3]
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd
    print(f"\n■ 最大ドローダウン: {max_dd*100:.2f}%")


if __name__ == "__main__":
    print("\n>>> デフォルト設定 (3〜5本)")
    analyze("6103_latest", lc=0.03, lp=0.06, tick=5, min_bars=3, max_bars=5)

    print("\n\n>>> 比較: 2〜4本")
    analyze("6103_latest", lc=0.03, lp=0.06, tick=5, min_bars=2, max_bars=4)

    print("\n\n>>> 比較: 3〜7本")
    analyze("6103_latest", lc=0.03, lp=0.06, tick=5, min_bars=3, max_bars=7)
