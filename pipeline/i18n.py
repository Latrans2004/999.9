"""Japanese strings and language-aware phrase builders for the UI chrome.

Page-specific prose (About, Methodology, per-mineral summaries and caveats)
is translated inline instead of living here: in the templates via
``data-i18n-text`` attributes and ``data-lang-only`` blocks, and in
``critical-minerals/data/catalog.json`` as the ``*_ja`` sibling of each
English field. This module only holds strings that repeat across pages
(navigation, table headers, chart vocabulary) and the handful of functions
that format a number into a full sentence in each language, mirroring
``render.py``'s ``trend_phrase`` / ``human_time`` for English.

Country and reporter names, and organisation names such as "USGS" or "UN
Comtrade", are deliberately not translated anywhere in this file: they are
treated as proper nouns, kept as the data reports them regardless of the
active language, the same way an English-language source would keep them.

See ``assets/js/i18n.js`` for how the client-side swap happens, and the
"Language toggle" section of README.md for the conventions future edits
should follow.
"""

from __future__ import annotations

import datetime as dt

# Shared UI chrome. Keyed exactly as templates reference them via
# data-i18n="<key>". The English side is never read from here — it is
# already the default DOM content the templates render — so only Japanese
# needs to be maintained in this dictionary.
STRINGS_JA: dict[str, str] = {
    "nav.critical_minerals": "重要鉱物",
    "nav.methodology": "算出方法",
    "nav.about": "このサイトについて",
    "skip.content": "本文へスキップ",
    "banner.title": "サンプルデータ。",
    "banner.body": (
        "このビルドは合成データ(フィクスチャ)から生成されたものであり、"
        "USGSやUN Comtradeの実データではありません。このページの数値は"
        "いずれも実測値ではありません。"
    ),
    "footer.tagline": (
        "公開データによる供給集中度の測定。手作業ではなくスケジュール実行で"
        "更新される個人プロジェクトです。"
    ),
    "footer.sections": "セクション",
    "footer.sources": "データソース",
    "footer.source": "ソース",
    "footer.repo": "GitHubのリポジトリ",
    "footer.build_history": "ビルド履歴",
    "footer.disclaimer": (
        "USGS・国連のいずれも、本サイトおよびその算出結果を承認・保証する"
        "ものではありません。"
    ),
    "footer.awaiting": "初回のデータビルド待ち",
    "band.unconcentrated": "非集中",
    "band.moderate": "中程度の集中",
    "band.high": "高度に集中",
    "panel.mine_title": "鉱山側の集中度",
    "panel.export_title": "輸出側の集中度",
    "table.toggle": "表で見る",
    "table.year": "年",
    "table.top_three": "上位3カ国",
    "table.reporting": "報告国数",
    "table.country": "国",
    "table.share": "シェア",
    "table.cumulative": "累積",
    "stat.single_year": "単年データのみ",
    "stat.largest_supplier": "最大供給国",
    "stat.top_three": "上位3カ国合計",
    "stat.effective_suppliers": "実効供給者数",
    "figure.awaiting_build": "初回ビルド待ち",
    "figure.no_source_data": "ソースデータなし",
    "figure.page_ready_pending": "ページ準備済み・データ待ち",
    "figure.concentration": "集中度",
    "chart.no_data_yet": "データはまだありません",
    "chart.index_over_time": "指数の推移",
    "notfound.title": "ページが見つかりません",
    "notfound.body": (
        "このページは存在しないか、パイプラインの直近のビルドで名称が"
        "変更されました。"
    ),
    "notfound.link": "重要鉱物セクションへ →",
    "section.no_data_title": "データはまだ生成されていません。",
    "section.no_data_body": (
        "以下のページとパイプラインはすでに用意されていますが、USGSと"
        "UN Comtradeからの初回取得はまだ実行されていません。実行される"
        "まで、すべての数値は未取得として表示されます。"
    ),
    "section.no_data_link": "ビルド履歴を確認 →",
    "section.eight_minerals_title": "8つの鉱物",
    "section.eight_minerals_sub": (
        "掲載順に表示。数値は各ソースが公表している最新年のもの。"
    ),
    "section.two_indices_title": "2つの指標、それぞれ別の問い",
    "section.two_indices_sub": "鉱物ごとのページに2つの数値が並ぶ理由。",
    "caveats.heading": "この数値が語らないこと",
    "caveats.shared_note": (
        "いずれの指標も対象は国であって企業ではない。同じ親会社が異なる"
        "国に持つ2つの鉱山は、ここでは2つの独立した供給者として扱われる。"
    ),
    "notes.heading": "この鉱物についてのビルドノート。",
    "chart.read_method": "算出方法の全文を読む →",
    "hub.sections_title": "セクション",
    "hub.sections_sub": "素材群ごとに1セクション。それぞれ独立して完結する。",
    "hub.further_sections": "その他のセクション",
    "hub.not_yet_built": "未着手",
    "hub.further_blurb": (
        "パイプラインとレイアウトは共通化されているため、2つ目の素材群を"
        "追加するのに新しいサイトは要らず、カタログファイルと取得アダプタ"
        "を1つ足すだけで済む。"
    ),
    "hub.planned": "計画中",
    "hub.what_it_means_title": "この数値が意味すること",
    "hub.live": "稼働中",
    "panel.stage_title": "段階別の集中度",
    "panel.stage_sub": (
        "同じリチウムでも、鉱石・炭酸塩・水酸化物のどこを測るかで集中度は"
        "変わります。段階を選ぶと、その段階だけで算出した指数に切り替わります。"
        "既定は上の輸出側指標と同じヘッドライン(283691と282520の合算、"
        "USドル建て)です。"
    ),
    "stage.tablist": "測定する段階",
    "stage.sidelist": "申告側",
    "stage.headline_usd": "ヘッドライン(合算・USD)",
    "stage.ore": "鉱石・精鉱",
    "stage.carbonate": "炭酸塩",
    "stage.hydroxide": "水酸化物",
    "stage.mine_li_t": "鉱山生産(Li換算)",
    "side.world_export": "全世界向け輸出(自己申告)",
    "side.china_import": "中国の輸入申告(ミラー)",
    "stage.coverage": "報告完全性",
    "stage.no_coverage": "報告完全性は算出対象外",
    "stage.provisional_legend": "暫定値(報告完全性が不足)",
    "stage.confirmed_legend": "確定値",
    "source.reported": "自己申告",
    "source.partner_sum": "復元(相手国別合計)",
    "source.mirror": "ミラー採用",
    "source.estimated": "推計",
    "verification.unverified": "未検証",
    "verification.externally_confirmed": "外部照合済",
    "verification.externally_conflicting": "外部と食い違い",
    "evidence.close": "閉じる",
    "evidence.source": "照合したソース",
    "table.source": "採用根拠",
    "table.verification": "検証",
    # screener (hub and section index)
    "screener.search": "検索",
    "screener.placeholder": "鉱物名または元素記号",
    "screener.category": "カテゴリ",
    "screener.all_categories": "すべてのカテゴリ",
    "screener.caption": (
        "鉱物ごとの供給集中度。HHIは0〜10,000の尺度で、区分は鉱山側の値にもとづく。"
    ),
    "screener.pending": "準備中",
    "screener.under_review": "確認中",
    "screener.no_match": "該当する鉱物はありません。",
    "screener.showing": "{total}件中{shown}件を表示",
    "col.mineral": "鉱物",
    "col.mine_hhi": "鉱山HHI",
    "col.top_supplier": "最大供給国",
    "col.export_hhi": "輸出HHI",
    "col.band": "区分",
    "col.year": "年",
    "legend.title": "区分の読み方",
    "legend.caption": "区分の読み方",
    "legend.reading": "読み方",
    "stage.provisional_short": "暫定",
    # quote header (mineral pages)
    "quote.mine_hhi": "鉱山HHI",
    "quote.export_hhi": "輸出HHI",
    "quote.top_producer": "最大生産国",
    "quote.updated": "更新",
    "quote.provisional_title": "暫定値を含みます。",
    "quote.review_title": "貿易指標は確認中です。",
    "quote.coverage_title": "カバレッジ",
    "quote.globe_link": "地球儀で見る →",
    "hub.globe_link": "国別シェアを地球儀で見る →",
    # globe page
    "nav.globe": "地球儀",
    "globe.lede": (
        "各鉱物の鉱山生産と輸出が、どの国にどれだけあるか。公表済みの国別シェアを、"
        "鉱物と指標を1つずつ選んで表示します。数値は各鉱物ページと同じものです。"
    ),
    "globe.mineral": "鉱物",
    "globe.measure": "指標",
    "globe.no_data": "データなし",
    "globe.not_listed": "ソースに記載なし",
    "globe.legend_scale": (
        "すべての鉱物・指標で同じ尺度。0%には、ソースに記載のない国も含みます。"
    ),
    "globe.loading": "読み込み中…",
    "globe.load_failed": "地球儀のデータを読み込めませんでした。数値は各鉱物ページで確認できます。",
    "globe.table_title": "国別シェア",
    "globe.credit": (
        "国境データ:Natural Earth(パブリックドメイン)。地球儀の描画:globe.gl。"
        "シェア:USGS Mineral Commodity SummariesおよびUN Comtrade(各鉱物ページで公表済みのもの)。"
    ),
    "globe.aria": "{mineral}・{layer}({year}年)の国別シェアを示す地球儀。同じ数値を下の表に掲載。",
    "globe.share": "シェア",
    "globe.year": "対象年",
    "globe.source": "出典",
    "globe.leader": "首位国",
    "globe.cr3": "上位3カ国",
    "globe.coverage": "カバレッジ",
    "globe.coverage_named": "報告合計のうち、数値のある国が占める割合",
    "globe.coverage_world": "公表された世界合計のうち、数値のある国が占める割合",
    "globe.report_completeness": "報告完全性",
    "globe.no_data_list": "データなし",
    "globe.other": "その他(特定の国に帰属しない分) {pct}",
    "globe.provisional": "暫定値",
    "globe.page_link": "鉱物ページを開く →",
    "globe.show_all": "全{n}カ国を表示",
    "globe.show_fewer": "上位10カ国のみ表示",
    "globe.table_sub": "{mineral} · {layer} · {year}年",
    "globe.redirect": "{name}は{status}のため、地球儀では選べません。{fallback}を表示しています。",
    "globe.withheld": "データなし(非公表)",
}


