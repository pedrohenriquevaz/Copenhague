CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT PRIMARY KEY,
    currency_name TEXT NOT NULL DEFAULT 'pontos',
    voice_points_per_minute BIGINT NOT NULL DEFAULT 2,
    message_points BIGINT NOT NULL DEFAULT 1,
    activity_provider TEXT NOT NULL DEFAULT 'native',
    economy_channel_id BIGINT,
    shop_channel_id BIGINT,
    staff_log_channel_id BIGINT,
    min_voice_seconds_to_claim BIGINT NOT NULL DEFAULT 60,
    min_messages_to_claim BIGINT NOT NULL DEFAULT 1,
    ignore_afk_channel BIGINT NOT NULL DEFAULT 1,
    ignore_bots BIGINT NOT NULL DEFAULT 1,
    count_voice_when_alone BIGINT NOT NULL DEFAULT 0,
    max_admin_grant_per_use BIGINT NOT NULL DEFAULT 100000,
    casino_max_bet BIGINT NOT NULL DEFAULT 1000,
    casino_daily_profit_limit BIGINT NOT NULL DEFAULT 5000,
    casino_min_bet_coin_flip BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_dice BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_slot BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_roulette BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_mascot_race BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_duel BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_blackjack BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_scratch_card BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_collective_race BIGINT NOT NULL DEFAULT 1,
    casino_min_bet_match_bet BIGINT NOT NULL DEFAULT 1,
    casino_limiters_enabled BIGINT NOT NULL DEFAULT 1,
    economy_manager_role_id BIGINT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_wallets (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    balance BIGINT NOT NULL DEFAULT 0,
    total_earned BIGINT NOT NULL DEFAULT 0,
    total_spent BIGINT NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS activity_claim_cursors (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    claimed_voice_seconds BIGINT NOT NULL DEFAULT 0,
    claimed_messages BIGINT NOT NULL DEFAULT 0,
    last_claimed_at TEXT,
    last_source TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS economy_reward_claims (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    reward_key TEXT NOT NULL,
    last_claimed_at TEXT NOT NULL,
    last_claim_date TEXT,
    claim_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, reward_key)
);

CREATE TABLE IF NOT EXISTS economy_transactions (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    actor_id BIGINT,
    type TEXT NOT NULL,
    amount BIGINT NOT NULL,
    balance_before BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    reason TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS native_message_stats (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    message_count BIGINT NOT NULL DEFAULT 0,
    last_message_at TEXT,
    PRIMARY KEY (guild_id, channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS native_voice_sessions (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds BIGINT,
    is_valid BIGINT NOT NULL DEFAULT 1,
    invalid_reason TEXT
);

CREATE TABLE IF NOT EXISTS reward_items (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    price BIGINT NOT NULL,
    stock_quantity BIGINT,
    stock_mode TEXT NOT NULL DEFAULT 'LIMITED',
    max_per_user BIGINT,
    role_id BIGINT,
    delivery_message TEXT,
    is_active BIGINT NOT NULL DEFAULT 1,
    created_by BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS reward_purchases (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    reward_id BIGINT NOT NULL REFERENCES reward_items(id),
    transaction_id BIGINT REFERENCES economy_transactions(id),
    price_paid BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'COMPLETED',
    delivery_status TEXT NOT NULL DEFAULT 'PENDING',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE TABLE IF NOT EXISTS reward_codes (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    reward_id BIGINT NOT NULL REFERENCES reward_items(id),
    code_encrypted TEXT NOT NULL,
    is_claimed BIGINT NOT NULL DEFAULT 0,
    claimed_by BIGINT,
    claimed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_user_id BIGINT,
    target_resource_id TEXT,
    before_data_json TEXT NOT NULL DEFAULT '{}',
    after_data_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_achievements (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    achievement_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    reward_points BIGINT NOT NULL DEFAULT 0,
    reward_points_customized BIGINT NOT NULL DEFAULT 0,
    badge_emoji TEXT,
    is_active BIGINT NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (guild_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS user_game_achievements (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    achievement_key TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, achievement_key),
    FOREIGN KEY (guild_id, achievement_key)
        REFERENCES game_achievements(guild_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS game_jackpots (
    guild_id BIGINT NOT NULL,
    jackpot_key TEXT NOT NULL,
    amount BIGINT NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, jackpot_key)
);

CREATE TABLE IF NOT EXISTS game_seasonal_settings (
    guild_id BIGINT PRIMARY KEY,
    theme TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collective_races (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT UNIQUE,
    stake BIGINT NOT NULL,
    status TEXT NOT NULL,
    opened_by BIGINT NOT NULL,
    opened_at TEXT NOT NULL,
    closes_at TEXT NOT NULL,
    winner TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS collective_race_bets (
    id BIGSERIAL PRIMARY KEY,
    race_id BIGINT NOT NULL REFERENCES collective_races(id) ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    mascot TEXT NOT NULL,
    stake BIGINT NOT NULL,
    potential_payout BIGINT NOT NULL,
    status TEXT NOT NULL,
    debit_transaction_id BIGINT,
    payout_transaction_id BIGINT,
    created_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE (race_id, user_id)
);

CREATE TABLE IF NOT EXISTS match_bet_matches (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    team_1 TEXT NOT NULL,
    team_2 TEXT NOT NULL,
    odd_team_1_bps BIGINT NOT NULL,
    odd_team_2_bps BIGINT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT UNIQUE,
    created_by BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    is_active BIGINT NOT NULL DEFAULT 1,
    resolved_winner TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS match_bet_tickets (
    id BIGSERIAL PRIMARY KEY,
    match_id BIGINT NOT NULL REFERENCES match_bet_matches(id) ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    team TEXT NOT NULL,
    team_name_snapshot TEXT NOT NULL,
    stake BIGINT NOT NULL,
    odd_bps BIGINT NOT NULL,
    potential_payout BIGINT NOT NULL,
    status TEXT NOT NULL,
    debit_transaction_id BIGINT,
    payout_transaction_id BIGINT,
    created_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS bolao_events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    prize TEXT NOT NULL,
    team_1 TEXT NOT NULL,
    team_2 TEXT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT UNIQUE,
    created_by BIGINT NOT NULL,
    receiver_user_id BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    is_active BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bolao_guesses (
    id BIGSERIAL PRIMARY KEY,
    bolao_id BIGINT NOT NULL REFERENCES bolao_events(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    score_team_1 BIGINT NOT NULL,
    score_team_2 BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (bolao_id, user_id)
);

CREATE TABLE IF NOT EXISTS forms (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    response_channel_id BIGINT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT UNIQUE,
    created_by BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    is_active BIGINT NOT NULL DEFAULT 1,
    questions_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS form_responses (
    id BIGSERIAL PRIMARY KEY,
    form_id BIGINT NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    answers_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (form_id, user_id)
);

CREATE TABLE IF NOT EXISTS giveaway_events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT UNIQUE,
    created_by BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    is_active BIGINT NOT NULL DEFAULT 1,
    max_redemptions BIGINT,
    total_codes BIGINT NOT NULL,
    notify_user_id BIGINT,
    embed_color BIGINT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS giveaway_codes (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES giveaway_events(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    reward_name TEXT,
    reward_amount BIGINT,
    is_claimed BIGINT NOT NULL DEFAULT 0,
    claimed_by BIGINT,
    claimed_at TEXT,
    UNIQUE (event_id, code)
);

CREATE TABLE IF NOT EXISTS giveaway_claims (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES giveaway_events(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    code_id BIGINT NOT NULL UNIQUE REFERENCES giveaway_codes(id) ON DELETE CASCADE,
    claimed_at TEXT NOT NULL,
    reward_amount BIGINT,
    reward_name TEXT
);

CREATE TABLE IF NOT EXISTS giveaway_user_tickets (
    event_id BIGINT NOT NULL REFERENCES giveaway_events(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    extra_tickets BIGINT NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_economy_transactions_guild_user_created
    ON economy_transactions(guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_economy_reward_claims_user
    ON economy_reward_claims(guild_id, user_id, reward_key);
CREATE INDEX IF NOT EXISTS idx_native_voice_sessions_guild_user
    ON native_voice_sessions(guild_id, user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_native_voice_sessions_open
    ON native_voice_sessions(guild_id, user_id, ended_at);
CREATE INDEX IF NOT EXISTS idx_native_message_stats_guild_user
    ON native_message_stats(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_reward_items_guild_active
    ON reward_items(guild_id, is_active, price);
CREATE INDEX IF NOT EXISTS idx_reward_purchases_guild_user_created
    ON reward_purchases(guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reward_purchases_reward_user
    ON reward_purchases(guild_id, reward_id, user_id);
CREATE INDEX IF NOT EXISTS idx_collective_races_open
    ON collective_races(guild_id, status, closes_at);
CREATE INDEX IF NOT EXISTS idx_collective_race_bets_race
    ON collective_race_bets(race_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_match_bet_matches_active
    ON match_bet_matches(guild_id, is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_match_bet_matches_message
    ON match_bet_matches(message_id);
CREATE INDEX IF NOT EXISTS idx_match_bet_tickets_match
    ON match_bet_tickets(match_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_match_bet_tickets_user
    ON match_bet_tickets(guild_id, user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bolao_events_active
    ON bolao_events(is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_bolao_events_message
    ON bolao_events(message_id);
CREATE INDEX IF NOT EXISTS idx_bolao_guesses_event_user
    ON bolao_guesses(bolao_id, user_id);
CREATE INDEX IF NOT EXISTS idx_bolao_guesses_winning
    ON bolao_guesses(bolao_id, score_team_1, score_team_2, created_at);
CREATE INDEX IF NOT EXISTS idx_forms_active
    ON forms(is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_forms_active_published
    ON forms(is_active, message_id, created_at);
CREATE INDEX IF NOT EXISTS idx_form_responses_form_user
    ON form_responses(form_id, user_id);
CREATE INDEX IF NOT EXISTS idx_giveaway_codes_event_claimed
    ON giveaway_codes(event_id, is_claimed);
CREATE INDEX IF NOT EXISTS idx_giveaway_claims_user_latest
    ON giveaway_claims(event_id, user_id, claimed_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_giveaway_claims_event_user
    ON giveaway_claims(event_id, user_id);
CREATE INDEX IF NOT EXISTS idx_giveaway_claims_event_reward
    ON giveaway_claims(event_id, reward_amount, reward_name);
CREATE INDEX IF NOT EXISTS idx_giveaway_tickets_event_user
    ON giveaway_user_tickets(event_id, user_id);
CREATE INDEX IF NOT EXISTS idx_giveaway_events_expires_at
    ON giveaway_events(is_active, expires_at);
CREATE INDEX IF NOT EXISTS idx_giveaway_events_active_created
    ON giveaway_events(is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_giveaway_events_active_published
    ON giveaway_events(is_active, message_id, created_at);
