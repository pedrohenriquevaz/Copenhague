from __future__ import annotations

import pytest

from app.integrations.network_logging import sanitize_url
from app.integrations.timeout_policy import DiscordOrchestratedTimeoutPolicy


def test_timeout_policy_respects_discord_ack_deadline() -> None:
    policy = DiscordOrchestratedTimeoutPolicy(
        interaction_ack_seconds=2.5,
        connect_seconds=3,
        request_seconds=15,
        max_retries=2,
    )

    assert policy.interaction_ack_seconds < 3
    assert policy.request_seconds >= policy.connect_seconds


def test_timeout_policy_rejects_ack_at_discord_deadline() -> None:
    with pytest.raises(ValueError, match="menor que 3"):
        DiscordOrchestratedTimeoutPolicy(interaction_ack_seconds=3)


def test_network_log_sanitizes_tokens_and_query_strings() -> None:
    sanitized = sanitize_url(
        "https://discord.com/api/v10/webhooks/123/secret-token/messages/@original"
        "?access_token=secret"
    )

    assert sanitized == (
        "https://discord.com/api/v10/webhooks/123/<redacted>/messages/@original"
    )
    assert "secret" not in sanitized
