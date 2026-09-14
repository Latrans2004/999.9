# コバルト：一次資料の比較・差異台帳

2026-09-15。A0の認証取得と分類確認を進め、A2/A3に相当する主要国・主要年の照合を実施した。
全期間の取得・検証完了ではない。既存の処理結果を否定する監査ではなく、採用する数値の根拠を強化する作業。
公開数値・HHI・HS範囲の変更はない。

## 確認結果と採否

値の単位は、貿易貨物重量を除き各資料に記載されたコバルト量のトン。
PDFページはファイル先頭を1とする。`data/review/cobalt/source-review.json` に
原本ハッシュ・表位置・数値・比較計算を保存。PDF原表は画像でも確認した。
`human_reviewed: false` は維持し、エージェントの照合を人間の承認と扱わない。

| 論点 | 原数値と照合結果 | 判断 |
|---|---|---|
| カナダ2024鉱山生産 | USGS MCS2025: 4,500 → MCS2026: 3,350。NRCan: 3,351、BGS: 3,351 | 最新USGSの丸め値は国内統計と整合。旧4,500を新版と混在させない |
| カナダ2023鉱山生産 | USGS MCS2025: 4,220、BGS最新版: 5,099、NRCan最新版: 3,260 | 未解決。2024の一致を過去年の正しさに一般化しない |
| DRC2024鉱山生産 | USGS MCS2025: 220,000 → MCS2026: 226,000、BGS: 200,253 | 大きな差が残る。政府の販売量198,844.05と同じ測定対象とは限らない |
| インドネシア2024鉱山生産 | USGS 28,000 → 35,000、BGS: 31,570 | 改訂・推計差。企業報告との対応を追う必要あり |
| トルコ2024鉱山生産 | USGS最新版: 2,200、BGS: 425 | 未解決。数値の大きさだけで採否を決めない |
| 世界2024鉱山生産 | USGS 290,000 → 302,000、BGS: 269,000 | 定義・推計・国別内訳が異なるため平均しない |
| DRC政府サイトの年次表示 | ダッシュボードは「2024」139,840。2023年報p17は139,840.09、2024年報p26は198,777.21 | 年次表示または更新の不整合が疑われる。ダッシュボード値を2024年値に採用しない |
| DRC2023輸出の版間差 | 2023年報p17: 139,840.09 → 2024年報p26: 152,798.86（約9.27%増） | 同一年が後年報で改訂。原因説明未確認。年報の版を必ず保持 |
| DRC2024販売量と輸出量 | 2024年報p22表32: 198,844.05、p26表35輸出: 198,777.21 | 販売量には国内販売を含む旨の注記がある。66.84の差を誤記と断定しない |
| DRC2024のComtrade輸出 | 260500・810520・追加検討282200はいずれも空応答 | ゼロ輸出ではない。主要供給国が欠ける全reporter輸出集計を世界全体と扱えない |

