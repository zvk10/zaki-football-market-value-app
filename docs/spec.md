# 仕様書:サッカー選手 市場価値可視化アプリ

- 作成日:2026-10-24(開発着手時点)
- 対象:Streamlit製Webアプリ(個人開発)
- 関連:CLAUDE.md(Claude Code用の前提ファイル)

---

## 1. 目的と前提

### 1.1 目的
サッカー選手の市場価値(Transfermarkt由来)の推移・ランキング・週間変動を可視化するアプリを作る。会社の評価期間(2026年10月〜2027年3月末)に紐づく個人開発で、初版を2026年12月末までにリリースする。

### 1.2 制約(絶対条件)
- 完全無料で運用する。無料枠を超える場合は課金ではなく停止する構成にする
- 非商用・個人利用の範囲で行う
- アプリ内にデータ出典(Transfermarkt由来のコミュニティデータセット)をクレジット表記する
- 閲覧者のログイン機能は作らない(誰でも閲覧可)

---

## 2. システム構成

```
Kaggle「player-scores」(CC0、週次更新)
  → GitHub Actions(週次cron、Pythonスクリプト実行)
    → Supabase(PostgreSQL)
      → Streamlit Cloud(st.connection + st.cache_data)
        → ユーザー(閲覧のみ)
```

| コンポーネント | 役割 | 備考 |
|---|---|---|
| Kaggle | データ提供元 | `davidcariboo/player-scores`。Kaggle APIで対象ファイルのみ取得 |
| GitHub Actions | 週次でスクリプトを実行する場所 | パブリックリポジトリなら無料・無制限。リポジトリへのCSVコミットはしない |
| Supabase | データ保管(PostgreSQL) | 無料枠500MB。Auth等の付帯機能は使わない |
| Streamlit Cloud | アプリのホスティング | 無料 |

### 2.1 接続方式(重要)
- Supabaseの直接接続(`db.xxx.supabase.co`)は**IPv6のみ**で、GitHub ActionsはIPv4のみのため**接続できない**
- GitHub Actions・Streamlit Cloudの両方で、**Supavisorのセッションモード接続文字列**(`...pooler.supabase.com:5432`)を使う
- トランザクションモード(6543)を使う場合は、接続ライブラリ側でprepared statementsを無効にする

### 2.2 秘匿情報(Secrets)
| 名前 | 登録先 | 内容 |
|---|---|---|
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | GitHub Secrets | Kaggle API認証 |
| `SUPABASE_DB_URL` | GitHub Secrets | 書き込み用接続文字列(セッションモード) |
| `connections.supabase.url` | Streamlit Cloud Secrets | 読み込み用接続文字列(セッションモード) |

- リポジトリはパブリックのため、接続文字列・APIキーは絶対にコミットしない(ローカルは`.env`を`.gitignore`)
- 推奨:Streamlit用には読み取り専用のDBロールを作り、その接続文字列を使う

---

## 3. データ仕様

### 3.1 取り込み対象(Kaggle側)
| ファイル | 用途 |
|---|---|
| `player_valuations.csv` | 市場価値の査定履歴(査定が更新された時点のみ行が存在) |
| `players.csv` | 選手名・生年月日・ポジション・国籍・所属クラブID |
| `clubs.csv` | クラブ名・所属リーグID |
| `competitions.csv` | リーグ名 |

※カラムの確定は、実際のCSVヘッダーを確認して行う(下記のテーブル定義は想定)。

### 3.2 Supabaseのテーブル(想定)
```sql
-- マスタ系(毎週洗い替え)
players(player_id PK, name, position, sub_position, country_of_citizenship,
        date_of_birth, current_club_id, ...)
clubs(club_id PK, name, domestic_competition_id, ...)
competitions(competition_id PK, name, country_name, ...)

-- 市場価値の全履歴(毎週洗い替え)
player_valuations(player_id, date, market_value_in_eur, ...)
  -- INDEX (player_id, date)

-- 週次スナップショット(追記型)
market_value_snapshots(
  player_id        integer,
  snapshot_date    date,
  market_value_in_eur bigint,
  PRIMARY KEY (player_id, snapshot_date)
)
```
結合:`player_valuations → players(player_id) → clubs(current_club_id) → competitions(domestic_competition_id)`

### 3.3 週次更新処理(`scripts/update_data.py`)
1. Kaggle APIで上記4ファイルのみダウンロード
2. **1トランザクション内**でマスタ系4テーブルを `TRUNCATE` → 再INSERT(失敗時は元のデータが残る)
   - `to_sql(if_exists="replace")` はテーブルを作り直して主キー・インデックスが消えるため使わない
