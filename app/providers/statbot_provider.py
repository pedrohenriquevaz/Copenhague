from __future__ import annotations

from app.models.activity import ActivityStats


class StatbotProvider:
    """Provider reservado para integracao futura com Statbot."""

    source = "statbot"

    async def get_user_stats(self, guild_id: int, user_id: int) -> ActivityStats:
        raise RuntimeError(
            "StatbotProvider ainda nao esta configurado. Use o provider nativo."
        )
