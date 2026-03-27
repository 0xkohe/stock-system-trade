"""過学習チェック・ロバスト性検証付きバックテスト分析ツール

含む分析:
1. 基本メトリクス (Sharpe, Calmar, Expectancy, PF, etc.)
2. Walk-Forward Analysis (IS/OOS比較)
3. パラメータ感度分析 (1D sweep + 2D grid)
4. モンテカルロ分析 (シャッフル検定 + ブートストラップCI)
5. 過学習リスク総合判定
"""
from __future__ import annotations

import argparse
import datetime
import math
import random
from pathlib import Path

from backtester.candle import CandleSticks, load_csv
from backtester.position import Position, PositionType
from backtester.strategy import PullbackStrategy

Trade = tuple[datetime.date, datetime.date, str, float]  # entry, exit, type, pct_return


# ── Core backtest loop ────────────────────────────────────────────
def run_backtest(
    cs: CandleSticks,
    start_date: datetime.date,
    end_date: datetime.date | None,
    lc: float, lp: float, tick: float,
    min_bars: int, max_bars: int,
    dma_periods: list[int] | None = None,
) -> list[Trade]:
    strategy = PullbackStrategy(dma_periods=dma_periods or [10, 25], min_bars=min_bars, max_bars=max_bars)
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades: list[Trade] = []
    entry_info: tuple[datetime.date, float, str] | None = None

    for i in range(len(cs)):
        v = cs[i]
        if skip > 0 or v.date < start_date:
            skip -= 1
            continue
        if end_date and v.date >= end_date:
            break
        if i < 1:
            continue

        if pos.is_buying():
            _, per, ok = pos.try_sell(v)
            if ok and entry_info:
                trades.append((entry_info[0], v.date, "BUY", per))
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok and entry_info:
                trades.append((entry_info[0], v.date, "SELL", per))
                entry_info = None
            continue

        yesterday = cs[i - 1]
        buy_sig, _ = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = (v.date, p, "BUY")
            continue

        sell_sig, _ = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = yesterday.low if v.open >= yesterday.low else v.open
            pos.short_sell(p, v)
            entry_info = (v.date, p, "SELL")
            continue

    return trades


# ── Statistics helpers ────────────────────────────────────────────
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0

def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (k - f) * (s[c] - s[f])

def _max_drawdown(returns: list[float]) -> float:
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = max(dd, peak - cum)
    return dd


# ── 1. Standard Metrics ──────────────────────────────────────────
def compute_metrics(trades: list[Trade], start_date: datetime.date, end_date: datetime.date) -> dict:
    if not trades:
        return {}

    returns = [t[3] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    buy_trades = [t for t in trades if t[2] == "BUY"]
    sell_trades = [t for t in trades if t[2] == "SELL"]

    total_return = sum(returns)
    n = len(returns)
    win_rate = len(wins) / n
    avg_win = _mean(wins) if wins else 0.0
    avg_loss = _mean(losses) if losses else 0.0

    years_span = max((end_date - start_date).days / 365.25, 1)
    trades_per_year = n / years_span
    annualized_return = total_return / years_span

    sharpe = 0.0
    if _stdev(returns) > 0:
        sharpe = _mean(returns) / _stdev(returns) * math.sqrt(trades_per_year)

    max_dd = _max_drawdown(returns)
    calmar = annualized_return / max_dd if max_dd > 0 else float("inf")

    holding_days = []
    for t in trades:
        if t[1]:
            holding_days.append((t[1] - t[0]).days)

    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    return {
        "total_return": total_return,
        "n_trades": n,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": pf,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_drawdown": max_dd,
        "annualized_return": annualized_return,
        "avg_holding_days": _mean(holding_days) if holding_days else 0,
        "buy_win_rate": len([t for t in buy_trades if t[3] > 0]) / len(buy_trades) if buy_trades else 0,
        "sell_win_rate": len([t for t in sell_trades if t[3] > 0]) / len(sell_trades) if sell_trades else 0,
        "buy_return": sum(t[3] for t in buy_trades),
        "sell_return": sum(t[3] for t in sell_trades),
        "buy_count": len(buy_trades),
        "sell_count": len(sell_trades),
    }


def print_metrics(m: dict) -> None:
    print("=" * 60)
    print("  基本メトリクス")
    print("=" * 60)
    print(f"  総トレード数:     {m['n_trades']}")
    print(f"  勝率:             {m['win_rate']*100:.1f}%")
    print(f"  累計リターン:     {m['total_return']*100:+.2f}%")
    print(f"  年率リターン:     {m['annualized_return']*100:+.2f}%")
    print(f"  平均利益:         {m['avg_win']*100:+.2f}%")
    print(f"  平均損失:         {m['avg_loss']*100:.2f}%")
    print(f"  期待値/トレード:  {m['expectancy']*100:+.3f}%")
    pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] < 100 else "∞"
    print(f"  プロフィットファクター: {pf_str}")
    print(f"  Sharpe風比率:     {m['sharpe']:.2f}")
    calmar_str = f"{m['calmar']:.2f}" if m['calmar'] < 100 else "∞"
    print(f"  Calmar比率:       {calmar_str}")
    print(f"  最大ドローダウン: {m['max_drawdown']*100:.2f}%")
    print(f"  平均保有日数:     {m['avg_holding_days']:.1f}日")
    print(f"  ロング: {m['buy_count']}回 勝率{m['buy_win_rate']*100:.1f}% 累計{m['buy_return']*100:+.2f}%")
    print(f"  ショート: {m['sell_count']}回 勝率{m['sell_win_rate']*100:.1f}% 累計{m['sell_return']*100:+.2f}%")


