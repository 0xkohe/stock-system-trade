# 8306 Rule Spec

## Final Candidate

8306 専用の現時点の最有力候補は `0.5% + 前日高安手仕舞い`。

- DMA: `10`
- Pullback condition: `直近7本の中に逆行足が3本以上`
- Sides: `long + short`
- Entry timing:
  - Long: `前日終値 + 0.5%` 到達でエントリー
  - Short: `前日終値 - 0.5%` 到達でエントリー
- Exit:
  - Long: `前日安値` 割れで手仕舞い
  - Short: `前日高値` 超えで手仕舞い
- 現行実装では `当日エントリー・翌日以降手仕舞い判定`

## Interpretation

- 固定 `LC 3% / TP 6%` は使わない
- 毎日、前日高値/安値ベースでストップが更新される
- エントリーは現行ブレイクより少し早く、出口は価格構造ベースで追随する

## Validation Snapshot

- Gross:
  - IS `+142.4% / PF 1.69 / DD 23.3% / N 265`
  - OOS `+143.6% / PF 1.83 / DD 19.5% / N 253`
- Costed:
  - one-way `0.10%`: OOS `+93.0% / PF 1.46 / DD 22.3%`
  - one-way `0.20%`: OOS `+42.4% / PF 1.18 / DD 29.8%`

## Saved Artifacts

- Aggressive comparison CSV: [results_8306_aggressive_compare.csv](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_compare.csv)
- Aggressive yearly CSV: [results_8306_aggressive_yearly.csv](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_yearly.csv)
- Cost scenarios CSV: [results_8306_aggressive_costs.csv](/home/kooooohe/Documents/tech/stock/py/results_8306_aggressive_costs.csv)
- B vs candidates yearly CSV: [results_8306_yearly.csv](/home/kooooohe/Documents/tech/stock/py/results_8306_yearly.csv)
- s3 lb7 vs s3 lb8 yearly CSV: [results_8306_s3lb7_s3lb8_yearly.csv](/home/kooooohe/Documents/tech/stock/py/results_8306_s3lb7_s3lb8_yearly.csv)
- B charts:
  - [chart_1year.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_1year.png)
  - [chart_2016.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2016.png)
  - [chart_2018.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2018.png)
  - [chart_2025.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_b/chart_2025.png)
- Aggressive charts:
  - [chart_1year.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_1year.png)
  - [chart_2016.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2016.png)
  - [chart_2018.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2018.png)
  - [chart_2025.png](/home/kooooohe/Documents/tech/stock/py/charts/8306_aggressive/chart_2025.png)
