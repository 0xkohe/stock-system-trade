"""株価データを取得してCSV保存するスクリプト"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yfinance as yf


def fetch_ticker(ticker_code: str) -> None:
    ticker = f"{ticker_code}.T"
    data_root = Path(__file__).resolve().parent.parent / "data"
    out_dir = data_root / ticker_code
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ticker}.csv"

    print(f"Fetching {ticker}...")
    df = yf.download(ticker, period="max", auto_adjust=False, progress=False)
    if df.empty:
        print(f"Error: no data returned for {ticker}")
        return

    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    df = df.sort_index(ascending=False)

    with open(out_file, "w", encoding="shift_jis", errors="replace") as f:
        f.write("日付,始値,高値,安値,終値,出来高,調整後終値\n")
        for date, row in df.iterrows():
            date_str = f"{date.year}/{date.month}/{date.day}"
            o = float(row["Open"]) if row["Open"] == row["Open"] else 0
            h = float(row["High"]) if row["High"] == row["High"] else 0
            l = float(row["Low"]) if row["Low"] == row["Low"] else 0
            c = float(row["Close"]) if row["Close"] == row["Close"] else 0
            v = int(row["Volume"]) if row["Volume"] == row["Volume"] else 0
            adj_src = row.get("Adj Close", c)
            adj = float(adj_src) if adj_src == adj_src else c
            f.write(f"{date_str},{o},{h},{l},{c},{v},{adj}\n")

    print(f"Saved {len(df)} rows to {out_file}")
    print(f"Date range: {df.index.min().date()} ~ {df.index.max().date()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch JP stock history via yfinance")
    parser.add_argument("tickers", nargs="*", help="Ticker codes without .T suffix")
    args = parser.parse_args()

    tickers = args.tickers or ["6103"]
    ok = False
    for ticker in tickers:
        fetch_ticker(ticker)
        ok = True

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
