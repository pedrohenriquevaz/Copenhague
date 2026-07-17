CREATE TABLE IF NOT EXISTS mlbb_auth_attempts (
    id UUID PRIMARY KEY,
    guild_id BIGINT NOT NULL CHECK (guild_id > 0),
    discord_user_id BIGINT NOT NULL CHECK (discord_user_id > 0),
    role_id BIGINT NOT NULL CHECK (role_id > 0),
    zone_id BIGINT NOT NULL CHECK (zone_id > 0),
    purpose VARCHAR(16) NOT NULL CHECK (purpose IN ('LINK', 'REAUTH')),
    status VARCHAR(32) NOT NULL CHECK (
        status IN (
            'CREATED',
            'CODE_SENT',
            'VERIFYING',
            'VERIFIED',
            'EXPIRED',
            'FAILED',
            'CANCELLED'
        )
    ),
    attempts SMALLINT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    expires_at TIMESTAMPTZ NOT NULL,
    code_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mlbb_open_attempt_user_guild
ON mlbb_auth_attempts(guild_id, discord_user_id)
WHERE status IN ('CREATED', 'CODE_SENT', 'VERIFYING');

CREATE INDEX IF NOT EXISTS idx_mlbb_auth_attempts_expiry
ON mlbb_auth_attempts(expires_at)
WHERE status IN ('CREATED', 'CODE_SENT', 'VERIFYING');

CREATE TABLE IF NOT EXISTS mlbb_account_links (
    guild_id BIGINT NOT NULL CHECK (guild_id > 0),
    discord_user_id BIGINT NOT NULL CHECK (discord_user_id > 0),
    role_id BIGINT NOT NULL CHECK (role_id > 0),
    zone_id BIGINT NOT NULL CHECK (zone_id > 0),
    player_name TEXT,
    avatar_url TEXT,
    country_code VARCHAR(8),
    encrypted_jwt TEXT,
    status VARCHAR(32) NOT NULL CHECK (
        status IN ('PENDING', 'ACTIVE', 'REAUTH_REQUIRED', 'REVOKED')
    ),
    visibility VARCHAR(16) NOT NULL DEFAULT 'GUILD' CHECK (
        visibility IN ('PRIVATE', 'GUILD', 'PUBLIC')
    ),
    verified_at TIMESTAMPTZ,
    last_validated_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_mlbb_account_links
        PRIMARY KEY (guild_id, discord_user_id),
    CONSTRAINT uq_mlbb_account_links_game_account
        UNIQUE (guild_id, role_id, zone_id),
    CONSTRAINT ck_mlbb_account_links_credentials
        CHECK (
            (status IN ('ACTIVE', 'REAUTH_REQUIRED') AND encrypted_jwt IS NOT NULL)
            OR (status IN ('PENDING', 'REVOKED') AND encrypted_jwt IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_mlbb_links_game_account
ON mlbb_account_links(guild_id, role_id, zone_id);

CREATE INDEX IF NOT EXISTS idx_mlbb_links_status
ON mlbb_account_links(guild_id, status);