根拠：USGS [MCS2025](https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-cobalt.pdf)・
[MCS2026](https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-cobalt.pdf)各p2、
[BGS World Mineral Production 2020–2024](https://nora.nerc.ac.uk/id/eprint/541620/1/WMP_2020%20to%202024.pdf)p25（印刷p15）、
[NRCan Cobalt facts](https://natural-resources.canada.ca/minerals-mining/mining-data-statistics-analysis/minerals-metals-facts/cobalt-facts)国内生産表、
DRC鉱山省[統計一覧](https://mines.gouv.cd/statistique/pdf)・[2023年報](https://mines.gouv.cd/download/4)・[2024年報](https://mines.gouv.cd/download/3)。

## 独立した裏付けとして数えられる範囲

- NRCanの国内鉱山統計はNRCan/Statistics Canada由来。一方、同ページの国際比較はUSGS由来で、
  国内部分より古い数値（DRC220,000、インドネシア28,000）を含む。USGSの独立した追認に数えない。
  カナダの精製量5,920（2024）も鉱山量3,351と区別する。
- BGSは含有金属量と実回収量の報告基準が国によって不明確で、両者が混在しうると注記する。
  モロッコ・南アフリカは脚注(a)の金属／精製量。世界計を完全に同じ定義の別測定とはみなさない。
- [Glencore 2024 production report](https://www.glencore.com/.rest/api/v1/documents/static/437c6cdb-dbfb-4e61-a769-18655951cee2/Glencore+production+report_FY2024.pdf)
  p4のKCC・Mutandaは35.1kt。グループ全体38.2ktをDRCだけの生産と扱わない。
  p5脚注は精鉱・水酸化物に含まれるCo量、支配事業原則100%（例外は脚注）の集計基準。
- [CMOC 2024 results](https://en.cmoc.com/html/2025/News_0324/73.html)は114,165tの企業生産を報告。
  企業生産・政府販売・税関輸出には在庫・時点・持分／対象範囲の差がありうる。
  CMOCとGlencoreを足した数字を全国生産や輸出の確定値にはしない。
- USGSの国別残余「Other countries」は版間で構成が変わった（2025版に別掲のニューカレドニアが
  2026版では別掲されず、中国が別掲される）。単一国としてHHIへ入れたり同一国として比較しない。
  国別行合計と丸められた世界計の残差も台帳に保存し、黙って配賦しない。

## 認証貿易取得と分類

[Actions実行34882080432](https://github.com/Latrans2004/999.9/actions/runs/34882080432)は成功。
登録済みキーはActions環境へ注入し、値をローカル取得・表示していない。
12クエリはすべてHTTP200、8件に観測あり、4件は空。クエリ群合計158行。
Worldと二国間、全reporterと中国単独のクエリは重なるため、158件の独立取引とは呼ばない。

| 年 | HS | DRC輸出・全相手 | 中国輸入・全相手 | 全reporter輸出・World |
|---|---|---:|---:|---:|
| 2017 | 260500 | 8 (H4) | 9 (H5) | 未取得 |
| 2017 | 810520 | 空 | 26 (H5) | 未取得 |
| 2024 | 260500 | 空 | 7 (H6) | 26 (H6) |
| 2024 | 810520 | 空 | 22 (H6) | 46 (H6) |
| 2024 | 282200（候補） | 空 | 14 (H6) | 未取得 |

上限5,000行への到達・認証取得での429はなかった。契約上限そのものは未確認であり、
この試行から全世界・全相手の取得可能性を保証しない。preview時の429履歴もそのまま保持。

2017年HS260500のDRC→中国は、中国輸入100,120,283kg／USD339,950,461に対し、
DRC輸出63,558,048kg／USD183,428,737.633。重量約1.575倍、金額約1.853倍の不一致がある。
輸入CIF・輸出FOB、時点・原産国／仕向地などの差を調べる必要があり、原因を確定していない。
自動ミラー置換や単純平均は行わない。

国連の[H6–H5](https://unstats.un.org/unsd/classifications/Econ/tables/HS2022toHS2017ConversionAndCorrelationTables.xlsx)・
[H6–H4](https://unstats.un.org/unsd/classifications/Econ/tables/HS2022toHS2012ConversionAndCorrelationTables.xlsx)・
[H5–H4](https://unstats.un.org/unsd/classifications/Econ/tables/HS2017toHS2012ConversionAndCorrelationTables.xlsx)
のConversion/Correlation両シートで260500・810520・282200の18対応行を確認し、すべて1:1。
今回の3コードについて、HS版変更だけを上記貿易差の説明にはできない。

260500は鉱石・精鉱、810520はコバルト製錬中間品・未加工コバルト・粉、282200は酸化物・水酸化物。
810520を単一の精製段階と呼ばず、HS間の重量を合算しない。
2024年中国のDRC由来810520輸入は628,191,018kg（貨物重量）。
USGSの226,000t（鉱山含有Co量）との大小関係から誤りとは判定できず、品位係数なしに換算しない。
中国World輸入の重量は両headlineコードで推計フラグあり。DRC相手の上記重量は推計フラグなし。
元フラグを保持し、「推計でない」を独立検証済みと解釈しない。
282200の中国輸入にDRC相手行は観測されなかったが、これだけで対象品の流通ゼロとはしない。
追加の採否は保留し、headline2コードを維持する。

## 再現と次の作業

リポジトリルートから以下を実行する（オフライン、公開ファイルへの書込みなし）。

```text
python -m pipeline.cobalt_sources
python -m pipeline.cobalt_collect
python -m pipeline.cobalt_review
python -m pipeline.cobalt_probe
```

初期10原本、認証12応答、追加14資料を保存済み。比較台帳はUSGSを含む16資料と18対応行を照合し、
60件の原数値と比較計算を再生成する。原本ハッシュと転記値の正しさは別の検証である。
取得時台帳の`archived_unreviewed`は取得時点の状態として残し、本照合の範囲は別台帳へ記録した。

残作業は2017〜2024全期間の鉱山年報・貿易取得、未解決国の定義／改訂照合、
国母集団とカバレッジ確定、系列採用、鉱山／段階別の公開判定。
今回は全期間のカバレッジ分母やHHIを確定していない。
実装時は最新の `docs/task-e-mineral-rollout.md` のPetralysis出力契約に従う。
