# Task F: Petralysis リブランドと白基調スクリーナー型UIへの改装

2026-09-14。指示書「Task F 実装指示書」にもとづく実装記録。決定事項と検証手順を残す。
本タスクはプレゼンテーション層のみを対象とし、パイプラインの計算ロジック・検証ゲート・
公開判定・公開済み指標JSONの数値には触れていない。

## 1. リネーム(F-1)

- Orelysis は既存企業と名称が衝突したため使用不可となり、サイト名を **Petralysis** に変更した。
- 置換範囲: テンプレート、`<title>` / OGP / `twitter:*`、フッター、README、LICENSE の権利者表記、
  ワークフローのコミット者名(`Petralysis pipeline`)、JS のローカルストレージキー
  (`petralysis:lang`)、SVG パターン ID。
- 意図的に残したもの: パイプライン内部のロガー名(`orelysis.*`)、環境変数名
  (`ORELYSIS_UA` / `ORELYSIS_CACHE_DIR`)、User-Agent 文字列。いずれも公開HTMLに現れず、
  変更するとワークフロー設定との整合を別途確認する必要があるため、本タスクの射程外とした。
  docs/ 配下の過去の作業記録も歴史として書き換えていない。
- `site.json` に `site_url`(`https://latrans2004.github.io/petralysis/`)を追加し、
  `<link rel="canonical">`、`og:url`、`og:image` を絶対URLで出力する。`repo_url` と
  `site_base` は `petralysis` に更新済み。相対パスは維持しているため、GitHub 上のリポジトリ名
  変更の前後どちらでも配信は壊れない。
- 完了判定: `grep -rl Orelysis --include=*.html .` が 0 件(`pipeline/tests/test_screener.py`
  でも `index.html` に旧名が残らないことを確認する)。

## 2. ブランド資産(F-2)

- 単一のマスター `assets/brand/petralysis-master.png` から `tools/make_brand_assets.py` が
  全派生物を生成する: `favicon.ico`(16/32/48)、`icon-192.png`、`icon-512.png`、
  `apple-touch-icon.png`(180)、`brand-32.png` / `brand-64.png`(ヘッダー用、`srcset` 2x)、
  `ogp.png`(1200×630、ワードマーク付き)。
- アイコン系はマスターの四隅から実測した地色(アリスブルー `#F0F8FF`)をそのまま保持し、
  クリスタル本体が中央 80% のセーフゾーンに収まるよう配置する(maskable 対応)。
- **コミット済みのマスターは `--synthesize` で生成した仮画像**である。セッションにオーナーの
  PNG が提供されていなかったため、指示書の記述(ファセット状、シルバー〜黒、細い薄アウトライン、
  アリスブルー背景)に沿った代替を置いた。本物の PNG を同じパスに上書きして
  `python tools/make_brand_assets.py` を実行すれば、全派生物が差し替わる。
- 旧 `mark-320.png` / `mark-640.png` / `mark.png` と `favicon-16/32.png` は参照ごと削除した。

## 3. デザイントークン(F-3)

| トークン | 値 | 用途 |
|---|---|---|
| `--bg` | `#FFFFFF` | ページ背景 |
| `--bg-panel` | `#F6F8FA` | パネル・ゼブラ行・コードブロック |
| `--text` | `#14181D` | 本文 |
| `--text-2nd` | `#57606A` | 補足・ラベル |
| `--text-3rd` | `#6E7781` | さらに弱い補足(AA を満たす下限) |
| `--hairline` / `--hairline-soft` | `#D8DEE4` / `#E6EAEE` | 罫線 |
| `--link` / `--data` | `#0F62B7` | リンク・チャート系列色(鋼青) |
| `--brand-tint` | `#F0F8FF` | アイコンバッジ地。ページ全面には使わない |
| 非集中 | 文字 `#1A7F37` / 地 `#E6F4EA` | HHI < 1,000 |
| 中程度 | 文字 `#9A6700` / 地 `#FFF3D6` | 1,000–1,800 |
| 高集中 | 文字 `#B42318` / 地 `#FCEBE9` | > 1,800 |

