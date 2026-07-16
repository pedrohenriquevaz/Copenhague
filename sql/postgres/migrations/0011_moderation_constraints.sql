ALTER TABLE moderation_settings
    ADD CONSTRAINT moderation_settings_guild_id_positive
        CHECK (guild_id > 0) NOT VALID,
    ADD CONSTRAINT moderation_settings_log_channel_id_positive
        CHECK (log_channel_id IS NULL OR log_channel_id > 0) NOT VALID;

ALTER TABLE moderation_authorized_roles
    ADD CONSTRAINT moderation_authorized_roles_role_id_positive
        CHECK (role_id > 0) NOT VALID;

-- A 0009 aceitava zero; semanticamente isso representa ausencia de duracao.
UPDATE moderation_cases
SET duration_seconds = NULL
WHERE duration_seconds = 0;

ALTER TABLE moderation_cases
    DROP CONSTRAINT IF EXISTS moderation_cases_duration_seconds_check;

ALTER TABLE moderation_cases
    ADD CONSTRAINT moderation_cases_guild_id_positive
        CHECK (guild_id > 0) NOT VALID,
    ADD CONSTRAINT moderation_cases_action_type_valid
        CHECK (
            action_type IN (
                'BAN', 'KICK', 'TIMEOUT', 'WARN', 'PURGE', 'CONFIGURATION'
            )
        ) NOT VALID,
    ADD CONSTRAINT moderation_cases_target_user_id_positive
        CHECK (target_user_id > 0) NOT VALID,
    ADD CONSTRAINT moderation_cases_moderator_user_id_positive
        CHECK (moderator_user_id > 0) NOT VALID,
    ADD CONSTRAINT moderation_cases_reason_not_blank
        CHECK (BTRIM(reason) <> '') NOT VALID,
    ADD CONSTRAINT moderation_cases_duration_seconds_positive
        CHECK (duration_seconds IS NULL OR duration_seconds > 0) NOT VALID,
    ADD CONSTRAINT moderation_cases_status_valid
        CHECK (status IN ('OPEN', 'COMPLETED', 'REVOKED', 'FAILED')) NOT VALID,
    ADD CONSTRAINT moderation_cases_origin_valid
        CHECK (origin IN ('COMMAND', 'AUTOMATION', 'API')) NOT VALID,
    ADD CONSTRAINT moderation_cases_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object') NOT VALID;

ALTER TABLE moderation_settings
    VALIDATE CONSTRAINT moderation_settings_guild_id_positive;
ALTER TABLE moderation_settings
    VALIDATE CONSTRAINT moderation_settings_log_channel_id_positive;
ALTER TABLE moderation_authorized_roles
    VALIDATE CONSTRAINT moderation_authorized_roles_role_id_positive;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_guild_id_positive;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_action_type_valid;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_target_user_id_positive;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_moderator_user_id_positive;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_reason_not_blank;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_duration_seconds_positive;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_status_valid;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_origin_valid;
ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_metadata_object;