# ── 2. Walk-Forward Analysis ─────────────────────────────────────
def _add_years(d: datetime.date, years: int) -> datetime.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def walk_forward_analysis(
    cs: CandleSticks, lc: float, lp: float, tick: float,
    min_bars: int, max_bars: int, dma_periods: list[int],
    is_years: int = 3, oos_years: int = 1,
) -> list[dict]:
    data_start = cs[0].date
    data_end = cs[len(cs) - 1].date

    print("\n" + "=" * 60)
    print(f"  Walk-Forward分析 (IS={is_years}年 / OOS={oos_years}年)")
    print("=" * 60)
    print(f"  {'Window':<24} {'IS Return':>10} {'OOS Return':>11} {'劣化率':>8}")
    print("  " + "-" * 56)

    results = []
    window_start = data_start

    while True:
        is_end = _add_years(window_start, is_years)
        oos_end = _add_years(is_end, oos_years)
        if oos_end > data_end:
            break

        is_trades = run_backtest(cs, window_start, is_end, lc, lp, tick, min_bars, max_bars, dma_periods)
        oos_trades = run_backtest(cs, is_end, oos_end, lc, lp, tick, min_bars, max_bars, dma_periods)

        is_ret = sum(t[3] for t in is_trades) if is_trades else 0
        oos_ret = sum(t[3] for t in oos_trades) if oos_trades else 0

        # 年率換算して比較。ISが0近辺なら劣化率は算出しない
        is_annual = is_ret / is_years
        oos_annual = oos_ret / oos_years
        if abs(is_annual) > 0.005:
            degradation = (oos_annual - is_annual) / abs(is_annual) * 100
        else:
            degradation = 0.0  # IS≒0 なら比較不能

        label = f"{window_start.year}-{is_end.year-1}/{is_end.year}"
        flag = " ⚠" if degradation < -50 else ""
        print(f"  {label:<24} {is_annual*100:>+9.2f}% {oos_annual*100:>+10.2f}% {degradation:>+7.1f}%{flag}")

        results.append({
            "window": label,
            "is_annual": is_annual,
            "oos_annual": oos_annual,
            "is_trades": len(is_trades),
            "oos_trades": len(oos_trades),
            "degradation": degradation,
        })

        window_start = _add_years(window_start, oos_years)

    if results:
        avg_is = _mean([r["is_annual"] for r in results])
        avg_oos = _mean([r["oos_annual"] for r in results])
        valid_deg = [r["degradation"] for r in results if abs(r["is_annual"]) > 0.005]
        avg_deg = _mean(valid_deg) if valid_deg else 0
        print("  " + "-" * 56)
        print(f"  {'平均(年率)':<24} {avg_is*100:>+9.2f}% {avg_oos*100:>+10.2f}% {avg_deg:>+7.1f}%")

        # IS/OOS一貫性チェック
        oos_positive = sum(1 for r in results if r["oos_annual"] > 0)
        print(f"\n  OOS期間プラスの窓: {oos_positive}/{len(results)}")

    return results