- 色が意味を持つのはバンドバッジと provisional / 確認中の注記のみ。グラデーション・影・装飾は使わない。
- 書体はシステムサンセリフ。表 13px、本文 15px、クオートヘッダー主数値 28–32px、11px 未満は不使用。
  数値セルは `tabular-nums` + 右揃え。
- `meta color-scheme=light`、`theme-color=#FFFFFF`。`charts.js` の配色も同じトークンに合わせた。
- `.hero` の `padding` ショートハンドが `.wrap` の左右余白を打ち消していた既知バグは、
  ヒーロー廃止に伴い該当 CSS ごと削除した。

## 4. 情報設計(F-4)

### トップページ `index.html`

上から、ページヘッド(サイト名・一行説明・鉱物数・最終リビルド日時)、スクリーナー、
バンド凡例(3行)+ Methodology リンク、Task G 用の空スロット(`.cta-slot`、機能なし)、フッター。
ヒーロー画像・問いかけ型キャッチ・カードグリッド・HHI ナラティブは廃止。

### スクリーナー(`pipeline/templates/_screener.html`、`assets/js/screener.js`)

| 列 | 内容 |
|---|---|
| Mineral | 名前(リンク)+ 元素記号・カテゴリ(11px muted) |
| Mine HHI | `index.json` の鉱山側 headline |
| Top supplier | 最大生産国 + シェア |
| Export HHI | 下記ルール |
| Band | 鉱山 HHI 基準のバッジ |
| Year | 鉱山側の最新年(鉱山がなければ輸出側) |

Export HHI 列の決定順序(`render.export_cell`):

1. 鉱物 JSON の `trade.publication_status == "under_review"`(または `publishable: false`)なら
   **常に「Under review / 確認中」**。summary に数値があっても数値を出さない。天然黒鉛はこの経路。
   `test_a_withheld_trade_block_wins_even_when_a_summary_figure_exists` が守る。
2. 段階タブを持つ鉱物で `catalog.json` の `headline_trade_stage` が指す段階があれば、
   その段階の自己申告側の**最新確定年**(provisional でない最後の年)の値を表示し、
   段階名と年をサブ行に添える。リチウムは `283691`(炭酸リチウム)を指定 → 2024 年値。
   2025 年は provisional のため headline には使わない。
3. 段階が複数あり `headline_trade_stage` 未指定なら「N stages」リンクで個別ページへ誘導。
4. それ以外で summary に貿易 headline があればその値。
5. なければ「Pending / 準備中」。

`headline_trade_stage` の値はオーナー確認推奨事項(指示書 §11)。候補として最も構造が
クリーンな 283691 を設定したが、1 フィールドの変更で差し替えられる。

機能: 検索(名前 EN/JA・元素記号、部分一致)、カテゴリフィルタ(`catalog.json` の
`categories` と各鉱物の `category` で管理)、列ヘッダークリックでの昇降順ソート
(`aria-sort` 付与、空値は常に末尾)。全てクライアントサイド vanilla JS。
**JS 無効時**はコントロールが `hidden` のまま、カタログ順の静的テーブルがそのまま読める。

### `critical-minerals/index.html`

既存 URL を維持。同じスクリーナーを "Battery metals" に固定絞り込みしたビュー。
"Two indices, not one" は 1 段落に圧縮し、本文は Methodology(`#two-indices`)へ移した。

### 鉱物個別ページ(クオートヘッダー)

1. クオートカード: 名前 + 元素記号 + カテゴリ・役割 / 要約 1 文(`render.first_sentence`、
   表示のみ)/ 主数値 = 鉱山 HHI(最新年)+ バンドバッジ + 変化量注記(既存 `trend` を踏襲)/
   統計グリッド(Top producer / Top three / Effective suppliers / Export HHI / Updated)。
