# stock-backtester

このディレクトリは、日本株の時系列 CSV を使って押し目買い / 戻し売り戦略を検証するための検証用スクリプト置き場です。  
中心ロジックは [`src/backtester`](/home/kooooohe/Documents/tech/stock/py/src/backtester) にあり、ルート直下の `*.py` は個別の比較実験・分析・可視化用スクリプトです。

データ本体はこの配下ではなく、1つ上の `data/` を参照します。

## 基本構成

- [`pyproject.toml`](/home/kooooohe/Documents/tech/stock/py/pyproject.toml)
  `backtester` パッケージ定義。CLI エントリポイントは `backtester = backtester.__main__:main`。
- [`uv.lock`](/home/kooooohe/Documents/tech/stock/py/uv.lock)
  依存解決結果。
- [`main.py`](/home/kooooohe/Documents/tech/stock/py/main.py)
  雛形のエントリポイント。現状は `Hello from stock-backtester!` を出すだけで、実運用では未使用。
- [`8306_rule_spec.md`](/home/kooooohe/Documents/tech/stock/py/8306_rule_spec.md)
  8306 向けの最終候補ルール仕様と、主要成果物へのリンク。

## 実行の入口

- データ取得: [`fetch_data.py`](/home/kooooohe/Documents/tech/stock/py/fetch_data.py)
  `yfinance` から `../data/<ticker>/<ticker>.T.csv` を Shift_JIS で保存。
- 汎用バックテスト CLI: [`src/backtester/__main__.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/__main__.py)
  `--tdir`, `--lc`, `--lp`, `--tick`, `--start-date`, `--down-steps`, `--lookback`, `--dma`, `--exit-mode` を受け取り、年別・合計成績を標準出力に表示。

  ```bash
  # 従来の固定 LC/TP モード（デフォルト）
  uv run python -m backtester --tdir 8306 --lc 0.03 --lp 0.06

  # 8306 ルールスペック: 前日高安ブレイク + 前日高安手仕舞い
  uv run python -m backtester --tdir 8306 --dma 10 --down-steps 3 --lookback 7 --exit-mode prev_bar
  ```

  | オプション | デフォルト | 説明 |
  |-----------|-----------|------|
  | `--tdir` | (必須) | 銘柄フォルダ名 |
  | `--lc` | 0.03 | ロスカット率（`fixed` モード用） |
  | `--lp` | 0.06 | 利確率（`fixed` モード用） |
  | `--tick` | 5 | 値刻み |
  | `--start-date` | 2013/01/01 | 開始日 |
  | `--down-steps` | 3 | 逆行足の最低本数 |
  | `--lookback` | 5 | 逆行足を数える直近本数 |
  | `--dma` | 10,25 | DMA 期間（カンマ区切り） |
  | `--exit-mode` | fixed | `fixed`（固定 LC/TP）または `prev_bar`（前日高安手仕舞い） |
- 汎用チャート出力: [`chart.py`](/home/kooooohe/Documents/tech/stock/py/chart.py)
  指定銘柄の売買ポイント付きチャートとエクイティカーブを `charts/` に出力。

## コアモジュール

- [`src/backtester/candle.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/candle.py)
  CSV 読み込みと `CandleStick` / `CandleSticks`、DMA 計算。
- [`src/backtester/strategy.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/strategy.py)
  押し目 / 戻しシグナル判定。`dma_periods`, `down_steps`, `lookback`, `trend_filter_period` を持つ。
- [`src/backtester/position.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/position.py)
  ロング / ショートの建玉管理、LC/TP、5円刻み丸め。
- [`src/backtester/score.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/score.py)
  エントリー/イグジット記録、年別集計、合計集計。
- [`src/backtester/__init__.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/__init__.py)
  パッケージ初期化。

## 6103 系の分析スクリプト

- [`analyze.py`](/home/kooooohe/Documents/tech/stock/py/analyze.py)
  6103 の通常バックテスト詳細分析。3〜5本、2〜4本、3〜7本の3条件を標準出力で比較。
- [`robust_analysis.py`](/home/kooooohe/Documents/tech/stock/py/robust_analysis.py)
  ロバスト性確認。基本指標、Walk-Forward、感度分析、モンテカルロ、過学習警告を標準出力で表示。
- [`compare_steps.py`](/home/kooooohe/Documents/tech/stock/py/compare_steps.py)
  `down_steps × lookback` のグリッド比較。ロング+ショート、ロングのみ、DMA別の比較表を表示。
