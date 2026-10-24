# サッカー選手 市場価値可視化アプリ

このファイルはClaude Codeがプロジェクトルートで自動的に読み込む設定ファイルです。作業を始める前に必ずこの内容を前提として動いてください。

## プロジェクト概要

サッカー選手の市場価値(Transfermarkt由来データ)を可視化するStreamlitアプリ。個人の会社評価(2026年10月〜2027年3月末)に紐づくプロジェクトで、2026年10月から約3ヶ月(12月末目安)で初版をリリースする。

## 絶対条件

- **完全無料で運用すること**。商用利用はせず、個人利用の範囲。全サービス(GitHub Actions、Supabase、Streamlit Cloud、Kaggle)は無料プランの範囲内で構成し、意図しない課金が発生しない設定(支出上限$0など)を徹底する
- データ出典(Transfermarkt由来のコミュニティデータセットである旨)をアプリ内にクレジット表記すること

## データ

### データソース
- Kaggleデータセット「davidcariboo/player-scores」(元は dcaribou/transfermarkt-datasets、CC0-1.0ライセンス、週次更新)
- 使用ファイル:`player_valuations.csv`、`players.csv`、`clubs.csv`、`competitions.csv`

### データ更新方式
- GitHub Actionsで週次cron実行。Pythonスクリプト(`kaggle`ライブラリ)でKaggle APIから対象ファイルのみ取得し、Supabaseへ書き込む
- マスタ系テーブル(players/clubs/competitions/player_valuations)は毎回洗い替え(`if_exists="replace"`)
- 週間変動ランキング用に、選手ごとの最新市場価値を`market_value_snapshots`テーブルへ週次で追記(`if_exists="append"`)。査定額に変化がない週も「現状維持」として記録すること

## システム構成

```
Kaggle(データソース)
  → GitHub Actions(週次cron、.pyでKaggle API実行)
    → Supabase(PostgreSQL、保存)
      → Streamlit Cloud(st.connection + st.cache_dataで読み込み)
        → ユーザー(ログイン不要、閲覧のみ)
```

- GitHub Actionsは「定期的にPythonスクリプトを実行する場所」としてのみ使う。リポジトリへのCSVコミットは行わない
- Supabaseは素のPostgreSQLとして使う。Auth機能などの付帯機能は使用しない
- Kaggle API認証情報、Supabase接続文字列はGitHub SecretsとStreamlit Cloud Secretsでそれぞれ管理する(同じ接続文字列を両方に登録する)

## テーブル設計の方針

`player_valuations`(player_id)→`players`(player_id, current_club_id)→`clubs`(club_id, domestic_competition_id)→`competitions`(competition_id)の4段JOINで、選手名・クラブ名・リーグ名を表示する。

## 機能要件(優先順位順ではなく候補)

1. 選手検索+市場価値推移グラフ(折れ線、基本情報も併記)
2. リーグ/クラブ別ランキング(絞り込み+ソート)
3. 週間変動ランキング(急上昇/急落、前週スナップショットとの比較)
4. 選手同士の比較(複数選手の推移を1グラフに重ねる)

画面構成(1画面完結 or 複数ページ)とMVP範囲の優先順位は未確定。実装時に相談すること。

## スケジュール

| 期間 | 内容 |
|---|---|
| 2026年10月 | 基盤構築:テーブル設計確定、Supabase作成、GitHub Actions疎通確認 |
| 2026年11月 | コア機能実装(検索+推移グラフ、ランキング)でMVP完成 |
| 2026年12月 | 追加機能・仕上げ・初版リリース |
| 2027年1〜3月 | フィードバック改善・バッファ |

## 実装時の注意

- コスト:無料枠超過時は自動課金ではなく安全に停止する設定にする
- 可用性:Supabase無料プロジェクトが7日間非アクティブで一時停止しないよう、週次実行を確実に継続する設計にする