2. ヘッダー直下の注記: カバレッジ(< 100%)、貿易「確認中」、段階の provisional 年。
3. Mine concentration パネル(統計グリッドはヘッダーと重複するため省略)、Export concentration
   パネル(統計グリッド維持)、段階タブ(Task A の構造・データは不変、白基調に再スタイル)、
   国別シェア表(bars + table view、tabular-nums 右揃え)、出典リンク、注意事項、ビルドノート。

変化量注記の比較起点は、`hhi.trend` が算出する鉱物ごとの直近 5 年窓をそのまま使う
(全鉱物での統一は行わない。指示書 §11 の確認事項)。

### `catalog.json` への追加(表示用メタデータのみ)

- 最上位 `categories`: `{ "battery-metals": { "label", "label_ja" } }`
- 各鉱物 `category: "battery-metals"`
- リチウム `headline_trade_stage: "283691"`
- `symbol` は既存。`build.py` の `pack()` はカタログから特定フィールドしか写さないため、
  公開 JSON(`minerals/*.json`、`index.json`)は変化しない(graphite 再現チェックで確認)。

### i18n

新規 UI 文字列は `pipeline/i18n.py` の `STRINGS_JA`(`screener.*`、`col.*`、`legend.*`、
`quote.*`、`stage.provisional_short`)に追加し、数値を含む文は `data-i18n-text`、
About / Methodology の改稿部分は `data-lang-only` 並列ブロックで対応した。検索ボックスの
placeholder は `screener.js` が `i18n:change` で差し替える。翻訳欠落時に英語が残る
フェイルセーフは維持。**About / Methodology の日本語改稿はオーナー推敲前提。**

## 5. 不変条件の確認

- 公開 JSON・パイプライン・検証ゲートは無変更。`python -m pipeline.publish_graphite` 後の
  `git diff -- critical-minerals/data data/processed/natural-graphite` は空。
- 天然黒鉛の貿易 HHI は数値としてどこにも出力しない(スクリーナー、クオートヘッダー、
  Export パネルのいずれも「確認中」)。
- 外部ライブラリの新規導入なし。

## 6. 検証手順

```bash
pip install -r pipeline/requirements.txt
python -m pytest pipeline/tests -q                 # 264 passed
python -m pipeline.render && git diff --quiet -- '*.html'   # stale チェック
python -m pipeline.publish_graphite && git diff --exit-code -- critical-minerals/data data/processed/natural-graphite
grep -rl Orelysis --include=*.html .               # 0 件
```

Playwright(Chromium)での確認項目。`site_base` が `/petralysis/` のため、
リポジトリを `<root>/petralysis` として配信して実行する。

- EN ⇄ 日本語の往復(列ヘッダー、Pending / Under review、段階名、件数表示、placeholder、バッジ)
- ページ遷移後の言語保持(トップ → リチウム)
- 日本語ブラウザ(`locale=ja-JP`)の初期表示が日本語
- 検索・カテゴリフィルタ・ソート(`aria-sort` が 1 列のみ active、空値が末尾)
- JS 無効: 8 行の静的テーブルが読め、コントロールは非表示
- スマホ幅(390px): 言語トグルがブランド行、ナビが 2 行目、横スクロールなし
- 404: `site_base` 起点のリンク、日本語切替
- 全ページで JS エラーなし

## 7. オーナー側の残作業

1. `assets/brand/petralysis-master.png` を本物のマスター PNG で上書きし、
   `python tools/make_brand_assets.py` を実行してコミットする。
2. GitHub 上でリポジトリ名を `petralysis` に変更し、`latrans2004.github.io/petralysis/` の配信と
   旧 URL のリダイレクトを確認する(コード側は変更不要)。
3. リポジトリの Description / About 欄を更新する。
4. `headline_trade_stage`(リチウム = 283691)の妥当性を確認する。
5. About / Methodology の日本語改稿部分を推敲する。