3. `market_value_snapshots` に、各選手の最新の市場価値を `snapshot_date = 実行日` で追記
   - 同じ日の再実行に備え `ON CONFLICT (player_id, snapshot_date) DO UPDATE`(冪等)
   - 査定に変更がない選手も前回と同じ値で記録する(変化なし=0%として扱うため)
4. 初回実行時は前週のスナップショットが無いため、`player_valuations` の履歴から過去週分を遡って作る(任意)

### 3.4 容量見積もり
- 4万選手 × 週次 ≒ 約4MB/週(実データ)、インデックス込みで年間約260〜500MB
- 500MBに近づく場合は、古いスナップショットの間引きを検討する
- Supabaseダッシュボードの Database Size で定期確認する

---

## 4. 機能仕様

### F1. 選手検索+市場価値推移(MVP)
- 入力:選手名(部分一致、候補表示)
- 表示:氏名・所属クラブ・ポジション・国籍・年齢、現在の市場価値、前週比、リーグ内順位、市場価値の推移折れ線グラフ
- データ:`player_valuations` の全履歴(期間の制限なし)+`market_value_snapshots`(前週比)
- 画面モック作成済み

### F2. リーグ/クラブ別ランキング(MVP)
- リーグ・クラブ・ポジションで絞り込み、現在の市場価値順に一覧表示(ソート可)
- 表示件数は上位N件(初期値:50)

### F3. 週間変動ランキング
- 定義:最新の`snapshot_date`と、その直前の`snapshot_date`を比較(日付は固定せず自動で選ぶ)
  - 変化額 = 今回 − 前回、変化率 = 変化額 ÷ 前回 × 100
- 急上昇/急落を上位20件ずつ表示。比較に使った2つの日付を画面に明示する
- 前回値が0またはNULLの選手は除外。少額選手の極端な変化率を避けるため、前回値の下限(例:€1M以上)を設ける(値は要検討)

### F4. 選手比較
- 2〜3選手を選び、市場価値の推移を1つのグラフに重ねて表示

### F5(拡張・MVP対象外)エージェント機能
- LLMによる分析・示唆出しを追加する方針。具体的な内容は未定
- 注意:LLM APIは従量課金で無料枠がないため、「完全無料」前提との整合(実行回数の制限、キャッシュ、費用の許容範囲)を別途決める

---

## 5. 画面仕様

- 構成(暫定):複数ページ。ヘッダーに「選手検索 / ランキング / 比較」のナビ、フッターにデータ出典
- 共通:グラフは折れ線(推移)・棒(ランキング)、金額は€M表記
- キャッシュ:データが週次更新のため `st.cache_data` のTTLは長め(例:1日)。ユーザー間で共有される

---

## 6. リポジトリ構成(案)

```
.
├── CLAUDE.md
├── README.md                  # 出典・クレジット表記を含む
├── app.py                     # 選手検索(トップ)
├── pages/                     # ランキング・比較
├── lib/                       # DB接続・クエリ
├── scripts/update_data.py     # Kaggle → Supabase
├── sql/schema.sql
├── .github/workflows/update-data.yml
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 7. 非機能要件

- コスト:全サービス無料枠内。GitHubの支出上限は$0のまま変更しない
- 可用性:Supabase無料プロジェクトは7日間アクセスがないと一時停止するため、週次ジョブを確実に継続する(失敗に気づけるよう、Actionsの失敗通知を有効にしておく)
- 取得失敗時:マスタ更新はトランザクションで保護し、直近のデータでアプリが動き続ける

---

## 8. 開発の進め方(Claude Codeで構築)

1. Supabaseプロジェクト作成・接続文字列(セッションモード)取得(手作業)
2. `sql/schema.sql` 作成 → Supabaseへ適用 → 管理画面で確認
3. `update_data.py` を作成し、ローカルで実行して動作確認
4. GitHub Actionsワークフロー作成 → `workflow_dispatch` で手動実行して確認
5. Streamlit画面を機能ごとに追加(F1 → F2 → F3 → F4)し、都度ローカルで確認
6. Streamlit Cloudへデプロイ(Secrets登録は手作業)

---

## 9. スケジュール

| 期間 | 内容 |
|---|---|
| 2026年10月下旬〜11月上旬 | 基盤構築(手順1〜4)※10月下旬着手のため、10月中の完了から見直し |
| 2026年11月 | コア機能(F1・F2)でMVP完成 |
| 2026年12月 | F3・F4追加、仕上げ、初版リリース(目標:12月末) |
| 2027年1〜3月 | 改善・バッファ。F5(エージェント機能)の検討 |

---

## 10. 未確定事項

- テーブルの正式なカラム定義(実CSVのヘッダー確認後に確定)
- F3の前回値の下限額、表示件数
- F5の具体的な内容と、LLM費用の扱い
- 複数ページ構成の最終確定
- Jリーグなど、データセット対象外のリーグを扱うか(現時点では対象外)
