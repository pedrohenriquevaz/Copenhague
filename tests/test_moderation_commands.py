from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import discord
import pytest

from app.cogs.moderation import moderation as moderation_module
from app.cogs.moderation.moderation import ModerationCog
from app.models.moderation import (
    ModerationActionType,
    ModerationCase,
    ModerationCaseCreate,
    ModerationCaseStatus,
    ModerationSettings,
)
from app.services.moderation_service import ModerationService


class FakeModerationRepository:
    def __init__(self, guild_id: int, authorized_role_id: int) -> None:
        self.settings = ModerationSettings(
            guild_id=guild_id,
            authorized_role_ids=(authorized_role_id,),
        )
        self.cases: list[ModerationCase] = []
        self.fail_create = False

    async def get_settings(self, guild_id: int) -> ModerationSettings:
        if guild_id == self.settings.guild_id:
            return self.settings
        return ModerationSettings(guild_id)

    async def add_authorized_role(self, guild_id: int, role_id: int) -> bool:
        raise NotImplementedError

    async def remove_authorized_role(self, guild_id: int, role_id: int) -> bool:
        raise NotImplementedError

    async def set_log_channel(
        self,
        guild_id: int,
        channel_id: int | None,
    ) -> ModerationSettings:
        raise NotImplementedError

    async def create_case(self, case: ModerationCaseCreate) -> ModerationCase:
        if self.fail_create:
            raise RuntimeError("database unavailable")
        created = ModerationCase(
            id=len(self.cases) + 1,
            guild_id=case.guild_id,
            action_type=case.action_type,
            target_user_id=case.target_user_id,
            moderator_user_id=case.moderator_user_id,
            reason=case.reason,
            created_at=datetime.now(UTC),
            duration=case.duration,
            status=case.status,
            origin=case.origin,
            metadata=dict(case.metadata),
        )
        self.cases.append(created)
        return created

    async def get_case(self, guild_id: int, case_id: int) -> ModerationCase | None:
        return next(
            (
                case
                for case in self.cases
                if case.guild_id == guild_id and case.id == case_id
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class _FakeRole:
    id: int
    position: int


class _FakeGuild:
    def __init__(self, guild_id: int = 1) -> None:
        self.id = guild_id
        self.name = "Servidor de testes"
        self.owner_id = 999_999
        self.me: _FakeMember | None = None

    @staticmethod
    def get_channel(channel_id: int) -> None:
        del channel_id
        return None


class _FakeMember:
    def __init__(
        self,
        guild: _FakeGuild,
        user_id: int,
        *,
        role_ids: tuple[int, ...],
        top_role_id: int,
        top_role_position: int,
        permissions: frozenset[str] = frozenset(),
    ) -> None:
        self.guild = guild
        self.id = user_id
        self.roles = [
            _FakeRole(role_id, top_role_position if role_id == top_role_id else 1)
            for role_id in role_ids
        ]
        self.top_role = _FakeRole(top_role_id, top_role_position)
        self.guild_permissions = discord.Permissions(
            **{permission: True for permission in permissions}
        )
        self.mention = f"<@{user_id}>"
        self.ban = AsyncMock()
        self.kick = AsyncMock()
        self.timeout = AsyncMock()
        self.send = AsyncMock()

    def __str__(self) -> str:
        return f"member-{self.id}"


class _FakeInteraction:
    def __init__(self, guild: _FakeGuild, user: _FakeMember) -> None:
        self.guild = guild
        self.user = user
        self.response = SimpleNamespace(
            defer=AsyncMock(),
            send_message=AsyncMock(),
        )
        self.followup = SimpleNamespace(send=AsyncMock())


@dataclass(slots=True)
class _CommandContext:
    repository: FakeModerationRepository
    cog: ModerationCog
    interaction: _FakeInteraction
    actor: _FakeMember
    target: _FakeMember


@pytest.fixture(autouse=True)
def _use_fake_discord_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(moderation_module.discord, "Member", _FakeMember)


def _command_context(permission: str | None) -> _CommandContext:
    guild = _FakeGuild()
    actor_role_id = 100
    actor_permissions = frozenset({permission}) if permission else frozenset()
    actor = _FakeMember(
        guild,
        10,
        role_ids=(guild.id, actor_role_id),
        top_role_id=actor_role_id,
        top_role_position=20,
        permissions=actor_permissions,
    )
    target = _FakeMember(
        guild,
        20,
        role_ids=(guild.id, 200),
        top_role_id=200,
        top_role_position=5,
    )
    bot = _FakeMember(
        guild,
        30,
        role_ids=(guild.id, 300),
        top_role_id=300,
        top_role_position=30,
        permissions=actor_permissions,
    )
    guild.me = bot
    repository = FakeModerationRepository(guild.id, actor_role_id)
    service = ModerationService(repository)
    cog = ModerationCog(SimpleNamespace(), service)  # type: ignore[arg-type]
    return _CommandContext(
        repository=repository,
        cog=cog,
        interaction=_FakeInteraction(guild, actor),
        actor=actor,
        target=target,
    )


def _forbidden() -> discord.Forbidden:
    response = SimpleNamespace(status=403, reason="Forbidden")
    return discord.Forbidden(
        response,  # type: ignore[arg-type]
        {"message": "Missing Permissions", "code": 50_013},
    )


def _last_followup_message(interaction: _FakeInteraction) -> str:
    return str(interaction.followup.send.await_args.args[0])


def test_command_surface_exposes_kick_mute_and_warn_without_timeout() -> None:
    commands = {
        command.name: command for command in ModerationCog.__cog_app_commands__
    }

    assert {"kick", "mute", "warn"}.issubset(commands)
    assert "timeout" not in commands
    assert commands["kick"].default_permissions.kick_members
    assert commands["mute"].default_permissions.moderate_members
    assert commands["warn"].default_permissions.moderate_members

    mute_parameters = {
        parameter.name: parameter for parameter in commands["mute"].parameters
    }
    assert mute_parameters["duration"].min_value == 1
    assert mute_parameters["duration"].max_value == 40_320


async def test_kick_executes_discord_action_and_persists_completed_case() -> None:
    context = _command_context("kick_members")

    await ModerationCog.kick.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        "  spam   repetido ",
    )

    context.target.kick.assert_awaited_once()
    audit_reason = context.target.kick.await_args.kwargs["reason"]
    assert len(audit_reason) <= 512
    assert audit_reason.endswith(str(context.actor.id))
    assert len(context.repository.cases) == 1
    case = context.repository.cases[0]
    assert case.action_type is ModerationActionType.KICK
    assert case.status is ModerationCaseStatus.COMPLETED
    assert case.reason == "spam repetido"
    assert case.duration is None
    assert case.target_user_id == context.target.id
    assert case.moderator_user_id == context.actor.id
    assert "sucesso" in _last_followup_message(context.interaction).casefold()


async def test_mute_uses_native_timeout_and_persists_duration() -> None:
    context = _command_context("moderate_members")

    await ModerationCog.mute.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        90,
        "comportamento inadequado",
    )

    context.target.timeout.assert_awaited_once()
    assert context.target.timeout.await_args.args[0] == timedelta(minutes=90)
    case = context.repository.cases[0]
    assert case.action_type is ModerationActionType.MUTE
    assert case.status is ModerationCaseStatus.COMPLETED
    assert case.duration == timedelta(minutes=90)
    assert "1 hora, 30 minutos" in _last_followup_message(context.interaction)


