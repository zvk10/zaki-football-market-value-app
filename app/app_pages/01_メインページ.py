"""メインページ(叩き台):選手検索+市場価値推移(仕様書 F1)。

起動方法(app/app.py から読み込まれる):
    ./app/run_app.sh

※ st.set_page_config と出典フッターは app/app.py 側で全ページ共通に設定している

前提:
    .streamlit/secrets.toml に [connections.supabase] の url(セッションモード接続文字列)を設定済み
"""

from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

# データは週次更新なのでキャッシュは長め(ユーザー間で共有される)
CACHE_TTL = "1d"


# ---------------------------------------------------------------------------
# データ取得
# ---------------------------------------------------------------------------
def get_conn():
    return st.connection("supabase", type="sql")


def load_player_options(league: str) -> pd.DataFrame:
    """選択肢用の選手一覧(市場価値の高い順)。league が "ALL" なら全リーグ。"""
    return get_conn().query(
        """
        SELECT player_id, name, current_club_name, market_value_in_eur
        FROM players
        WHERE :league = 'ALL' OR current_club_domestic_competition_id = :league
        ORDER BY market_value_in_eur DESC NULLS LAST, name
        """,
        params={"league": league},
        ttl=CACHE_TTL,
    )


def load_player_detail(player_id: int) -> pd.Series | None:
    """選手の基本情報+クラブ名・リーグ名・リーグ内順位。"""
    df = get_conn().query(
        """
        WITH ranked AS (
            SELECT
                player_id,
                RANK() OVER (
                    PARTITION BY current_club_domestic_competition_id
                    ORDER BY market_value_in_eur DESC NULLS LAST
                ) AS league_rank,
                COUNT(*) OVER (PARTITION BY current_club_domestic_competition_id) AS league_players
            FROM players
        )
        SELECT
            p.player_id, p.name, p.position, p.sub_position,
            p.country_of_citizenship, p.date_of_birth, p.contract_expiration_date,
            p.market_value_in_eur, p.highest_market_value_in_eur, p.url,
            COALESCE(c.name, p.current_club_name) AS club_name,
            comp.name AS competition_name,
            r.league_rank, r.league_players
        FROM players p
        LEFT JOIN clubs c          ON c.club_id = p.current_club_id
        LEFT JOIN competitions comp ON comp.competition_id = c.domestic_competition_id
        LEFT JOIN ranked r         ON r.player_id = p.player_id
        WHERE p.player_id = :player_id
        """,
        params={"player_id": player_id},
        ttl=CACHE_TTL,
    )
    return None if df.empty else df.iloc[0]


def load_valuations(player_id: int) -> pd.DataFrame:
    """市場価値の全履歴。"""
    df = get_conn().query(
        """
        SELECT date, market_value_in_eur
        FROM player_valuations
        WHERE player_id = :player_id
        ORDER BY date
        """,
        params={"player_id": player_id},
        ttl=CACHE_TTL,
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_weekly_change(player_id: int) -> pd.DataFrame:
    """最新2回分のスナップショット(前週比用)。データがなければ空。"""
    return get_conn().query(
        """
        SELECT snapshot_date, market_value_in_eur
        FROM market_value_snapshots
        WHERE player_id = :player_id
        ORDER BY snapshot_date DESC
        LIMIT 2
        """,
        params={"player_id": player_id},
        ttl=CACHE_TTL,
    )


# ---------------------------------------------------------------------------
# 表示用ヘルパー
# ---------------------------------------------------------------------------
def fmt_eur(value) -> str:
    """金額を €M / €k 表記にする。"""
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:,.0f}k"
    return f"€{value:,.0f}"


def calc_age(birth) -> str:
    if birth is None or pd.isna(birth):
        return "-"
    birth = pd.to_datetime(birth).date()
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    return f"{age}歳"


