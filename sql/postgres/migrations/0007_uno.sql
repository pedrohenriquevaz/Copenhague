CREATE TABLE IF NOT EXISTS uno_games (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    status TEXT NOT NULL,
    created_by BIGINT NOT NULL,
    player_ids_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS uno_actions (
    id BIGSERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL REFERENCES uno_games(id),
    user_id BIGINT,
    action_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_uno_games_guild_status
    ON uno_games(guild_id, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_uno_games_channel
    ON uno_games(guild_id, channel_id, status);

CREATE INDEX IF NOT EXISTS idx_uno_games_message
    ON uno_games(message_id);

CREATE INDEX IF NOT EXISTS idx_uno_actions_game
    ON uno_actions(game_id, created_at);