async def test_warn_persists_case_and_delivers_best_effort_dm() -> None:
    context = _command_context("moderate_members")

    await ModerationCog.warn.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        "primeira advertência",
    )

    context.target.send.assert_awaited_once()
    case = context.repository.cases[0]
    assert case.action_type is ModerationActionType.WARN
    assert case.status is ModerationCaseStatus.COMPLETED
    assert case.duration is None
    assert case.metadata["notification_channel"] == "direct_message"
    assert "notificado" in _last_followup_message(context.interaction).casefold()


@pytest.mark.parametrize("duration", [-1, 0, 40_321])
async def test_mute_rejects_invalid_duration_in_callback(duration: int) -> None:
    context = _command_context("moderate_members")

    await ModerationCog.mute.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        duration,
        "motivo",
    )

    context.interaction.response.send_message.assert_awaited_once()
    context.interaction.response.defer.assert_not_awaited()
    context.target.timeout.assert_not_awaited()
    assert context.repository.cases == []


@pytest.mark.parametrize(
    ("command_name", "permission", "discord_method"),
    [
        ("kick", "kick_members", "kick"),
        ("mute", "moderate_members", "timeout"),
    ],
)
async def test_discord_forbidden_does_not_persist_completed_case(
    command_name: str,
    permission: str,
    discord_method: str,
) -> None:
    context = _command_context(permission)
    api_call: AsyncMock = getattr(context.target, discord_method)
    api_call.side_effect = _forbidden()

    command = getattr(ModerationCog, command_name)
    arguments: tuple[Any, ...] = (
        (context.target, 15, "motivo")
        if command_name == "mute"
        else (context.target, "motivo")
    )
    await command.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        *arguments,
    )

    api_call.assert_awaited_once()
    assert context.repository.cases == []
    assert "permiss" in _last_followup_message(context.interaction).casefold()


async def test_persistence_failure_is_reported_after_kick_was_executed() -> None:
    context = _command_context("kick_members")
    context.repository.fail_create = True

    await ModerationCog.kick.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        "motivo",
    )

    context.target.kick.assert_awaited_once()
    assert context.repository.cases == []
    message = _last_followup_message(context.interaction).casefold()
    assert "foi executada" in message
    assert "registrar o caso" in message


async def test_warn_dm_forbidden_preserves_case_and_reports_non_delivery() -> None:
    context = _command_context("moderate_members")
    context.target.send.side_effect = _forbidden()

    await ModerationCog.warn.callback(
        context.cog,
        context.interaction,  # type: ignore[arg-type]
        context.target,  # type: ignore[arg-type]
        "advertência persistente",
    )

    context.target.send.assert_awaited_once()
    assert len(context.repository.cases) == 1
    assert context.repository.cases[0].action_type is ModerationActionType.WARN
    message = _last_followup_message(context.interaction).casefold()
    assert "registrada" in message
    assert "não foi entregue" in message
