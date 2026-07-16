ALTER TABLE moderation_cases
    DROP CONSTRAINT IF EXISTS moderation_cases_action_type_valid;

UPDATE moderation_cases
SET action_type = 'MUTE'
WHERE action_type = 'TIMEOUT';

ALTER TABLE moderation_cases
    ADD CONSTRAINT moderation_cases_action_type_valid
        CHECK (
            action_type IN ('BAN', 'KICK', 'MUTE', 'WARN', 'PURGE', 'CONFIGURATION')
        ) NOT VALID;

ALTER TABLE moderation_cases
    VALIDATE CONSTRAINT moderation_cases_action_type_valid;
