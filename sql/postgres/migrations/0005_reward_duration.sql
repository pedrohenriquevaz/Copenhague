ALTER TABLE reward_items
    ADD COLUMN IF NOT EXISTS duration_days BIGINT;
