"""アプリの入口。各ページを st.navigation で束ね、全ページ共通の部品(サイドバーのナビ・出典)を描く。

ローカル起動:   ./app/run_app.sh
Streamlit Cloud: Main file path に app/app.py を指定
"""

import streamlit as st

st.set_page_config(page_title="選手市場価値", page_icon="⚽", layout="wide")

# ---------------------------------------------------------------------------
# ページ切り替え(サイドバーに表示)
# ---------------------------------------------------------------------------
pages = [
    st.Page(
        "app_pages/01_メインページ.py",
        title="メインページ",
        icon=":material/home:",
        url_path="main",
        default=True,
    ),
    st.Page(
        "app_pages/02_使い方.py",
        title="使い方がわからない時は",
        icon=":material/help:",
        url_path="help",
    ),
    st.Page(
        "app_pages/03_データソース.py",
        title="データソースについて",
        icon=":material/database:",
        url_path="data-source",
    ),
]

nav = st.navigation(pages, position="sidebar")
nav.run()

# --- 全ページ共通:データ出典(必須)---
st.divider()
st.caption(
    "データ出典:Transfermarkt のデータを元にしたコミュニティデータセット "
    "[dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)"
    "(Kaggle: davidcariboo/player-scores, CC0-1.0)。週次更新。"
    "本アプリは非公式・非商用の個人プロジェクトです。"
)