# ── 3. Parameter Sensitivity ─────────────────────────────────────
def parameter_sensitivity(
    cs: CandleSticks, start_date: datetime.date, end_date: datetime.date | None,
    base_lc: float, base_lp: float, base_tick: float,
    base_min: int, base_max: int, dma_periods: list[int],
) -> dict:
    print("\n" + "=" * 60)
    print("  パラメータ感度分析")
    print("=" * 60)

    results: dict[str, list] = {}

    # 1D sweeps
    sweeps: dict[str, list] = {
        "lc": [0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05],
        "lp": [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10],
        "min_bars": [2, 3, 4, 5],
        "max_bars": [4, 5, 6, 7, 8],
    }

    for param_name, values in sweeps.items():
        print(f"\n  ■ {param_name} 感度")
        print(f"  {'値':>8} {'リターン':>10} {'勝率':>6} {'PF':>6} {'トレード数':>8}")
        sweep_results = []
        for val in values:
            lc = val if param_name == "lc" else base_lc
            lp = val if param_name == "lp" else base_lp
            mn = val if param_name == "min_bars" else base_min
            mx = val if param_name == "max_bars" else base_max
            if param_name == "min_bars" and mn > base_max:
                continue
            if param_name == "max_bars" and mx < base_min:
                continue

            trades = run_backtest(cs, start_date, end_date, lc, lp, base_tick, mn, mx, dma_periods)
            ret = sum(t[3] for t in trades) if trades else 0
            wins = [t for t in trades if t[3] > 0]
            losses = [t for t in trades if t[3] <= 0]
            wr = len(wins) / len(trades) * 100 if trades else 0
            pf = sum(t[3] for t in wins) / abs(sum(t[3] for t in losses)) if losses and sum(t[3] for t in losses) != 0 else 0

            marker = " ◀" if (param_name in ("lc", "lp") and val == (base_lc if param_name == "lc" else base_lp)) or \
                           (param_name == "min_bars" and val == base_min) or \
                           (param_name == "max_bars" and val == base_max) else ""
            val_str = f"{val*100:.1f}%" if isinstance(val, float) else str(val)
            print(f"  {val_str:>8} {ret*100:>+9.2f}% {wr:>5.1f}% {pf:>5.2f} {len(trades):>8}{marker}")
            sweep_results.append((val, ret, wr, pf, len(trades)))

        results[param_name] = sweep_results

        # Edge-of-range チェック
        rets = [s[1] for s in sweep_results]
        best_idx = rets.index(max(rets))
        if best_idx == 0 or best_idx == len(rets) - 1:
            print(f"  ⚠ 最適値がレンジ端 → 探索範囲を広げるべき")

        # 安定性チェック
        if len(rets) >= 3 and _stdev(rets) > 0:
            cv = _stdev(rets) / abs(_mean(rets)) if _mean(rets) != 0 else float("inf")
            if cv > 2.0:
                print(f"  ⚠ 高感度 (CV={cv:.1f}) → パラメータに脆弱")

    # 2D grid: lc x lp
    print(f"\n  ■ LC × LP ヒートマップ (リターン%)")
    lc_vals = [0.02, 0.025, 0.03, 0.035, 0.04]
    lp_vals = [0.04, 0.05, 0.06, 0.07, 0.08]
    header = "         " + "".join(f"lp={v*100:.0f}%  " for v in lp_vals)
    print(f"  {header}")

    grid_results = []
    best_val = -999
    best_pos = (0, 0)
    for lc in lc_vals:
        row_str = f"  lc={lc*100:.1f}%"
        for lp in lp_vals:
            trades = run_backtest(cs, start_date, end_date, lc, lp, base_tick, base_min, base_max, dma_periods)
            ret = sum(t[3] for t in trades) if trades else 0
            grid_results.append(ret)
            marker = f"[{ret*100:+5.1f}]" if lc == base_lc and lp == base_lp else f" {ret*100:+5.1f} "
            row_str += f" {marker}"
            if ret > best_val:
                best_val = ret
                best_pos = (lc, lp)
        print(row_str)

    if best_pos[0] in (lc_vals[0], lc_vals[-1]) or best_pos[1] in (lp_vals[0], lp_vals[-1]):
        print(f"  ⚠ 最適値 (LC={best_pos[0]*100:.1f}%, LP={best_pos[1]*100:.1f}%) がグリッド端")

    # グリッド全体の安定性
    grid_cv = _stdev(grid_results) / abs(_mean(grid_results)) if _mean(grid_results) != 0 else float("inf")
    print(f"  グリッドCV: {grid_cv:.2f} {'(安定)' if grid_cv < 1.0 else '(不安定 ⚠)'}")

    return results


