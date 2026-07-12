ALTER TABLE guild_settings
    ADD COLUMN IF NOT EXISTS casino_min_bet_truco BIGINT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS truco_games (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    status TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    stake BIGINT NOT NULL,
    player_ids_json TEXT NOT NULL,
    accepted_user_ids_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS truco_actions (
    id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES truco_games(id),
    user_id BIGINT,
    action_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_truco_games_guild_status
    ON truco_games(guild_id, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_truco_games_message
    ON truco_games(message_id);

CREATE INDEX IF NOT EXISTS idx_truco_actions_game
    ON truco_actions(game_id, created_at);
