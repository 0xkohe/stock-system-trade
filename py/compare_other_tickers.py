"""A基準とB改善案を他銘柄で横展開比較する。"""
from __future__ import annotations

import datetime
from pathlib import Path

from backtester.candle import load_csv
from backtester.position import Position
from backtester.strategy import PullbackStrategy


Trade = tuple[datetime.date, str, int, float]


def run_backtest(cs, start_date, lc, lp, tick, strategy) -> list[Trade]:
    pos = Position(lc=lc, lp=lp, tick=tick)
    skip = 60
    trades: list[Trade] = []
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
            if ok and entry_info:
                trades.append((*entry_info, per))
                entry_info = None
            continue

        if pos.is_selling():
            _, per, ok = pos.try_buy_back(v)
            if ok and entry_info:
                trades.append((*entry_info, per))
                entry_info = None
            continue

        yesterday = cs[i - 1]
        buy_sig, buy_period = strategy.check_buy_signal(cs, i)
        if buy_sig:
            p = yesterday.high if v.open <= yesterday.high else v.open
            pos.buy(p, v)
            entry_info = (v.date, "BUY", buy_period)
            continue

        sell_sig, sell_period = strategy.check_sell_signal(cs, i)
        if sell_sig:
            p = yesterday.low if v.open >= yesterday.low else v.open
            pos.short_sell(p, v)
            entry_info = (v.date, "SELL", sell_period)
            continue

    return trades


def stats(trades: list[Trade]) -> tuple[float, float, float, float, int]:
    n = len(trades)
    wins = [t for t in trades if t[3] > 0]
    losses = [t for t in trades if t[3] <= 0]
    ret = sum(t[3] for t in trades)
    wr = len(wins) / n * 100 if n else 0.0
    pf = sum(t[3] for t in wins) / abs(sum(t[3] for t in losses)) if losses and sum(t[3] for t in losses) != 0 else 0.0
    cum = peak = dd = 0.0
    for t in trades:
        cum += t[3]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return ret, wr, pf, dd, n


def fmt_pct(v: float) -> str:
    return f"{v*100:+.1f}%"


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_root = base_dir / "data"
    start = datetime.date(2013, 1, 1)
    lc, lp, tick = 0.03, 0.06, 5

    tickers = ["6135", "6361", "6481", "8306", "8601", "8604"]
    baseline = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5)
    improved = PullbackStrategy(dma_periods=[10], down_steps=3, lookback=5, trend_filter_period=25)

    print("=" * 108)
    print("  他銘柄での A基準 vs B改善案 比較")
    print("=" * 108)
    print(
        f"  {'ticker':<6} {'A Ret':>8} {'A PF':>6} {'A DD':>7} {'A N':>5}  "
        f"{'B Ret':>8} {'B PF':>6} {'B DD':>7} {'B N':>5}  "
        f"{'dRet':>8} {'dPF':>6} {'dDD':>7}"
    )
    print("  " + "-" * 102)

    ret_improved = 0
    pf_improved = 0
    dd_improved = 0
    rows = []

    for ticker in tickers:
        data_dir = data_root / ticker
        csv_files = sorted(data_dir.glob("*.csv"))
        cs = load_csv(csv_files)
        a_trades = run_backtest(cs, start, lc, lp, tick, baseline)
        b_trades = run_backtest(cs, start, lc, lp, tick, improved)

        a_ret, _, a_pf, a_dd, a_n = stats(a_trades)
        b_ret, _, b_pf, b_dd, b_n = stats(b_trades)
        d_ret = b_ret - a_ret
        d_pf = b_pf - a_pf
        d_dd = b_dd - a_dd

        rows.append((ticker, a_ret, a_pf, a_dd, a_n, b_ret, b_pf, b_dd, b_n, d_ret, d_pf, d_dd))
        if d_ret > 0:
            ret_improved += 1
        if d_pf > 0:
            pf_improved += 1
        if d_dd < 0:
            dd_improved += 1

        print(
            f"  {ticker:<6} {fmt_pct(a_ret):>8} {a_pf:>6.2f} {a_dd*100:>+6.1f}% {a_n:>5}  "
            f"{fmt_pct(b_ret):>8} {b_pf:>6.2f} {b_dd*100:>+6.1f}% {b_n:>5}  "
            f"{fmt_pct(d_ret):>8} {d_pf:>+6.2f} {d_dd*100:>+6.1f}%"
        )

    avg_a_ret = sum(r[1] for r in rows) / len(rows)
    avg_a_pf = sum(r[2] for r in rows) / len(rows)
    avg_a_dd = sum(r[3] for r in rows) / len(rows)
    avg_b_ret = sum(r[5] for r in rows) / len(rows)
    avg_b_pf = sum(r[6] for r in rows) / len(rows)
    avg_b_dd = sum(r[7] for r in rows) / len(rows)
    avg_d_ret = sum(r[9] for r in rows) / len(rows)
    avg_d_pf = sum(r[10] for r in rows) / len(rows)
    avg_d_dd = sum(r[11] for r in rows) / len(rows)

    print("  " + "-" * 102)
    print(
        f"  {'avg':<6} {fmt_pct(avg_a_ret):>8} {avg_a_pf:>6.2f} {avg_a_dd*100:>+6.1f}% {'':>5}  "
        f"{fmt_pct(avg_b_ret):>8} {avg_b_pf:>6.2f} {avg_b_dd*100:>+6.1f}% {'':>5}  "
        f"{fmt_pct(avg_d_ret):>8} {avg_d_pf:>+6.2f} {avg_d_dd*100:>+6.1f}%"
    )
    print()
    print(f"  Ret改善: {ret_improved}/{len(rows)} 銘柄")
    print(f"  PF改善:  {pf_improved}/{len(rows)} 銘柄")
    print(f"  DD改善:  {dd_improved}/{len(rows)} 銘柄")


if __name__ == "__main__":
    main()
