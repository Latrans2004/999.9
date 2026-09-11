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
