#!/usr/bin/env bash
# ローカルでアプリを起動する(Streamlit Cloud では使わない)
#   使い方: ./app/run_app.sh                       → http://localhost:8501
#           ./app/run_app.sh --server.port 8502    (追加オプションはそのまま streamlit に渡す)
set -euo pipefail

# どこから実行してもプロジェクトのルートへ移動する(.streamlit/secrets.toml を読ませるため)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STREAMLIT=".venv/bin/streamlit"
ENTRY="app/app.py"

if [[ ! -x "$STREAMLIT" ]]; then
  echo "[エラー] .venv がありません。先に以下を実行してください:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -f ".streamlit/secrets.toml" ]]; then
  echo "[エラー] .streamlit/secrets.toml がありません(Supabase の接続文字列を設定してください)" >&2
  exit 1
fi

if [[ ! -f "$ENTRY" ]]; then
  echo "[エラー] $ENTRY がありません" >&2
  exit 1
fi

exec "$STREAMLIT" run "$ENTRY" "$@"
