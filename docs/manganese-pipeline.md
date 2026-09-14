# マンガン鉱石・精鉱の検証パイプライン

対象は **HS260200、暦年2017–2024**。合金、金属マンガン、酸化物・硫酸塩などの電池材料を含めない。
過去データの追加取得とHS2007対応は [追加検証報告](manganese-history-2026-09-14.md) を参照。
監査専用で、公開JSON/HTML・既存リチウム/黒鉛の選択規則には接続しない。
診断と人間による値の採用を分離し、全成果物の `publishable` は常に `false`。

## 既存設計との差分

調査開始時のHEADは `062cc09`、追跡済みファイルの変更はなかった。
作業ツリー・対象ディレクトリ・祖先ディレクトリで `AGENTS.md` は確認できなかった。
添付「天然黒鉛パイプライン 実装引継ぎメモ」の実ファイルはこのセッションでは取得できなかったため、
ユーザーが本文に指定した7要件と `natural-graphite-pipeline.md`、`lithium-pipeline.md` を設計前提にした。

現行黒鉛は `graphite.py` と `graphite_usgs.py`。`graphite_anchor.py`、企業discover/CSVはまだない。
`mirror_allowlist` はリチウムの炭酸塩設定にのみ存在する。黒鉛の `compare` は25%差や
ミラー欠落を同じ未解決フラグに含め、無争点行では自己申告重量を仮選択する。
マンガンにはこの部分を流用せず、strict normalizer、Raw archive、entity registry、
計測診断とRawからの再正規化を共有する。既存77件のテストと期待値は変更していない。

ローカルレビュー設定ファイルはなかった。GitHub公開rulesets APIは空配列を返したが、
mainのbranch protection APIは401だった。**保護規則や必須レビューがないとは結論しない**。
取得結果は `data/review/manganese-research/repository-review-settings.json` に保存した。
既存Actionsはリチウム更新、旧汎用更新、黒鉛監査、テスト/Pages公開を確認した。
今回追加した2ワークフローにはcommit、push、deployがなく、既存設定は変更していない。

## 公式分類と重量

