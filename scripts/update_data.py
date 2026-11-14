"""Kaggle(davidcariboo/player-scores)のCSVを読み込み、Supabaseの4テーブルを洗い替えする。

使い方:
    .venv/bin/python scripts/update_data.py            # DBへ書き込み
    .venv/bin/python scripts/update_data.py --dry-run  # DBに触れず内容確認のみ

環境変数:
    TARGET_COMPETITIONS  対象リーグの competition_id(カンマ区切り。未設定なら GB1)
    SUPABASE_DB_URL      Supabaseの接続文字列(セッションモード)。--dry-run では不要
    KAGGLE_API_TOKEN     tmp_data/ にCSVがない場合のみ必要

注意: market_value_snapshots には書き込まない(データ更新停止中のため)。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

KAGGLE_DATASET = "davidcariboo/player-scores"
DATA_DIR = Path(__file__).resolve().parent.parent / "tmp_data"
DEFAULT_COMPETITIONS = "GB1"

# 安全確認のしきい値
MIN_RAW_PLAYERS = 10_000
MIN_RAW_VALUATIONS = 100_000
MIN_FILTERED_PLAYERS = 100

# sql/schema.sql に合わせた列定義(列名: 型)
#   str: 文字列 / int: 整数(Int64, 欠損可) / float: 小数 / date: 日付
SCHEMA: dict[str, dict[str, str]] = {
    "competitions": {
        "competition_id": "str",
        "name": "str",
        "sub_type": "str",
        "type": "str",
        "country_name": "str",
        "confederation": "str",
    },
    "clubs": {
        "club_id": "int",
        "name": "str",
        "domestic_competition_id": "str",
        "total_market_value": "int",
        "squad_size": "int",
        "average_age": "float",
        "last_season": "int",
    },
    "players": {
        "player_id": "int",
        "name": "str",
        "last_season": "int",
        "current_club_id": "int",
        "current_club_name": "str",
        "current_club_domestic_competition_id": "str",
        "country_of_citizenship": "str",
        "date_of_birth": "date",
        "position": "str",
        "sub_position": "str",
        "contract_expiration_date": "date",
        "international_caps": "int",
        "international_goals": "int",
        "market_value_in_eur": "int",
        "highest_market_value_in_eur": "int",
        "url": "str",
    },
    "player_valuations": {
        "player_id": "int",
        "date": "date",
        "market_value_in_eur": "int",
        "current_club_id": "int",
        "player_club_domestic_competition_id": "str",
    },
}

# 主キー(重複があれば投入前に止める)
PRIMARY_KEYS = {
    "competitions": "competition_id",
    "clubs": "club_id",
    "players": "player_id",
}

# 書き込み順(TRUNCATEと再投入)
TABLES = ["competitions", "clubs", "players", "player_valuations"]


class SafetyCheckError(Exception):
    """安全確認に失敗した(DBには触れていない)。"""


# ---------------------------------------------------------------------------
# 1. CSVの取得
# ---------------------------------------------------------------------------
def ensure_csv_files() -> None:
    """tmp_data/ に4つのCSVが揃っていなければ Kaggle からダウンロードする。"""
    missing = [t for t in TABLES if not (DATA_DIR / f"{t}.csv").exists()]
    if not missing:
        print(f"[取得] {DATA_DIR.name}/ の既存CSVを使用します")
        return

    print(f"[取得] CSVが不足しているため Kaggle からダウンロードします: {', '.join(missing)}")
    if not os.environ.get("KAGGLE_API_TOKEN"):
        raise RuntimeError("KAGGLE_API_TOKEN が設定されていません")

    # kaggle は import 時に認証を行うため、必要になったときだけ読み込む
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 版の混在を避けるため、4ファイルとも取り直す
    for table in TABLES:
        api.dataset_download_file(
            KAGGLE_DATASET, f"{table}.csv", path=str(DATA_DIR), force=True, quiet=True, unzip=True
        )
        if not (DATA_DIR / f"{table}.csv").exists():
            raise RuntimeError(f"{table}.csv のダウンロードに失敗しました")
    print("[取得] ダウンロード完了")


# ---------------------------------------------------------------------------
# 2. 読み込みと変換
# ---------------------------------------------------------------------------
def convert_column(series: pd.Series, kind: str) -> pd.Series:
    if kind == "str":
        stripped = series.str.strip()
        return stripped.mask(stripped == "")  # 空白だけの値は NULL にする
    if kind == "int":
        # 一度数値にしてから Int64 へ(小数部がある値はエラーで止まる)
        return pd.to_numeric(series, errors="raise").astype("Int64")
    if kind == "float":
        return pd.to_numeric(series, errors="raise").astype("float64")
    if kind == "date":
        # "1978-06-09 00:00:00" → date(1978, 6, 9)。欠損は None
        parsed = pd.to_datetime(series, errors="raise")
        return pd.Series(
            [d.date() if pd.notna(d) else None for d in parsed], index=series.index, dtype="object"
        )
    raise ValueError(f"未知の型: {kind}")


def load_table(table: str) -> pd.DataFrame:
    columns = SCHEMA[table]
    # 型推測をさせず、すべて文字列で読んでから明示的に変換する
    df = pd.read_csv(DATA_DIR / f"{table}.csv", dtype=str, keep_default_na=True)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"{table}.csv に必要な列がありません: {missing}")
    df = df[list(columns)].copy()
    for col, kind in columns.items():
        df[col] = convert_column(df[col], kind)
    return df


# ---------------------------------------------------------------------------
# 3. 絞り込みと安全確認
# ---------------------------------------------------------------------------
def target_competitions() -> list[str]:
    raw = os.environ.get("TARGET_COMPETITIONS", "").strip() or DEFAULT_COMPETITIONS
    targets = [c.strip() for c in raw.split(",") if c.strip()]
    if not targets:
        raise SafetyCheckError("TARGET_COMPETITIONS に有効な値がありません")
    return targets


def build_frames(targets: list[str]) -> dict[str, pd.DataFrame]:
    frames = {t: load_table(t) for t in TABLES}

    raw_players = len(frames["players"])
    raw_valuations = len(frames["player_valuations"])
    print(f"[確認] 絞り込み前: players={raw_players:,} 行, player_valuations={raw_valuations:,} 行")
    if raw_players < MIN_RAW_PLAYERS:
        raise SafetyCheckError(f"絞り込み前の players が {MIN_RAW_PLAYERS:,} 行未満です({raw_players:,} 行)")
    if raw_valuations < MIN_RAW_VALUATIONS:
        raise SafetyCheckError(
            f"絞り込み前の player_valuations が {MIN_RAW_VALUATIONS:,} 行未満です({raw_valuations:,} 行)"
        )

    known = set(frames["competitions"]["competition_id"].dropna())
    unknown = [t for t in targets if t not in known]
    if unknown:
        print(f"[警告] competitions に存在しない competition_id: {', '.join(unknown)}")

    players = frames["players"]
    players = players[players["current_club_domestic_competition_id"].isin(targets)].reset_index(drop=True)
    if len(players) < MIN_FILTERED_PLAYERS:
        raise SafetyCheckError(f"絞り込み後の players が {MIN_FILTERED_PLAYERS} 行未満です({len(players)} 行)")

    valuations = frames["player_valuations"]
    valuations = valuations[valuations["player_id"].isin(players["player_id"])].reset_index(drop=True)

    print(f"[確認] データセット全体の最新査定日: {frames['player_valuations']['date'].max()}")
    frames["players"] = players
    frames["player_valuations"] = valuations

    for table, key in PRIMARY_KEYS.items():
        dup = frames[table][key].duplicated().sum()
        if dup:
            raise SafetyCheckError(f"{table}.{key} に重複が {dup} 件あります")
        if frames[table][key].isna().any():
            raise SafetyCheckError(f"{table}.{key} に空欄があります")
    if valuations[["player_id", "date"]].isna().any().any():
        raise SafetyCheckError("player_valuations の player_id / date に空欄があります")

    return frames


# ---------------------------------------------------------------------------
# 4. DBへの書き込み
# ---------------------------------------------------------------------------
def write_to_db(frames: dict[str, pd.DataFrame]) -> None:
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL が設定されていません")
    if db_url.startswith("postgres://"):  # SQLAlchemy は postgresql:// のみ受け付ける
        db_url = "postgresql://" + db_url[len("postgres://"):]

    # hide_parameters: エラー時にSQLのパラメータ(データ値)をログへ出さない
    engine = create_engine(db_url, hide_parameters=True, pool_pre_ping=True)
    try:
        # engine.begin(): ブロックを抜けたらCOMMIT、例外が出たら全体をROLLBACK
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)}"))
            for table in TABLES:
                frames[table].to_sql(
                    table, conn, if_exists="append", index=False, method="multi", chunksize=1000
                )
                print(f"[書込] {table}: {len(frames[table]):,} 行")
    finally:
        engine.dispose()
    print("[書込] コミット完了")


# ---------------------------------------------------------------------------
# dry-run 表示
# ---------------------------------------------------------------------------
def print_summary(frames: dict[str, pd.DataFrame], targets: list[str]) -> None:
    comps = frames["competitions"].set_index("competition_id")["name"]
    labels = [f"{t}({comps.get(t, '不明')})" for t in targets]
    print(f"\n対象リーグ: {', '.join(labels)}")
    print(f"データ基準日(player_valuations の最新 date): {frames['player_valuations']['date'].max()}")
    print("\n投入予定の行数:")
    for table in TABLES:
        print(f"  {table:<18} {len(frames[table]):>8,} 行")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        for table in TABLES:
            print(f"\n--- {table}(先頭5行)---")
            print(frames[table].head(5).to_string(index=False))
            print("dtypes: " + ", ".join(f"{c}={t}" for c, t in frames[table].dtypes.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Kaggleデータを Supabase へ洗い替えする")
    parser.add_argument("--dry-run", action="store_true", help="DBに書き込まず内容を表示する")
    args = parser.parse_args()

    load_dotenv(".env")

    try:
        targets = target_competitions()
        ensure_csv_files()
        frames = build_frames(targets)
    except SafetyCheckError as e:
        print(f"[中止] 安全確認に失敗しました(DBには触れていません): {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print_summary(frames, targets)
        print("\n[dry-run] DBへの書き込みは行っていません")
        return 0

    write_to_db(frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
