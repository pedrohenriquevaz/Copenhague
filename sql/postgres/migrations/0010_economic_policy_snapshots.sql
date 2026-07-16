ALTER TABLE economy_transactions
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_economy_transactions_idempotency
    ON economy_transactions(guild_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS economy_effect_claims (
    guild_id BIGINT NOT NULL CHECK (guild_id > 0),
    user_id BIGINT NOT NULL CHECK (user_id > 0),
    effect_key TEXT NOT NULL CHECK (BTRIM(effect_key) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, effect_key)
);

ALTER TABLE collective_race_bets
    ADD COLUMN IF NOT EXISTS economic_policy_json TEXT;

ALTER TABLE match_bet_tickets
    ADD COLUMN IF NOT EXISTS economic_policy_json TEXT;