| 項目 | 定義と扱い |
|---|---|
| HS260200 | マンガン鉱石・精鉱。乾燥重量基準でMn20%以上の鉄質マンガン鉱石・精鉱を含む。品位条件は分類条件であり、貿易重量が乾燥トンであるという意味ではない。 |
| 分類変更 | [UNSD HS2012](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/32/260200)から[HS2017](https://unstats.un.org/unsd/classifications/Econ/Detail/EN/2089/260200)の対応と、[WCO HS2022 Chapter 26](https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-2022/2022/0526_2022e.pdf) p.1を確認。6桁コード・品目定義の分割/統合はない。H4/H5/H6を保持し、未確認分類を拒否。対象期間を越えて自動延長しない。 |
| 貿易 | Comtrade `netWgt` kg、欠損時のみ補助数量の単位コード8（kg）。kg/1,000でmetric tonnes。水分不明の鉱石・精鉱貨物重量として記録し、乾燥鉱石量や含有Mn量と同一視しない。[UN数量単位](https://uncomtrade.org/docs/supplementary-quantity-units/)。ゼロと欠損を区別し、推計フラグと元数量を保存。 |
| 金額 | 原報告USDを保持。一般に輸入CIF・輸出FOBであり、全国一律の運賃調整・価格からの重量推計は行わない。[UN trade valuation](https://uncomtrade.org/docs/trade-valuation/)。 |
| USGS生産 | MCS2026 p.1の基本単位は千metric tons、p.2のWorld Mine Productionは明示的に**含有Mn量**。参考抽出は1,000倍という単位換算のみ行う。鉱石重量への品位換算はしない。米国需給表のgross weightや、合金も含む見掛消費量を輸出アンカーにしない。 |
| South32 | 年次報告2024は6月30日終了年度。豪州/南アの生産販売表はkwmt（千湿量トン）かつSouth32持分。国全体・暦年・乾燥量とは異なる。価格のdmtuと生産量のkwmtも区別する。 |
| Eramet | 年次決算の鉱石＋焼結鉱生産、輸送、外販は異なるmeasure。Comilog値はガボン全国の輸出と同じでない。資料p.19の年度/四半期列と小数表記・単位、水分、焼結鉱範囲を人間が確認するまでCSVに値を追加しない。 |

企業原本は `pipeline/manganese_sources.json` で特定し、取得履歴・SHA256・パスは
`data/review/manganese-evidence/discover.json` で追跡できる。
参照した生産統計は[USGS MCS2026](https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-manganese.pdf)、
[MCS2025](https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-manganese.pdf)。新版では豪州・ガーナの2024年値に
大きな改訂がある旨が明記されており、旧版と混ぜて同一vintageの時系列とは表示しない。

## 実行

```sh
python -m pip install -r pipeline/requirements.txt
python -m pytest pipeline/tests -q

# 全期間、全reporter/partner。COMTRADE_API_KEYを環境から利用。資料取得はしない。
python -m pipeline.manganese

# 明示的な限定サンプル。2024年、豪州・ブラジル・中国・ガボン・インド・オランダ・南ア・米国のX/M
python -m pipeline.manganese --sample --output .cache/manganese-sample

# 取得済みRawから再現。通信・秘密情報不要。
python -m pipeline.manganese --replay data/review/manganese-sample/bundle.json --output .cache/manganese-replay

# 企業/政府のdocumentのみを取得。indexは取得しない。未レビュー資料として保存。
python -m pipeline.manganese_disclosures --output .cache/manganese-discover

# コミット対象の原本からUSGS2026/2024を未レビュー参考値として抽出・比較可能性を診断。
python -m pipeline.manganese_reference --output .cache/manganese-reference
```

サンプル再現はデータの正規化・Raw検証が成功しても、元の5取得失敗を引き継ぐため**終了コード1**。
`status: diagnosed` と `failed_queries` を併せて確認する。取得失敗を再現時に成功へ書き換えない。
未完全集合は世界貿易として扱わず `queries_complete: false`、`global_completeness: unverified`。
フル監査は8年×1HS×2flowの16独立クエリ。キーがない場合はネットワークを呼ばず16件を失敗記録する。
500行上限、count不一致、重複、想定外次元、無効数値などを既存strict normalizerで拒否する。
取得・正規化の失敗はクエリごとに記録して続行し、空応答をゼロ貿易に変換しない。

出力先は `.cache` または `data/review` のサブディレクトリに制限する。
Rawは本文とURL/queryに由来する内容アドレス名、本文SHA256、sidecarを保存する。
再現時は成功・失敗の双方のRawを検証し、正規化結果がbundleと一致することも確認する。
出力先に異なるRawが既にあれば上書きせずエラー。検証失敗時はstatusをfailed/非公開にする。

## 診断と人間のレビュー

`diagnostics.json` は自己申告の計測フラグとミラーの網羅性フラグを別々に出す。
ミラー量は重量がある輸入報告の**観測部分合計**。欠損行数・観測reporter・未観測仕向国を併記する。
ミラーに相手国がないことだけで自己申告を誤りと判定しない。差率は記録するが25%を適用しない。
数量が等しく計測/網羅性の争点が見つからない場合のみ `no_dispute` とするが、正確性の認証ではない。

`manganese_anchor.py` は `missing / no_dispute / hub / domestic_consumption / incomparable / indeterminate`
を区別する。生産/販売量から輸出を選ばず、0.5–1.5倍帯は未適用。
国の構造は `manganese_policy.json` の一次資料に基づく**調査コンテキスト**として明示する。
中国・インドの国内需要は輸出/生産一致を仮定しない理由になるが、自己申告の誤りの証拠ではない。
オランダのマンガン固有のハブ機能、ガボンの単一産地性などは未確定。
比率や国の立地だけでハブ/輸出単一鉱山型に分類しない。ハブ分岐の実装はテスト済みだが実例未検証。

`manganese_reference.py` はアーカイブ検証後、USGS2026の2024年列だけを抽出する。
千含有Mnトンを含有Mnトンへ換算し、e/W/NA/ゼロ、世界計とOtherを分ける。
抽出値は `unreviewed_machine_extraction`。診断にのみ使い、レビュー済みCSVへ書き込まない。
他のUSGS版の自動表抽出は未対応。企業値の自動抽出・四半期合計による年値生成も行わない。

採用には以下の3入力が必要。現在はいずれも空であり、今回の調査を人間のレビューと偽っていない。

1. `pipeline/manganese_reviewed_sources.json`: `kind: document`、`source_url`、`reviewer`、
   `review_date`、`review_status: human_reviewed` と `raw` を人間が登録。
   `raw` はdiscoverのメタデータ全体をコピーし、**pathとsha256の両方**を必ずピン留めする。
   参照Rawは既定 `data/review/manganese-evidence/` からの相対パス。
   出典一覧が未レビュー、index、未ピン留め、またはRaw/sidecarが改変されていれば拒否する。
2. `data/manual/manganese-disclosures.csv`: 基本9項目に `weight_basis,product_scope,period_start,period_end,coverage_scope`
   を追加。measureはproduction/salesのみ。必須空欄、重複、不正数値、範囲外年、四半期を拒否する。
   sourceの `measurements` 配列に、CSVの `review_date` を除く全フィールドを型付きJSONで登録する
   （yearは整数、value_tは数値）。これにより年次資料内の四半期セルを年度値と誤記した入力も、
   人間が確認した年次セルの意味と一致しなければ通らない。会計年度は明示して保持し、暦年とは比較しない。
3. `pipeline/manganese_reviews.json`: 国/年/HS別の人間の採用判断を別管理。
   `decision` はreported/mirror/external/exclude、`selected_weight_t` は採用値または除外のnull。
   reason/reviewer/review_date/review_status/source_url/locator/evidence_sha256/evidence_path/
   weight_basis/product_scopeを必須とする。一次資料の `trade_decisions` にはcountry/year/hs_code/locator/
   weight_basis/product_scopeと `measure: exports, coverage_scope: national, value_t` の年次輸出根拠を登録する。
   生産/販売の文脈だけでは輸出採用を許可しない。mirrorは国別allowlistにも入っている必要がある。
   reported/mirror判断は実際の観測値との一致を検証する。採用後も公開許可にはならない。

人間による署名の暗号検証はしていない。レビュー用ファイルの編集権限とPRレビューが人間判断の信頼境界。
公開ゲートの解除は本実装の機能として提供せず、別途完全性と統計設計のレビューを必要とする。

## Actionsと保管

`manganese-audit.yml` と `manganese-disclosures.yml` はそれぞれ `workflow_dispatch` のみ、
`contents: read`、checkoutの資格情報永続化なし。前者はComtradeキーを取得ステップだけに渡す。
後者にはSecretsを渡さず、企業/USGS資料を取得し、個別失敗後も残りを処理する。
どちらも常時artifact保存し、90日で期限が来るため、継続的に利用するRawはレビュー領域へ保管する。
今回のRawと診断は `data/review/manganese-*` に保存済み。外部へのpush/マージ/公開は未実施。

実行件数、代表例、レビュー優先事項は [結果報告](manganese-audit-2026-09-14.md) を参照。