# ── 4. Monte Carlo Analysis ──────────────────────────────────────
def monte_carlo_analysis(trades: list[Trade], n_sims: int = 2000, seed: int = 42) -> dict:
    random.seed(seed)
    returns = [t[3] for t in trades]
    actual_total = sum(returns)
    actual_dd = _max_drawdown(returns)
    n = len(returns)

    print("\n" + "=" * 60)
    print(f"  モンテカルロ分析 ({n_sims}回シミュレーション)")
    print("=" * 60)

    # シャッフル検定: 順序をランダム化して総リターンのDDを比較
    shuffled_dds = []
    for _ in range(n_sims):
        shuffled = returns[:]
        random.shuffle(shuffled)
        shuffled_dds.append(_max_drawdown(shuffled))

    # ブートストラップCI: 復元抽出で総リターンの分布を推定
    bootstrap_returns = []
    for _ in range(n_sims):
        sample = random.choices(returns, k=n)
        bootstrap_returns.append(sum(sample))

    p5 = _percentile(bootstrap_returns, 5)
    p25 = _percentile(bootstrap_returns, 25)
    p50 = _percentile(bootstrap_returns, 50)
    p75 = _percentile(bootstrap_returns, 75)
    p95 = _percentile(bootstrap_returns, 95)

    print(f"\n  実際の累計リターン:  {actual_total*100:+.2f}%")
    print(f"\n  ブートストラップ リターン分布:")
    print(f"    5th  percentile:   {p5*100:+.2f}%")
    print(f"    25th percentile:   {p25*100:+.2f}%")
    print(f"    50th (中央値):     {p50*100:+.2f}%")
    print(f"    75th percentile:   {p75*100:+.2f}%")
    print(f"    95th percentile:   {p95*100:+.2f}%")

    # 90% CI
    ci_low = _percentile(bootstrap_returns, 5)
    ci_high = _percentile(bootstrap_returns, 95)
    print(f"\n  90% 信頼区間:        [{ci_low*100:+.2f}%, {ci_high*100:+.2f}%]")

    # ゼロを含むか？
    if ci_low <= 0 <= ci_high:
        print(f"  ⚠ 信頼区間がゼロを含む → 統計的に有意でない可能性")
    elif ci_low > 0:
        print(f"  ✓ 信頼区間がゼロを含まない → リターンは有意にプラス")

    # DD分析
    dd_median = _percentile(shuffled_dds, 50)
    dd_95 = _percentile(shuffled_dds, 95)
    print(f"\n  実際の最大DD:        {actual_dd*100:.2f}%")
    print(f"  シャッフルDD中央値:  {dd_median*100:.2f}%")
    print(f"  シャッフルDD 95th:   {dd_95*100:.2f}%")

    if actual_dd > dd_95:
        print(f"  ⚠ 実際のDDがシャッフルより悪い → 不運な順序 or 系列相関あり")

    return {
        "ci_low": ci_low, "ci_high": ci_high,
        "bootstrap_median": p50,
        "actual_dd": actual_dd, "dd_95": dd_95,
        "includes_zero": ci_low <= 0 <= ci_high,
    }


