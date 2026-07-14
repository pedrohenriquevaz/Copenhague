ALTER TABLE giveaway_claims
    DROP CONSTRAINT IF EXISTS giveaway_claims_event_id_user_id_key;

CREATE INDEX IF NOT EXISTS idx_giveaway_claims_event_user
    ON giveaway_claims(event_id, user_id);
