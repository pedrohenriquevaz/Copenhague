from __future__ import annotations

from typing import Any, cast

import pytest
from discord.ext import commands

from app.cogs.mlbb.account import setup
from app.ui.mlbb_panel import MlbbPanelView


class DummyBot:
    def __init__(self) -> None:
        self.mlbb_auth_service = object()
        self.mlbb_profile_service = object()
        self.cogs: list[object] = []
        self.views: list[object] = []

    async def add_cog(self, cog: object) -> None:
        self.cogs.append(cog)

    def add_view(self, view: object) -> None:
        self.views.append(view)


@pytest.mark.asyncio
async def test_mlbb_panel_has_stable_persistent_custom_ids() -> None:
    bot = cast(commands.Bot, DummyBot())
    view = MlbbPanelView(bot)

    assert view.timeout is None
    assert {item.custom_id for item in view.children} == {
        "mlbb:account:link",
        "mlbb:account:manage",
    }


@pytest.mark.asyncio
async def test_mlbb_persistent_view_is_registered_during_cog_setup() -> None:
    bot = DummyBot()

    await setup(cast(Any, bot))

    assert len(bot.cogs) == 1
    assert len(bot.views) == 1
    assert isinstance(bot.views[0], MlbbPanelView)
    assert cast(MlbbPanelView, bot.views[0]).timeout is None
    cog = bot.cogs[0]
    group = cog.__cog_app_commands_group__
    assert group.name == "mlbb"
    assert {command.name for command in group.commands} == {
        "vincular",
        "confirmar",
        "conta",
        "desvincular",
        "reautenticar",
        "perfil",
        "conquistas",
        "privacidade",
        "painel_publicar",
    }
