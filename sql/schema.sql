-- 市場価値アプリ用テーブル定義(Supabase / PostgreSQL)

-- 大会・リーグ
CREATE TABLE IF NOT EXISTS competitions (
    competition_id  text PRIMARY KEY,
    name            text,
    sub_type        text,
    type            text,
    country_name    text,
    confederation   text
);

-- クラブ
CREATE TABLE IF NOT EXISTS clubs (
    club_id                  integer PRIMARY KEY,
    name                     text,
    domestic_competition_id  text,
    total_market_value       bigint,
    squad_size               integer,
    average_age              numeric,
    last_season              integer
);

-- 選手(urlはTransfermarktの選手ページ。出典リンクに使う)
CREATE TABLE IF NOT EXISTS players (
    player_id                             integer PRIMARY KEY,
    name                                  text,
    last_season                           integer,
    current_club_id                       integer,
    current_club_name                     text,
    current_club_domestic_competition_id  text,
    country_of_citizenship                text,
    date_of_birth                         date,
    position                              text,
    sub_position                          text,
    contract_expiration_date              date,
    international_caps                    integer,
    international_goals                   integer,
    market_value_in_eur                   bigint,
    highest_market_value_in_eur           bigint,
    url                                   text
);
CREATE INDEX IF NOT EXISTS idx_players_club ON players (current_club_id);
CREATE INDEX IF NOT EXISTS idx_players_competition ON players (current_club_domestic_competition_id);

-- 市場価値の履歴(査定が更新された時点の行のみ)
CREATE TABLE IF NOT EXISTS player_valuations (
    player_id                            integer NOT NULL,
    date                                 date NOT NULL,
    market_value_in_eur                  bigint,
    current_club_id                      integer,
    player_club_domestic_competition_id  text
);
CREATE INDEX IF NOT EXISTS idx_player_valuations_player_date ON player_valuations (player_id, date);

-- 週次スナップショット(追記型)
CREATE TABLE IF NOT EXISTS market_value_snapshots (
    player_id            integer NOT NULL,
    snapshot_date        date NOT NULL,
    market_value_in_eur  bigint,
    PRIMARY KEY (player_id, snapshot_date)
);

-- 外部のAPI経由でテーブルに触れないようにする(RLS有効化。ポリシーは作らない)
ALTER TABLE competitions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE clubs                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE players                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_valuations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_value_snapshots  ENABLE ROW LEVEL SECURITY;