def fmt_date(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def value_chart(df: pd.DataFrame) -> alt.Chart:
    """市場価値推移の折れ線(査定日間は値が据え置きなので階段状)。"""
    plot = df.assign(value_m=df["market_value_in_eur"] / 1_000_000)
    base = alt.Chart(plot).encode(
        x=alt.X("date:T", title="査定日"),
        y=alt.Y("value_m:Q", title="市場価値(€M)"),
        tooltip=[
            alt.Tooltip("date:T", title="査定日", format="%Y-%m-%d"),
            alt.Tooltip("value_m:Q", title="市場価値(€M)", format=",.1f"),
        ],
    )
    line = base.mark_line(interpolate="step-after")
    points = base.mark_circle(size=50)
    return (line + points).properties(height=380)


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
st.title("⚽ 選手の市場価値")
st.caption("選手名を入力すると候補が絞り込まれます。")

# 共通サイドバー(app.py)で選んだリーグ
league = st.session_state.get("league", "ALL")

try:
    options = load_player_options(league)
except Exception as e:  # 接続設定ミスなどを画面で分かるようにする(叩き台用)
    st.error("データベースに接続できませんでした。secrets.toml の設定を確認してください。")
    st.exception(e)
    st.stop()

if options.empty:
    st.warning("選手データがありません。データ更新スクリプトの実行状況を確認してください。")
    st.stop()

labels = {
    row.player_id: f"{row.name}({row.current_club_name or '所属不明'})"
    for row in options.itertuples()
}
player_id = st.selectbox(
    "選手を検索",
    options=list(labels),
    format_func=labels.get,
    index=0,
    placeholder="選手名を入力",
)

detail = load_player_detail(int(player_id))
if detail is None:
    st.warning("選手情報が見つかりませんでした。")
    st.stop()

# --- 基本情報 ---
st.subheader(detail["name"])
info_cols = st.columns(4)
info_cols[0].markdown(f"**クラブ**  \n{detail['club_name'] or '-'}")
info_cols[1].markdown(f"**リーグ**  \n{detail['competition_name'] or '-'}")
info_cols[2].markdown(
    f"**ポジション**  \n{detail['position'] or '-'}"
    + (f" / {detail['sub_position']}" if detail["sub_position"] else "")
)
info_cols[3].markdown(
    f"**国籍 / 年齢**  \n{detail['country_of_citizenship'] or '-'} / {calc_age(detail['date_of_birth'])}"
)

# --- 指標 ---
weekly = load_weekly_change(int(player_id))
delta = None
if len(weekly) == 2 and weekly.iloc[1]["market_value_in_eur"]:
    diff = weekly.iloc[0]["market_value_in_eur"] - weekly.iloc[1]["market_value_in_eur"]
    delta = f"{'+' if diff >= 0 else '-'}{fmt_eur(abs(diff))}(前週比)"

metric_cols = st.columns(4)
metric_cols[0].metric("現在の市場価値", fmt_eur(detail["market_value_in_eur"]), delta=delta)
metric_cols[1].metric("自己最高額", fmt_eur(detail["highest_market_value_in_eur"]))
metric_cols[2].metric(
    "リーグ内順位",
    f"{int(detail['league_rank'])}位 / {int(detail['league_players'])}人"
    if pd.notna(detail["league_rank"])
    else "-",
)
metric_cols[3].metric("契約満了", fmt_date(detail["contract_expiration_date"]))
if delta is None:
    st.caption("※ 前週比は週次スナップショットが2週分たまると表示されます。")

# --- 推移グラフ ---
st.subheader("市場価値の推移")
valuations = load_valuations(int(player_id))
if valuations.empty:
    st.info("この選手の査定履歴はありません。")
else:
    st.altair_chart(value_chart(valuations), width="stretch")
    with st.expander("査定履歴(表)"):
        st.dataframe(
            valuations.sort_values("date", ascending=False).assign(
                date=lambda d: d["date"].dt.strftime("%Y-%m-%d"),
                market_value_in_eur=lambda d: d["market_value_in_eur"].map(fmt_eur),
            ).rename(columns={"date": "査定日", "market_value_in_eur": "市場価値"}),
            hide_index=True,
            width="stretch",
        )

if detail["url"]:
    st.link_button("Transfermarktで見る", detail["url"])
