CREATE TABLE IF NOT EXISTS user_credit_protection (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    saves BIGINT NOT NULL DEFAULT 0,
    lose_streak BIGINT NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_credit_protection_guild
    ON user_credit_protection(guild_id, user_id);
