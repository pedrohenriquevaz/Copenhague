CREATE TABLE IF NOT EXISTS shop_level_configs (
    guild_id BIGINT NOT NULL,
    level BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    price BIGINT NOT NULL,
    is_active BIGINT NOT NULL DEFAULT 1,
    created_by BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, level),
    UNIQUE (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS user_level_upgrades (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    level BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL REFERENCES economy_transactions(id),
    price_paid BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (guild_id, level)
        REFERENCES shop_level_configs(guild_id, level),
    UNIQUE (guild_id, user_id, level)
);

CREATE INDEX IF NOT EXISTS idx_shop_level_configs_active
    ON shop_level_configs(guild_id, is_active, level);

CREATE INDEX IF NOT EXISTS idx_user_level_upgrades_user
    ON user_level_upgrades(guild_id, user_id, level);
