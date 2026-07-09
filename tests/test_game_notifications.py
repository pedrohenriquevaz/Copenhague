from __future__ import annotations

from datetime import UTC, datetime

from app.models.guild_settings import GuildEconomySettings
from app.ui.game_notifications import announce_game_result_to_channel


class FakeChannel:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


async def test_game_notifications_announce_wins_and_expressive_losses() -> None:
    settings = _settings()
    channel = FakeChannel()

    await announce_game_result_to_channel(
        channel,
        user_id=10,
        game_name="Roleta",
        stake=100,
        payout=200,
        settings=settings,
    )
    await announce_game_result_to_channel(
        channel,
        user_id=10,
        game_name="Roleta",
        stake=500,
        payout=0,
        settings=settings,
    )
    await announce_game_result_to_channel(
        channel,
        user_id=10,
        game_name="Roleta",
        stake=501,
        payout=0,
        settings=settings,
    )

    assert len(channel.messages) == 2
    assert "ganhar" in channel.messages[0]
    assert "perder" in channel.messages[1]
    assert "501 pontos" in channel.messages[1]


def _settings() -> GuildEconomySettings:
    now = datetime.now(UTC)
    return GuildEconomySettings(
        guild_id=1,
        currency_name="pontos",
        voice_points_per_minute=2,
        message_points=1,
        activity_provider="native",
        economy_channel_id=None,
        shop_channel_id=None,
        staff_log_channel_id=None,
        min_voice_seconds_to_claim=60,
        min_messages_to_claim=1,
        ignore_afk_channel=True,
        ignore_bots=True,
        count_voice_when_alone=False,
        max_admin_grant_per_use=100000,
        casino_max_bet=1000,
        casino_daily_profit_limit=5000,
        economy_manager_role_id=None,
        created_at=now,
        updated_at=now,
    )
