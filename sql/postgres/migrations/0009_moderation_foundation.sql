CREATE TABLE IF NOT EXISTS moderation_settings (
    guild_id BIGINT PRIMARY KEY,
    log_channel_id BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS moderation_authorized_roles (
    guild_id BIGINT NOT NULL REFERENCES moderation_settings(guild_id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS moderation_cases (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    action_type TEXT NOT NULL,
    target_user_id BIGINT NOT NULL,
    moderator_user_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds BIGINT CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    status TEXT NOT NULL,
    origin TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_moderation_cases_guild_created
    ON moderation_cases(guild_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_cases_guild_target
    ON moderation_cases(guild_id, target_user_id, created_at DESC);