# ── 5. Overfitting Risk Assessment ───────────────────────────────
def check_overfitting_warnings(
    trades: list[Trade], metrics: dict,
    wf_results: list[dict], sensitivity: dict, mc: dict,
) -> None:
    print("\n" + "=" * 60)
    print("  過学習リスク総合判定")
    print("=" * 60)

    warnings = 0
    checks = 0

    # (1) OOS劣化
    checks += 1
    if wf_results:
        valid_deg = [r["degradation"] for r in wf_results if abs(r["is_annual"]) > 0.005]
        avg_deg = _mean(valid_deg) if valid_deg else 0
        if avg_deg < -50:
            print(f"  [WARN] OOS平均劣化率: {avg_deg:.1f}% (閾値: -50%)")
            warnings += 1
        else:
            print(f"  [PASS] OOS平均劣化率: {avg_deg:.1f}% (閾値: -50%)")

    # (2) OOS期間で常にマイナスでないか
    checks += 1
    if wf_results:
        oos_neg = sum(1 for r in wf_results if r["oos_annual"] <= 0)
        ratio = oos_neg / len(wf_results)
        if ratio > 0.6:
            print(f"  [WARN] OOS期間の{oos_neg}/{len(wf_results)}がマイナス → レジーム不安定")
            warnings += 1
        else:
            print(f"  [PASS] OOS期間の{len(wf_results)-oos_neg}/{len(wf_results)}がプラス")

    # (3) 信頼区間がゼロを含むか
    checks += 1
    if mc["includes_zero"]:
        print(f"  [WARN] 90%CIがゼロを含む [{mc['ci_low']*100:+.1f}%, {mc['ci_high']*100:+.1f}%]")
        warnings += 1
    else:
        print(f"  [PASS] 90%CIがゼロを含まない [{mc['ci_low']*100:+.1f}%, {mc['ci_high']*100:+.1f}%]")

    # (4) 少数トレード依存: 上位3件を除外してリターンが50%以上減るか
    checks += 1
    returns = sorted([t[3] for t in trades], reverse=True)
    total = sum(returns)
    top3_removed = sum(returns[3:])
    if total > 0:
        drop_pct = (1 - top3_removed / total) * 100
        if drop_pct > 50:
            print(f"  [WARN] 上位3トレード除外で利益{drop_pct:.0f}%減 → 少数依存")
            warnings += 1
        else:
            print(f"  [PASS] 上位3トレード除外で利益{drop_pct:.0f}%減 (閾値: 50%)")
    else:
        print(f"  [WARN] 累計リターンがマイナス → 戦略自体が機能していない可能性")
        warnings += 1

    # (5) サンプルサイズ
    checks += 1
    n = len(trades)
    if n < 30:
        print(f"  [WARN] トレード数{n} → サンプル不足 (最低30推奨)")
        warnings += 1
    elif n < 50:
        print(f"  [NOTE] トレード数{n} → やや少ない (50以上推奨)")
    else:
        print(f"  [PASS] トレード数{n} → 十分なサンプル")

    # (6) ロングとショートの乖離
    checks += 1
    buy_ret = metrics.get("buy_return", 0)
    sell_ret = metrics.get("sell_return", 0)
    if buy_ret > 0 and sell_ret < 0 and abs(sell_ret) > buy_ret * 0.3:
        print(f"  [WARN] ショートが足を引っ張り (ロング{buy_ret*100:+.1f}%, ショート{sell_ret*100:+.1f}%)")
        print(f"         → ショート除外 or 別パラメータを検討")
        warnings += 1
    elif buy_ret < 0 and sell_ret > 0 and abs(buy_ret) > sell_ret * 0.3:
        print(f"  [WARN] ロングが足を引っ張り (ロング{buy_ret*100:+.1f}%, ショート{sell_ret*100:+.1f}%)")
        warnings += 1
    else:
        print(f"  [PASS] ロング/ショートのバランス (ロング{buy_ret*100:+.1f}%, ショート{sell_ret*100:+.1f}%)")

    # 判定
    print(f"\n  {'─'*40}")
    risk = "低" if warnings <= 1 else "中" if warnings <= 3 else "高"
    print(f"  チェック: {checks}項目 / 警告: {warnings}件")
    print(f"  過学習リスク: {risk}")

    if warnings <= 1:
        print("  → 戦略は比較的ロバスト")
    elif warnings <= 3:
        print("  → パラメータ調整や戦略修正を検討")
    else:
        print("  → 戦略の根本的な見直しが必要")


# ── Main ──────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Robust backtesting analysis")
    parser.add_argument("--tdir", required=True)
    parser.add_argument("--lc", type=float, default=0.03)
    parser.add_argument("--lp", type=float, default=0.06)
    parser.add_argument("--tick", type=float, default=5)
    parser.add_argument("--start-date", default="2013/01/01")
    parser.add_argument("--min-bars", type=int, default=3)
    parser.add_argument("--max-bars", type=int, default=5)
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data" / args.tdir
    csv_files = sorted(data_dir.glob("*.csv"))
    cs = load_csv(csv_files)

    parts = args.start_date.split("/")
    start_date = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
    end_date = cs[len(cs) - 1].date
    dma_periods = [10, 25]

    print("=" * 60)
    print(f"  オークマ(6103) ロバスト性検証")
    print(f"  期間: {start_date} ~ {end_date}")
    print(f"  パラメータ: LC={args.lc*100}% TP={args.lp*100}% Tick={args.tick}")
    print(f"  押し目: {args.min_bars}〜{args.max_bars}本 / DMA: {dma_periods}")
    print("=" * 60)

    # 基本バックテスト
    trades = run_backtest(cs, start_date, None, args.lc, args.lp, args.tick, args.min_bars, args.max_bars, dma_periods)
    metrics = compute_metrics(trades, start_date, end_date)
    print_metrics(metrics)

    # Walk-Forward
    wf = walk_forward_analysis(cs, args.lc, args.lp, args.tick, args.min_bars, args.max_bars, dma_periods)

    # パラメータ感度
    sens = parameter_sensitivity(cs, start_date, None, args.lc, args.lp, args.tick, args.min_bars, args.max_bars, dma_periods)

    # モンテカルロ
    mc = monte_carlo_analysis(trades)

    # 過学習リスク総合判定
    check_overfitting_warnings(trades, metrics, wf, sens, mc)


if __name__ == "__main__":
    main()
