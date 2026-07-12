ALTER TABLE guild_settings
    ADD COLUMN IF NOT EXISTS savings_daily_interest_bps BIGINT NOT NULL DEFAULT 0;

ALTER TABLE shop_level_configs
    ADD COLUMN IF NOT EXISTS saves_reward BIGINT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS user_savings_accounts (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    balance BIGINT NOT NULL DEFAULT 0,
    total_interest_earned BIGINT NOT NULL DEFAULT 0,
    last_interest_at TEXT NOT NULL,
    locked_until TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_savings_accounts_guild
    ON user_savings_accounts(guild_id, user_id);