def trend_phrase_ja(trend: dict | None) -> str:
    if not trend:
        return ""
    change = trend["change"]
    span = trend["to_year"] - trend["from_year"]
    if abs(change) < 25:
        return f"{trend['from_year']}年以降ほぼ横ばい"
    direction = "上昇" if change > 0 else "低下"
    return f"{span}年間で{abs(change):,.0f}{direction}"


def coverage_notice_ja(coverage: float) -> str:
    pct = coverage * 100
    return (
        f"カバレッジ {pct:.0f}%。上に記載した国だけで、公表されている世界合計の"
        "うちこの割合を占める。残りは非開示または未配分としてソース側で扱われて"
        "おり、特定の国に割り当てるのではなく指数の算出から除外している。した"
        "がって実際の指数は、表示されている値よりもやや低い可能性が高い。"
    )


def human_time_ja(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        stamp = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return stamp.strftime("%Y年%m月%d日 %H:%M UTC")


def rebuilt_notice_ja(generated_at_ja: str | None) -> str:
    if not generated_at_ja:
        return STRINGS_JA["footer.awaiting"]
    return f"データは最終 {generated_at_ja} に再構築されました"


def no_data_notice_ja(source: str) -> str:
    return f"この指標は、{source}からの初回取得が完了すると表示されます。"


# --------------------------------------------------------------- stage tabs
#
# The stage tabs are generated from pipeline/minerals.json, so their wording
# cannot live in the template the way the rest of the English chrome does:
# the template never knows which stages exist. Both languages are therefore
# kept here, keyed exactly as the ``data-i18n`` attribute the template emits,
# and the English side is looked up rather than written out.
#
# Keys are policy names ("ore", "carbonate", "hydroxide") rather than HS
# codes, so a second mineral measured at the same stages reuses the wording
# and a new stage needs one entry here instead of a template change.
LABELS_EN: dict[str, str] = {
    "stage.headline_usd": "Headline (combined, USD)",
    "stage.ore": "Ore and concentrate",
    "stage.carbonate": "Carbonate",
    "stage.hydroxide": "Hydroxide",
    "stage.mine_li_t": "Mine production (Li content)",
    "side.world_export": "Exports to the world (self-reported)",
    "side.china_import": "China's import declarations (mirror)",
    "source.reported": "Self-reported",
    "source.partner_sum": "Reconstructed (partner sum)",
    "source.mirror": "Mirror adopted",
    "source.estimated": "Estimated",
    "verification.unverified": "Unverified",
    "verification.externally_confirmed": "Externally confirmed",
    "verification.externally_conflicting": "Externally conflicting",
}


def label_en(key: str) -> str:
    """English wording for a generated label, falling back to the key itself.

    An unknown stage policy renders as its own name rather than as an empty
    tab: a pipeline that grows a stage this module has not learned yet stays
    legible instead of shipping a blank control.
    """
    if key in LABELS_EN:
        return LABELS_EN[key]
    return key.split(".", 1)[-1].replace("_", " ")


def label_ja(key: str) -> str:
    """Japanese wording for a generated label; empty means 'keep the English'."""
    return STRINGS_JA.get(key, "")


def stage_coverage_ja(coverage_pct: float) -> str:
    return f"報告完全性 {coverage_pct:.1f}%(その段階の全期間中央値に対する報告国数)"


# --------------------------------------------------------------- globe page
#
# Sentences written into critical-minerals/data/globe/<slug>.json, English
# and Japanese side by side. Country names are not part of them: the page
# lists no-data countries itself, by name, from the border file.

def globe_share_note_en(kind: str, world_coverage, no_data: list[str]) -> str:
    parts = []
    if kind == "reserves":
        parts.append(
            "Reserves are not supply concentration: they are the quantity estimated to be "
            "economically extractable, not what is produced or shipped."
        )
    if kind in ("mine", "reserves"):
        parts.append("Shares are of the total the USGS reports by country.")
        if isinstance(world_coverage, (int, float)) and world_coverage < 1:
            parts.append(
                f"The countries with a figure account for {world_coverage * 100:.1f}% of the "
                "published world total; the rest is withheld or unallocated at source and is "
                "not attributed to any country, as on the mineral page."
            )
    else:
        parts.append(
            "Shares are of the total the reporting countries declared; a country that did "
            "not report has no share on the map."
        )
    if no_data:
        parts.append("Countries listed without a figure are shown as no data, not as 0%.")
    return " ".join(parts)


def globe_share_note_ja(kind: str, world_coverage, no_data: list[str]) -> str:
    parts = []
    if kind == "reserves":
        parts.append(
            "埋蔵量は供給集中度そのものではなく、経済的に採掘可能と推計される量であり、"
            "生産量や出荷量ではありません。"
        )
    if kind in ("mine", "reserves"):
        parts.append("シェアはUSGSが国別に報告した合計に対する割合です。")
        if isinstance(world_coverage, (int, float)) and world_coverage < 1:
            parts.append(
                f"数値のある国の合計は、公表されている世界合計の{world_coverage * 100:.1f}%です。"
                "残りはソース側で非公表または未配分とされており、鉱物ページと同様に、"
                "特定の国には割り当てていません。"
            )
    else:
        parts.append(
            "シェアは報告国が申告した合計に対する割合です。報告のない国には、"
            "地図上でシェアを割り当てていません。"
        )
    if no_data:
        parts.append("数値のない国は0%ではなく「データなし」として表示しています。")
    return "".join(parts)


def globe_trade_measure_en(unit: str) -> str:
    if unit == "USD":
        return "share of reported export value (USD)"
    if unit == "t":
        return "share of reported export weight (t)"
    return f"share of reported exports ({unit})"


def globe_trade_measure_ja(unit: str) -> str:
    if unit == "USD":
        return "報告された輸出額(USドル)に占める割合"
    if unit == "t":
        return "報告された輸出重量(t)に占める割合"
    return f"報告された輸出({unit})に占める割合"


def provisional_legend_ja(years: list[int], coverage_pct: float | None) -> str:
    span = "・".join(f"{year}年" for year in years)
    if coverage_pct is None:
        return f"{span}は暫定値(報告完全性が不足)"
    return f"{span}は暫定値(報告完全性が不足、{coverage_pct:.1f}%)"
