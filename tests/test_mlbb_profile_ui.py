from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from discord.ext import commands

from app.models.mlbb import (
    MlbbAchievement,
    MlbbAchievementsSnapshot,
    MlbbProfileSection,
    MlbbProfileSnapshot,
    MlbbProfileVisibility,
)
from app.ui.mlbb_profile_view import (
    MlbbProfileView,
    build_mlbb_achievements_embed,
    build_mlbb_profile_embed,
)
from app.utils.mlbb_formatters import NOT_AVAILABLE

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


class DummyBot:
    mlbb_profile_service = object()


def test_profile_embed_masks_ids_handles_nulls_and_has_attribution() -> None:
    snapshot = MlbbProfileSnapshot(
        discord_user_id=20,
        role_id=123456789,
        zone_id=1234,
        player_name="Jogador",
        avatar_url=None,
        level=None,
        current_rank=NOT_AVAILABLE,
        highest_rank="Rank não mapeado (código 9999)",
        matches=0,
        wins=0,
        win_rate=0.0,
        mvp_count=0,
        country_code=None,
        visibility=MlbbProfileVisibility.GUILD,
        updated_at=NOW,
        from_cache=True,
    )

    embed = build_mlbb_profile_embed(snapshot)
    rendered = str(embed.to_dict())

    assert "123456789" not in rendered
    assert "1234)" not in rendered
    assert NOT_AVAILABLE in rendered
    assert "comunitária e não oficial" in cast(str, embed.footer.text)
    assert "cache" in cast(str, embed.footer.text)
    assert len(embed) <= 6_000
    assert "jwt" not in rendered.lower()
    assert "token" not in rendered.lower()


def test_achievements_embed_keeps_hero_name_and_image() -> None:
    snapshot = MlbbAchievementsSnapshot(
        discord_user_id=20,
        player_name="Jogador",
        avatar_url=None,
        longest_win_streak=4,
        game_time_hours=12.25,
        average_score=7.62,
        highlights=(
            MlbbAchievement(
                kind="HIGHEST_KILLS",
                value=24,
                occurred_at=None,
                hero_name="Herói Teste",
                hero_image_url="https://cdn.example.test/hero.png",
            ),
        ),
        visibility=MlbbProfileVisibility.GUILD,
        updated_at=NOW,
        from_cache=False,
    )

    embed = build_mlbb_achievements_embed(snapshot)
    rendered = str(embed.to_dict())

    assert "Herói Teste" in rendered
    assert "https://cdn.example.test/hero.png" in rendered
    assert "12h 15min" in rendered
    assert "7,62" in rendered
    assert len(embed) <= 6_000


def test_profile_view_is_dynamic_and_exposes_only_phase_two_actions() -> None:
    view = MlbbProfileView(
        cast(commands.Bot, DummyBot()),
        requester_user_id=20,
        target_user_id=20,
        section=MlbbProfileSection.PROFILE,
    )

    assert view.timeout == 300
    assert {item.label for item in view.children} == {
        "Perfil",
        "Conquistas",
        "Atualizar",
        "Histórico",
        "Heróis",
    }
    assert all(item.custom_id is not None for item in view.children)
