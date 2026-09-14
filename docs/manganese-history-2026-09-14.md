# マンガン過去データの追加検証（2026-09-14）

信頼できる公的資料を実際に取得し、2017–2024年の診断材料を増やした。
個々の輸出値の正確性が確定したという意味ではなく、欠落の縮小、原本追跡、版間差の検出を改善した。
採用値は0件。人間レビューCSV・採用決定・公開ゲートは変更していない。

## 実データと結果

| データ | 結果 |
|---|---|
| UN Comtrade | 16報告国 × 8年 × 輸出入、256照会。最終191成功・65空応答。2,642行、518輸出国年。 |
| BGS World Mineral Production | 2017–2021版と2020–2024版の鉱石生産統計を取得。310年次観測、34か国・254国年。重複56国年のうち25件で数値が異なる。 |
| USGS MCS | 今回2019–2024版を追加取得。既取得の2025・2026版と併せて原本参照可能。新たな過去版の数値はまだ自動抽出・採用していない。 |
| USGS Minerals Yearbook 2019 | 原本取得。米国貿易表の総重量・Mn含有量・品目別行・輸入制度の違いを確認。採用値にはしていない。 |

貿易診断は `missing: 438`、`indeterminate: 76`、`observed_difference_threshold_deferred: 4`。
レビュー済み生産アンカーはないため、アンカー診断は `missing: 510`、`domestic_consumption: 8`。
BGSの機械抽出候補をレビュー済みアンカーへ自動接続していない。ハブ等の国別判断も比率から推定しない。

最初の履歴取得では2,572行・185成功だった。ガボン2017–2019年の6照会がH3分類で保留されたため、
[WCO HS2007 Chapter 26](https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-older-edition/2007/hs-2007/0526_2007e.pdf) p.1で260200の定義を確認。
H4/H5/H6と対象定義が一致することを根拠にH3を正規化対象に追加し、通信せず原本から70行を追加した。
元の失敗記録は保存し、新スナップショットには `previous_failure` と同一Raw参照を残した。
これは入力の正規化であり、値の信頼性に関する人間レビューや採用判断ではない。

2024年のミラー観測合計は、南アフリカで16,054,487.19tから17,212,884.76t、
豪州で2,145,280.45tから2,386,016.16t、ガボンで4,454,512.67tから4,813,807.66tへ増えた。
報告国追加による観測範囲の拡大であり、輸出世界総額・総重量の確定ではない。
南アフリカの自国申告24,716,301.86tは訂正していない。相手国の欠落だけでは誤申告と判定しない。

## 比較可能性・未解決事項

- Comtradeは[公開preview API](https://uncomtrade.org/docs/what-is-data-preview/)を利用。16報告国は取得範囲であり `mirror_allowlist` ではない。世界網羅率は不明。上限到達はstrict normalizerで拒否する。
- 65件の空応答はゼロ貿易ではない。豪州の輸出等が欠けている。APIキーを使う全世界監査は未実行。
- BGSは[2017–2021版](https://nora.nerc.ac.uk/id/eprint/534316/1/WMP_2017_2021_FINAL.pdf)と[2020–2024版](https://nora.nerc.ac.uk/id/eprint/541620/1/WMP_2020%20to%202024.pdf)の各印刷p.46。metric tonnesの鉱石量で、USGSのMn含有量とは別系列。乾湿・品位の換算はしていない。
- BGSでは35観測が会計年度等で追加確認を要する。インド2024欄は2025年3月31日終了年度。イランは翌年3月20日終了で、開始日は推測せず空欄。Marketable等の脚注も保持。その他は暦年として候補化したが、定義・全国範囲・産業構造の人間レビュー前には比較アンカーに使わない。
- BGSの記号表では「—」はnil、「0」は表示単位の半分未満、「*」は推計。nil16観測は0として記号を保持し、欠損と区別した。推計値も確定値に見せない。
- BGS豪州2020年は旧版4,752,200t、新版6,425,848t。改訂なのか集計範囲等の違いなのか、理由の確認は未完了。最新版を無条件採用したり、複数版を黙って接続しない。
- [USGS Yearbook 2019](https://pubs.usgs.gov/myb/vol1/2019/myb1-2019-manganese.pdf)表5の米国2019年鉱石・精鉱輸出は1,010t（丸め値）、Comtradeは1,075.529t。差を検出したが、改訂・品目範囲等の確認前に訂正しない。表6の輸入434,000tは「imports for consumption」であり、Comtrade輸入434,010.681tとの近さだけでは同一定義と認定しない。両者とも米国Censusを基礎とし、統計的に独立した証拠とは数えない。
- ブラジルMDIC APIは403応答で取得できず。公式の年次一括CSVによる独立照合も未実施。
- USGS2019の初回URLは失敗。その記録を残し、公式索引が案内する旧形式URLから別の取得履歴として成功。途中の承認サービス利用上限による拒否は、サービス復帰後の承認付き再試行で解消。安全設定は変更していない。

## 再現方法

```sh
# 再開可能な公開API取得。既存の成功・失敗Rawを再利用する。
python -m pipeline.manganese_history --output .cache/manganese-history --seed data/review/manganese-history/bundle.json

# 分類調査後の失敗Raw再検証。元スナップショットを保護するため別出力を使用。
python -m pipeline.manganese_history --output .cache/manganese-history-validated --seed data/review/manganese-history/bundle.json --revalidate-failed

# 通信不要の最終貿易診断。空応答65件を含むため終了コード1が正常な保留結果。
python -m pipeline.manganese --replay data/review/manganese-history-validated/bundle.json --output .cache/manganese-history-replay

# BGS原本のハッシュ・パス・sidecarを検証して機械抽出。
python -m pipeline.manganese_bgs --output .cache/manganese-bgs-history

# 資料だけの取得。COMTRADE_API_KEY不要。index取得・自動採用なし。
python -m pipeline.manganese_disclosures --manifest pipeline/manganese_history_sources.json --output .cache/manganese-history-documents
python -m pipeline.manganese_disclosures --manifest pipeline/manganese_additional_sources.json --output .cache/manganese-additional-documents
```

最終データは `data/review/manganese-history-validated/`、元の履歴は `manganese-history/`。
BGS候補・版間差は `data/review/manganese-bgs-history/`。
追加PDFの `sha256` と `path` は各 `*-evidence/discover.json` にあり、すべて未レビュー。
人間が出典と測定定義を確認して既存のレビュー手順で両方をピン留めするまで、採用不可。

テストは既存期待値を変更せず追加。原本再現、キャッシュ照会次元の改変拒否、H3再検証の履歴保持、
BGSの版間差・年度境界・単位/脚注/列変更の拒否、未レビュー採用防止を確認。
全189件が成功（60.67秒）。その後のBGS nil記号の処理変更についても履歴テスト15件が成功（5.96秒）。
Windowsのsandboxではpytest一時ディレクトリの権限エラーがあり、承認付き通常実行で全件検証した。
既存の公開HTML変更は保持し、この追加処理から公開データを書き換えていない。