- [`compare_steps_detail.py`](/home/kooooohe/Documents/tech/stock/py/compare_steps_detail.py)
  複数設定の年別詳細比較。全体/ロング/ショート別に表形式で出す。
- [`compare_dma_modes.py`](/home/kooooohe/Documents/tech/stock/py/compare_dma_modes.py)
  DMA 判定方式の比較。独立判定、両方上向き必須、10DMAトリガ、10DMAのみ、25DMAのみを比較。
- [`compare_trend_filters.py`](/home/kooooohe/Documents/tech/stock/py/compare_trend_filters.py)
  基準戦略に 25DMA / 75DMA の方向フィルタを入れた時の差を比較。
- [`compare_next_ideas.py`](/home/kooooohe/Documents/tech/stock/py/compare_next_ideas.py)
  次の改善案比較。`25DMA方向 + 10DMAタイミング` と `ロング/ショート分離` を基準戦略と比較。
- [`compare_other_tickers.py`](/home/kooooohe/Documents/tech/stock/py/compare_other_tickers.py)
  6103 で見えた改善案を他銘柄へ横展開し、A基準と B改善案の差分を標準出力で確認。
- [`chart.py`](/home/kooooohe/Documents/tech/stock/py/chart.py)
  6103 向けの汎用チャート出力にも使っている。デフォルトで `charts/chart_1year.png` などを生成。

## 8306 系の分析スクリプト

- [`explore_8306.py`](/home/kooooohe/Documents/tech/stock/py/explore_8306.py)
  8306 向け小規模ルール探索。IS/OOS 分割で候補をランキング表示。
- [`check_8306_stability.py`](/home/kooooohe/Documents/tech/stock/py/check_8306_stability.py)
  B案近傍の `steps/lookback` 安定性確認。標準出力のみ。
- [`compare_8306_aggressive.py`](/home/kooooohe/Documents/tech/stock/py/compare_8306_aggressive.py)
  B案に対するアグレッシブ変更の比較。出力 CSV は `results_8306_aggressive_compare.csv`。
- [`cost_8306_aggressive.py`](/home/kooooohe/Documents/tech/stock/py/cost_8306_aggressive.py)
  8306 最有力ルールに片道コストを載せて再計算。出力 CSV は `results_8306_aggressive_costs.csv`。
- [`validate_8306_live_risks.py`](/home/kooooohe/Documents/tech/stock/py/validate_8306_live_risks.py)
  8306 候補の live リスク検証。同日両ヒットや保守約定モデルも含めて標準出力で検証。
- [`compare_long_vs_hold.py`](/home/kooooohe/Documents/tech/stock/py/compare_long_vs_hold.py)
  AGG long-only と buy-and-hold を 8306 / 6103 で比較。OOS・コスト込みの比較表を表示。
- [`compare_aggressive_other_tickers.py`](/home/kooooohe/Documents/tech/stock/py/compare_aggressive_other_tickers.py)
  B案と AGG 案を他銘柄へ展開して比較。出力 CSV は `results_aggressive_other_tickers.csv`。
- [`plot_8306_b_trades.py`](/home/kooooohe/Documents/tech/stock/py/plot_8306_b_trades.py)
  8306 B案の売買ポイント付きチャートを `charts/8306_b/` に出力。
- [`plot_8306_aggressive_trades.py`](/home/kooooohe/Documents/tech/stock/py/plot_8306_aggressive_trades.py)
  8306 AGG 案の売買ポイント付きチャートを `charts/8306_aggressive/` に出力。

## 6103 AGG 可視化

- [`plot_6103_aggressive_trades.py`](/home/kooooohe/Documents/tech/stock/py/plot_6103_aggressive_trades.py)
  6103 に AGG ルールを当てたチャートを `charts/6103_aggressive/` に出力。

## 生成済み CSV の意味

- [`results_yearly.csv`](/home/kooooohe/Documents/tech/stock/py/results_yearly.csv)
  6103 の A/B/C 候補の年別比較結果。
- [`results_8306_yearly.csv`](/home/kooooohe/Documents/tech/stock/py/results_8306_yearly.csv)
  8306 の A/B/C 候補の年別比較結果。
- [`results_8306_s3lb7_s3lb8_yearly.csv`](/home/kooooohe/Documents/tech/stock/py/results_8306_s3lb7_s3lb8_yearly.csv)
  8306 の `steps=3 lookback=7/8` 周辺を含む年別比較結果。
