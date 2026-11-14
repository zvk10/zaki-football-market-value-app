"""データソースページ(叩き台):出典・ライセンス・更新方法・収録範囲。"""

import pandas as pd
import streamlit as st

CACHE_TTL = "1d"  # データは週次更新


def load_data_summary() -> pd.Series:
    """データ基準日と収録件数。"""
    return st.connection("supabase", type="sql").query(
        """
        SELECT
            (SELECT MAX(date) FROM player_valuations) AS latest_date,
            (SELECT COUNT(*)  FROM players)           AS player_count,
            (SELECT COUNT(*)  FROM player_valuations) AS valuation_count
        """,
        ttl=CACHE_TTL,
    ).iloc[0]


st.title("データソースについて")

# --- 現在のデータ ---
st.header("現在のデータ")
try:
    summary = load_data_summary()
    cols = st.columns(3)
    latest = summary["latest_date"]
    cols[0].metric("データ基準日", f"{pd.to_datetime(latest):%Y-%m-%d}" if pd.notna(latest) else "-")
    cols[1].metric("収録選手数", f"{int(summary['player_count']):,}人")
    cols[2].metric("査定履歴の件数", f"{int(summary['valuation_count']):,}件")
    st.caption("データ基準日は、収録データの中で最も新しい査定日です。")
except Exception:
    st.warning("データベースに接続できないため、現在のデータ状況を表示できません。")

# --- 出典 ---
st.header("出典")
st.markdown(
    """
- データセット:[dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)
  (Kaggle:[davidcariboo/player-scores](https://www.kaggle.com/datasets/davidcariboo/player-scores))
- 元データ:[Transfermarkt](https://www.transfermarkt.com/) の公開情報をもとに、コミュニティが作成したデータセットです
- ライセンス:CC0-1.0(パブリックドメイン)
"""
)

# --- 収録範囲 ---
st.header("収録範囲")
st.markdown(
    """
- 対象リーグ:プレミアリーグ(イングランド)
- 対象選手:各リーグに現在所属している選手
- 市場価値の履歴:Transfermarkt で査定が行われた日ごとの金額
"""
)

# --- 更新の仕組み ---
st.header("更新の仕組み")
st.write("データは週1回、次の流れで自動更新しています。")
st.markdown(
    """
1. Kaggle から最新のデータセットを取得
2. データベース(Supabase)の内容を入れ替え
3. このアプリで表示(表示内容は最大1日キャッシュされます)
"""
)

# --- 注意事項 ---
st.header("注意事項")
st.info(
    "市場価値は Transfermarkt による推定値であり、実際の移籍金や年俸を示すものではありません。"
    "本アプリは非公式・非商用の個人プロジェクトで、Transfermarkt とは関係ありません。",
    icon=":material/info:",
)
