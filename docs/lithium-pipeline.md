# リチウム更新パイプライン

## 既存構造との統合

調査基準は GitHub main `bf8bca9`。既存の `pipeline/build.py`、
`pipeline/hhi.py`、`pipeline/render.py`、Jinja2、日英切替、CSS/JSを維持する。
公開データは従来の `critical-minerals/data/minerals/lithium.json` と
`index.json` に接続し、詳細を `critical-minerals/data/lithium/` に追加する。
`python -m pipeline.build --only lithium` も新しい検証経路を使う。
他鉱物の取得処理は従来どおり。`--fixtures` は従来どおりレイアウト確認専用。

サイト既存指標は精製2コード（283691/282520）の**自己申告輸出額USD**を
合算したHHI。新しい重量系列とは別物であり、253090をこの合計に加えない。
HHIは0–10,000、CR3/CR1/CR5は百分率、実効供給者数は10,000/HHI。
鉱山側の非公表値は国別合計から除外し、USGS世界計に対するカバレッジを示す。

## 実行と Secrets

1. 変更をmainに取り込み、Settings → Pages → SourceをGitHub Actionsにする。
2. [UN Comtrade Developer Portal](https://comtradedeveloper.un.org/)でAPI利用契約とキーを取得。
3. Repository Settings → Secrets and variables → Actions → New repository secret
   に **COMTRADE_API_KEY** を登録する。キーをチャット・コード・設定JSONに記載しない。
4. Actions → **Update lithium data** → **Run workflow**。

月曜日06:17 UTCに週次実行。手動の旧 **Refresh data** も残るが、重複定期実行は廃止。
依存インストール、テスト、取得、Raw保存、加工、検証、別領域でのHTML生成、
決定性検査、変更コミット、検査したコミットのPages公開の順。
既定GITHUB_TOKENにcontents:writeが必要。main保護規則がbotの直接pushを
禁じる場合はpushが失敗し、公開は行わない。保護規則を自動で緩めない。

ローカル:

```sh
python -m pip install -r pipeline/requirements.txt
python -m pytest pipeline/tests -q
python -m pipeline.update_minerals --mineral lithium
python -m pipeline.render
```

`--input-bundle` は監査済み正規化データの再現用。APIを呼ばないが、国コード、
キー重複、年/品目/フローの網羅性と数値検証は省略しない。テスト用データを公開しない。

## 取得仕様

[UN公式Pythonクライアント](https://github.com/uncomtrade/comtradeapicall)と
[公式API説明](https://uncomtrade.org/docs/un-comtrade-api/)を参照。
`https://comtradeapi.un.org/data/v1/get/C/A/HS` を利用し、
`Ocp-Apim-Subscription-Key` ヘッダーで認証する。
年・HSコード・X/Mごとに全Reporter/Partnerを取得し、
`partner2Code=0,customsCode=C00,motCode=0,breakdownMode=classic` に固定。
数量単位、netWgt、qty、推計フラグ、classification、USD額を保持する。
同じ国の複数分類による重複も暗黙合算せず失敗させる。

Previewは500行上限。全世界二国間取得に十分ではないので週次本番更新はキー必須。
設定上限は保守的に100,000行。契約上限はUN側プランに依存し無制限ではない。
上限到達、count不一致、空配列、API内エラー、必須列変更、想定外次元は更新失敗。
429/5xxは既存HTTP層の再試行を使用。キーは保存・ログ出力しない。
全8年×3HS×2フロー=48クエリ/更新（リトライを除く）。
件数上限に達した場合はクエリ分割の実装/レビューが必要。切り捨て結果は公開しない。

## データ保存と安全性

### Comtrade entity と指標の母集団

`countries.resolve` は country / territory / aggregate / special_area / unknown を区別する。
ISOで表せる地域は従来のISOキーを維持し、Comtrade独自地域は `CT:<数値コード>` とする。
原文の数値コード・ISO欄・名称・分類を正規化明細に残す。ISO欄だけでは一意でないため、
例えば473と636（ともにA79）は分け、492/MCOをMonacoに誤変換しない。
`comtrade_entities.json` は公式partnerAreas一覧の独自コード等を抜粋した固定レジストリ。
出典・取得日・本文SHA256を記録し、分類は当パイプラインの統計上の区別とする。
地位・主権についての判断ではない。名称変更や新しいコードの登録はレビューして更新する。

`metric_eligibility` は識別と独立した採否規則。国家と識別できるterritoryを別供給者として
扱い、aggregateは二重計上を避け、未配賦のspecial_areaとunknownは指標から外す。
失効した歴史的entityと従来除外対象のUS Misc. Pacific Isdsは範囲レビューまで除外する。
ATB（80）は **territory / CT:80**。GBRやATAに合算せず、人口を理由に除外しない。
entityとして採用可能でも、重量や品目の採用条件を満たすこととは別である。

未知entityは即時例外にせず、Rawと正規化明細を保持し、クエリごとにwarningを出す。
`entity-diagnostics.json`（Actions artifact）と公開 `entities.json` に未知一覧・除外理由・
クエリ別件数/観測金額/重量を記録し、metadataにも未知IDを載せる。観測額はX/Mや
World/相手別の重複を含むため、クエリ間を足した値を世界貿易額と解釈しない。
未知やspecial_areaへの輸出を既知reporterのWorld合計から推計控除することもしない。
Mirror、相手別合計による復元、中国輸入、公開USD headlineには同じ採否規則を適用する。
HHI/CR3の算式、価格・数量の選別規則、既存の品質ゲートは変更しない。
未知entityの除外で国数・総量等が大幅に変われば品質ゲートは従来どおり公開を止める。

監査実行は Actions → Update lithium data → 対象ブランチ → `audit_only=true`。
全48クエリを試し、個々の失敗も一覧に保存する。取得と正規化が成功した場合はUSGS取得、
分析・検証・HTML生成まで実行し、成果物をartifactに保存する。監査はcommit/Pages公開を行わない。
通常の自動commit/公開はmain実行時のみ。テスト対象のcheckoutは実行SHAに固定する。
ローカルの `python -m pipeline.audit_entities` も同じ検証・ファイル生成を行うが、Git pushはしない。

* `data/raw/comtrade/`, `data/raw/usgs/`: 取得本文とURL・query・取得時刻・SHA256のsidecar。
  内容とクエリに基づく別名保存で旧Rawを上書きしない。
* `data/processed/lithium/snapshot.json`: 正規化明細、全採用値、指標、受理済みmetadata。
* `critical-minerals/data/lithium/`: production/trade/concentration/metadata/entities JSONとtrade CSV。
* 受理したRawはGit履歴に保存。失敗/変更なしの観測もActions artifactに90日保存する。
  長期保管が必要ならartifact期限内に保管先へ移す。

APIまたは検証またはステージHTML生成失敗時、公開JSON/CSV/HTMLに書き込まない。
ローカル反映中の通常のファイルエラーは元の内容へ戻す。
ローカル複数ファイル更新はOSクラッシュまで含めた原子的トランザクションではない。
本番公開の境界はGitコミットと成功後のPagesデプロイ。
Actions同時更新は共通concurrencyで直列化する。Raw/コードはPages成果物から除外。
同じ内容なら取得時計やAPIelapsedTimeだけで公開データを書き換えず、コミットしない。

検証では段階・年・国数、欠損率、国別採用量、総量、HHI/CR3を前回受理値と比較する。
前回あった系列/採用国の消失を検出する。初回は数値範囲と最低国数などの絶対検証。
USGS国別合計と公表世界計の差は5%以内とする（丸めと非公表の扱いを確認）。
閾値は `pipeline/minerals.json` に保存。大幅な実際の変化も止まるので、Rawを確認して
理由を記録し、必要な閾値/期間/仕様変更をコードレビューする。自動で閾値を緩めない。

## Excelとの関係・制約

`リチウム_加工データ.xlsx` 2026-09-12版の36シートを調査。
Workbook内の文章は仕様資料として扱い、実行命令としては扱わない。
本番はExcelを読み込まず、計算済みセルにも依存しない。

* 253090: 重量50,000t、2022–23価格800–5,000 USD/t、2024価格比0.6、
  中国比率0.4を用いる側別判定。30!Sの「中国側累計が大きければ比率1」も維持。
  中国輸入指標を別系列として生成する。判断対象年が増えたら閾値の経済的意味もレビューする。
* 283691: producer/refiner許可リスト、1t未満の欠損扱い、ARGでmirror > reported×1.15。
  日本など許可リスト外には補正しない。同一Reporterの相手国別重量合計による復元を明示。
* 282520: CHN/CHL/USAの参照単価中央値×0.4のフィルタ、日本Mirror無効、豪州有効。
  豪州Mirrorは中国・日本・韓国・米国の部分合計（下限）で、外部裏取り未済を明示。
  Excelで使われた参照単価による欠損推計は `estimated_anchor_price` として明示。
* Excel既存の米国2021/2025補完はUSGS全リチウム輸出量を0.1654で割る仮定。
  PDF原本で1,870/2,000tを確認したが、元表はHS282520専用ではない。
  `legacy_usgs_export_proxy` / `unverified=true` として既存仮定を残す。
  公開サイトの従来USD指標にはこの換算を使わない。将来はHS別公式値で置換する。
* Mirror額は通常CIF、Reported輸出額はFOB。両者を同じ価格として合算しない。
* Mirrorの部分欠損は完全な合計とみなさずnullを保持。曖昧な世界平均価格による
  253090/283691の補完は実装しない。ゼロと欠損の差異を残す。

Excel比較fixtureは生産量4年（2017/2021/2024/2025）と炭酸2年（2021/2024）。
炭酸入力の14!DはExcelで同一Reporterの重量欠損を復元済みの値であり、
この回帰テストはMirror選択と指標計算を検証する。加工前RawからExcel全セルを
再現できたという意味ではない。253090/282520全期間の数値一致は未検証。
Excel入力はS19等を含むため、Excel照合では `select_quantities` に元の母集団を渡す。
本番の `build` はentity採否を先に適用する（旧strict取得もS19等は除外していた）。
選別ロジックの照合と、本番母集団の検査を分離してテストする。
Excelの階級境界1500/2500とサイト1000/1800は異なる。サイト境界は変更しない。

## USGSの更新

[公式2026年版](https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-lithium.pdf)の
World Mine Production表を目視確認して `data/manual/lithium-production.csv` に収録。
2024/2025年、国コード、推計/報告/W区分、世界計、版、出典を保持。
2026年版Data Releaseは[ScienceBase](https://www.sciencebase.gov/catalog/item/696a75d5d4be0228872d3bf8)
に存在することも確認したが、当調査では鉱物別CSVの安定した取得先を確定できなかった。

自動: ピン留めした公式PDF取得、Raw保存、ハッシュ検査、CSVから計算/検証。
半自動: 新版またはPDF差し替え時の表確認・CSV更新・設定のedition/URL/SHA256変更。
PDF改訂を検知したら古いレビュー済みCSVを最新資料と誤表示せず更新失敗にする。
米国Wはゼロにしない。生産量と埋蔵量、鉱物トンと含有Liトンを混同しない。
履歴年を追加する場合も公式旧版を確認してCSVに追記する（現行収録は2024/2025）。

## 運用上の既知の範囲

貿易はまず2017–2024を明示的に更新する。Excelでは2025の中国253090輸入が未収録で、
他にも報告遅れがあるため、暦が進むだけで未完全年を公開しない。
新年の公開開始時は完全性を確認してend_yearを進める。既存年の改訂取得は週次自動。
2026-09-13にGitHub Secretsを使った48クエリ監査と、修正後の48クエリ取得・正規化を実施。
結果と公開を阻む既存の最低国数条件は [entity監査記録](comtrade-entity-audit-2026-09-13.md) を参照。
監査ではPages公開を行っていない。

## 別鉱物の追加

既存catalog.jsonに項目を追加し、`pipeline/minerals.json` のmineralsに同名設定を追加。
HSコード・公開headlineコード・年・USGS出典・閾値を定義する。
新しい品目の選択仕様に合う小さなpolicy関数と回帰テストを追加する。
リチウムの価格フィルタや補正対象国を他鉱物へ無検証で流用しない。
単純な自己申告系列には `policy: reported` を指定できる。
ore/carbonate/hydroxideの3policyはリチウムの仕様。