- [`results_8306_aggressive_compare.csv`](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_compare.csv)
  8306 B案と各アグレッシブ変更案の IS/OOS 比較。
- [`results_8306_aggressive_yearly.csv`](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_yearly.csv)
  8306 の B案と AGG 案の年別比較。
- [`results_8306_aggressive_costs.csv`](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_costs.csv)
  8306 AGG 案にコストを乗せた場合の IS/OOS 比較。
- [`results_aggressive_other_tickers.csv`](/home/kooooohe/Documents/tech/stock/py/results_aggressive_other_tickers.csv)
  8306 AGG 案を他銘柄へ広げた比較結果。`b_*` は B案、`agg_*` は AGG 案、`d_*` は差分。

## 生成済み画像の意味

- [`charts/chart_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/chart_1year.png)
- [`charts/chart_3months.png`](/home/kooooohe/Documents/tech/stock/py/charts/chart_3months.png)
- [`charts/chart_2024.png`](/home/kooooohe/Documents/tech/stock/py/charts/chart_2024.png)
- [`charts/chart_2025.png`](/home/kooooohe/Documents/tech/stock/py/charts/chart_2025.png)
  `chart.py` が出す 6103 の売買ポイント付きチャート。
- [`charts/equity_curve.png`](/home/kooooohe/Documents/tech/stock/py/charts/equity_curve.png)
  `chart.py` が出す全期間エクイティカーブ。
- [`charts/8306_b/chart_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_1year.png)
- [`charts/8306_b/chart_2016.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2016.png)
- [`charts/8306_b/chart_2018.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2018.png)
- [`charts/8306_b/chart_2025.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2025.png)
  8306 B案の可視化。
- [`charts/8306_aggressive/chart_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_1year.png)
- [`charts/8306_aggressive/chart_2016.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2016.png)
- [`charts/8306_aggressive/chart_2018.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2018.png)
- [`charts/8306_aggressive/chart_2025.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2025.png)
  8306 AGG 案の可視化。
- [`charts/6103_aggressive/chart_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/6103_aggressive/chart_1year.png)
- [`charts/6103_aggressive/chart_2013.png`](/home/kooooohe/Documents/tech/stock/py/charts/6103_aggressive/chart_2013.png)
- [`charts/6103_aggressive/chart_2020.png`](/home/kooooohe/Documents/tech/stock/py/charts/6103_aggressive/chart_2020.png)
- [`charts/6103_aggressive/chart_2024.png`](/home/kooooohe/Documents/tech/stock/py/charts/6103_aggressive/chart_2024.png)
  6103 AGG 案の可視化。
- [`charts/8306_aggressive_split/chart_winners_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive_split/chart_winners_1year.png)
- [`charts/8306_aggressive_split/chart_winners_2016.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive_split/chart_winners_2016.png)
- [`charts/8306_aggressive_split/chart_losers_1year.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive_split/chart_losers_1year.png)
- [`charts/8306_aggressive_split/chart_losers_2016.png`](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive_split/chart_losers_2016.png)
  現在のソース一覧には対応スクリプトが見当たらない既存成果物。過去に別スクリプトで作られた可能性が高い。

## 自動生成物・補足

- [`src/stock_backtester.egg-info`](/home/kooooohe/Documents/tech/stock/py/src/stock_backtester.egg-info)
  パッケージメタデータ。配布用の自動生成物。
- [`__pycache__`](/home/kooooohe/Documents/tech/stock/py/__pycache__)
- [`src/backtester/__pycache__`](/home/kooooohe/Documents/tech/stock/py/src/backtester/__pycache__)
  Python のキャッシュ。
- [`.venv`](/home/kooooohe/Documents/tech/stock/py/.venv)
  ローカル仮想環境。
- [`.python-version`](/home/kooooohe/Documents/tech/stock/py/.python-version)
  Python バージョン管理用設定。

## ひとまず見るべきファイル

全体を追うなら、まず次の順が分かりやすいです。

1. [`src/backtester/strategy.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/strategy.py)
2. [`src/backtester/position.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/position.py)
3. [`src/backtester/__main__.py`](/home/kooooohe/Documents/tech/stock/py/src/backtester/__main__.py)
4. [`compare_8306_aggressive.py`](/home/kooooohe/Documents/tech/stock/py/compare_8306_aggressive.py)
5. [`8306_rule_spec.md`](/home/kooooohe/Documents/tech/stock/py/8306_rule_spec.md)
