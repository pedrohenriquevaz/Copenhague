from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest

from app.cogs.moderation.context import moderation_principal
from app.models.giveaway import utc_now
from app.models.moderation import (
    ModerationActionType,
    ModerationCase,
    ModerationCaseCreate,
    ModerationLogChannelReference,
    ModerationPrincipal,
    ModerationRoleReference,
    ModerationSettings,
)
from app.services.moderation_service import (
    ModerationAuthorizationError,
    ModerationService,
    ModerationValidationError,
)


class FakeModerationRepository:
    def __init__(self) -> None:
        self.settings: dict[int, ModerationSettings] = {}
        self.cases: dict[tuple[int, int], ModerationCase] = {}

    async def get_settings(self, guild_id: int) -> ModerationSettings:
        return self.settings.get(guild_id, ModerationSettings(guild_id))

    async def add_authorized_role(self, guild_id: int, role_id: int) -> bool:
        current = await self.get_settings(guild_id)
        if role_id in current.authorized_role_ids:
            return False
        self.settings[guild_id] = replace(
            current, authorized_role_ids=(*current.authorized_role_ids, role_id)
        )
        return True

    async def remove_authorized_role(self, guild_id: int, role_id: int) -> bool:
        current = await self.get_settings(guild_id)
        if role_id not in current.authorized_role_ids:
            return False
        self.settings[guild_id] = replace(
            current,
            authorized_role_ids=tuple(
                item for item in current.authorized_role_ids if item != role_id
            ),
        )
        return True

    async def set_log_channel(
        self, guild_id: int, channel_id: int | None
    ) -> ModerationSettings:
        updated = replace(await self.get_settings(guild_id), log_channel_id=channel_id)
        self.settings[guild_id] = updated
        return updated

    async def create_case(self, case: ModerationCaseCreate) -> ModerationCase:
        created = ModerationCase(
            id=len(self.cases) + 1,
            guild_id=case.guild_id,
            action_type=case.action_type,
            target_user_id=case.target_user_id,
            moderator_user_id=case.moderator_user_id,
            reason=case.reason,
            created_at=utc_now(),
            duration=case.duration,
            status=case.status,
            origin=case.origin,
            metadata=dict(case.metadata),
        )
        self.cases[(created.guild_id, created.id)] = created
        return created

    async def get_case(self, guild_id: int, case_id: int) -> ModerationCase | None:
        return self.cases.get((guild_id, case_id))


def principal(
    user_id: int,
    *,
    roles: set[int] | None = None,
    position: int = 10,
    top_role_id: int = 100,
    permissions: set[str] | None = None,
    owner: bool = False,
    administrator: bool = False,
    guild_id: int = 1,
) -> ModerationPrincipal:
    return ModerationPrincipal(
        guild_id=guild_id,
        user_id=user_id,
        role_ids=frozenset(roles or set()),
        top_role_position=position,
        top_role_id=top_role_id,
        native_permissions=frozenset(permissions or set()),
        is_owner=owner,
        is_administrator=administrator,
    )


def test_channel_permissions_do_not_fall_back_when_all_are_denied() -> None:
    member = SimpleNamespace(
        id=10,
        guild=SimpleNamespace(id=1, owner_id=99),
        roles=[SimpleNamespace(id=1)],
        top_role=SimpleNamespace(id=1, position=0),
        guild_permissions=discord.Permissions(administrator=True),
    )

    snapshot = moderation_principal(member, permissions=discord.Permissions.none())

    assert snapshot.native_permissions == frozenset()
    assert snapshot.is_administrator is False


async def test_owner_and_administrator_can_bootstrap_configuration() -> None:
    service = ModerationService(FakeModerationRepository())

    assert await service.add_authorized_role(
        1, principal(1, owner=True), ModerationRoleReference(1, 100)
    )
    assert await service.add_authorized_role(
        1, principal(2, administrator=True), ModerationRoleReference(1, 200)
    )


async def test_configured_role_still_requires_native_permission() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)

    with pytest.raises(ModerationAuthorizationError, match="Gerenciar Servidor"):
        await service.authorize_configuration(1, principal(2, roles={100}))


async def test_configuration_rejects_actor_from_another_guild() -> None:
    service = ModerationService(FakeModerationRepository())

    with pytest.raises(ModerationValidationError, match="outro servidor"):
        await service.authorize_configuration(1, principal(1, owner=True, guild_id=2))


async def test_configuration_is_isolated_between_guilds() -> None:
    repository = FakeModerationRepository()
    service = ModerationService(repository)
    owner = principal(1, owner=True)

    await service.add_authorized_role(1, owner, ModerationRoleReference(1, 100))
    await service.set_log_channel(
        1, owner, ModerationLogChannelReference(1, 500, True, True, True)
    )

    assert (await service.get_settings(1)).authorized_role_ids == (100,)
    assert (await service.get_settings(1)).log_channel_id == 500
    assert (await service.get_settings(2)).authorized_role_ids == ()
    assert (await service.get_settings(2)).log_channel_id is None


async def test_action_rejects_equal_or_higher_target_role() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)
    actor = principal(1, roles={100}, position=10, permissions={"ban_members"})
    bot = principal(999, position=20, permissions={"ban_members"})

    with pytest.raises(ModerationAuthorizationError, match="igual ou superior"):
        await service.authorize_action(
            1,
            actor,
            principal(2, position=10),
            bot,
            action_type=ModerationActionType.BAN,
        )


async def test_discord_role_id_breaks_equal_position_ties() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)

    await service.authorize_action(
        1,
        principal(
            1,
            roles={100},
            position=10,
            top_role_id=100,
            permissions={"ban_members"},
        ),
        principal(2, position=10, top_role_id=200),
        principal(999, position=20, permissions={"ban_members"}),
        action_type=ModerationActionType.BAN,
    )


async def test_action_rejects_server_owner_and_bot_hierarchy() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)
    actor = principal(1, roles={100}, position=20, permissions={"ban_members"})
    bot = principal(999, position=15, permissions={"ban_members"})

    with pytest.raises(ModerationAuthorizationError, match="proprietario"):
        await service.authorize_action(
            1,
            actor,
            principal(2, position=1, owner=True),
            bot,
            action_type=ModerationActionType.BAN,
        )
    with pytest.raises(ModerationAuthorizationError, match="cargo do bot"):
        await service.authorize_action(
            1,
            actor,
            principal(3, position=15),
            bot,
            action_type=ModerationActionType.BAN,
        )


async def test_action_rechecks_bot_and_actor_native_permissions() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)
    target = principal(3, position=1)

    with pytest.raises(ModerationAuthorizationError, match="Voce nao possui"):
        await service.authorize_action(
            1,
            principal(1, roles={100}, position=10),
            target,
            principal(999, position=20, permissions={"ban_members"}),
            action_type=ModerationActionType.BAN,
        )
    with pytest.raises(ModerationAuthorizationError, match="bot nao possui"):
        await service.authorize_action(
            1,
            principal(1, roles={100}, position=10, permissions={"ban_members"}),
            target,
            principal(999, position=20),
            action_type=ModerationActionType.BAN,
        )


async def test_owner_bypasses_actor_hierarchy_but_not_bot_hierarchy() -> None:
    service = ModerationService(FakeModerationRepository())

    await service.authorize_action(
        1,
        principal(1, position=1, owner=True),
        principal(2, position=50),
        principal(999, position=60, permissions={"ban_members"}),
        action_type=ModerationActionType.BAN,
    )


@pytest.mark.parametrize("participant", ["actor", "target", "bot"])
async def test_action_rejects_cross_guild_principals(participant: str) -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)
    actor = principal(1, roles={100}, position=20, permissions={"ban_members"})
    target = principal(2, position=1)
    bot = principal(999, position=30, permissions={"ban_members"})
    if participant == "actor":
        actor = replace(actor, guild_id=2)
    elif participant == "target":
        target = replace(target, guild_id=2)
    else:
        bot = replace(bot, guild_id=2)

    with pytest.raises(ModerationValidationError, match="outro servidor"):
        await service.authorize_action(
            1, actor, target, bot, action_type=ModerationActionType.BAN
        )


async def test_administrator_does_not_bypass_target_hierarchy() -> None:
    service = ModerationService(FakeModerationRepository())
    with pytest.raises(ModerationAuthorizationError, match="igual ou superior"):
        await service.authorize_action(
            1,
            principal(1, administrator=True, position=10),
            principal(2, position=11),
            principal(999, administrator=True, position=20),
            action_type=ModerationActionType.BAN,
        )


async def test_mute_rejects_administrator_target() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)

    with pytest.raises(ModerationAuthorizationError, match="receber mute"):
        await service.authorize_action(
            1,
            principal(
                1,
                roles={100},
                position=20,
                permissions={"moderate_members"},
            ),
            principal(2, position=10, administrator=True),
            principal(999, position=30, permissions={"moderate_members"}),
            action_type=ModerationActionType.MUTE,
        )


async def test_warn_does_not_require_native_permission_from_bot() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)

    await service.authorize_action(
        1,
        principal(
            1,
            roles={100},
            position=20,
            permissions={"moderate_members"},
        ),
        principal(2, position=10),
        principal(999, position=30),
        action_type=ModerationActionType.WARN,
    )


async def test_service_rejects_everyone_and_cross_guild_channel() -> None:
    service = ModerationService(FakeModerationRepository())
    owner = principal(1, owner=True)
    with pytest.raises(ModerationValidationError, match="@everyone"):
        await service.add_authorized_role(
            1, owner, ModerationRoleReference(1, 1, is_default=True)
        )
    with pytest.raises(ModerationValidationError, match="mesmo servidor"):
        await service.set_log_channel(
            1, owner, ModerationLogChannelReference(2, 500, True, True, True)
        )


async def test_service_rejects_log_channel_without_embed_permission() -> None:
    service = ModerationService(FakeModerationRepository())

    with pytest.raises(ModerationAuthorizationError, match="inserir links"):
        await service.set_log_channel(
            1,
            principal(1, owner=True),
            ModerationLogChannelReference(1, 500, True, True, False),
        )


async def test_purge_uses_central_native_permission_policy() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)
    with pytest.raises(ModerationAuthorizationError, match="permissao nativa"):
        await service.authorize_action(
            1,
            principal(1, roles={100}, permissions={"ban_members"}),
            None,
            principal(999, permissions={"manage_messages"}),
            action_type=ModerationActionType.PURGE,
        )


async def test_purge_requires_bot_read_history_permission() -> None:
    repository = FakeModerationRepository()
    repository.settings[1] = ModerationSettings(1, (100,))
    service = ModerationService(repository)

    with pytest.raises(ModerationAuthorizationError, match="bot nao possui"):
        await service.authorize_action(
            1,
            principal(1, roles={100}, permissions={"manage_messages"}),
            None,
            principal(
                999,
                permissions={"view_channel", "manage_messages"},
            ),
            action_type=ModerationActionType.PURGE,
        )


async def test_case_validation_and_duration_normalization() -> None:
    service = ModerationService(FakeModerationRepository())
    with pytest.raises(ModerationValidationError, match="inteiro positivo"):
        await service.get_case(1, True)
    with pytest.raises(ModerationValidationError, match="motivo"):
        await service.create_case(
            ModerationCaseCreate(1, ModerationActionType.BAN, 2, 1, "   ")
        )
    created = await service.create_case(
        ModerationCaseCreate(
            1,
            ModerationActionType.MUTE,
            2,
            1,
            "  motivo   normalizado ",
            duration=timedelta(seconds=60, microseconds=900),
        )
    )
    assert created.reason == "motivo normalizado"
    assert created.duration == timedelta(seconds=60)

    assert service.normalize_mute_duration(1) == timedelta(minutes=1)
    assert service.normalize_mute_duration(40_320) == timedelta(days=28)
    with pytest.raises(ModerationValidationError, match="entre 1 minuto"):
        service.normalize_mute_duration(0)
    with pytest.raises(ModerationValidationError, match="entre 1 minuto"):
        service.normalize_mute_duration(40_321)
    with pytest.raises(ModerationValidationError, match="minutos inteiros"):
        service.normalize_mute_duration(True)

    with pytest.raises(ModerationValidationError, match="Somente casos de mute"):
        await service.create_case(
            ModerationCaseCreate(
                1,
                ModerationActionType.BAN,
                2,
                1,
                "motivo",
                duration=timedelta(minutes=1),
            )
        )
    with pytest.raises(ModerationValidationError, match="passar de 28 dias"):
        await service.create_case(
            ModerationCaseCreate(
                1,
                ModerationActionType.MUTE,
                2,
                1,
                "motivo",
                duration=timedelta(days=28, microseconds=1),
            )
        )

    with pytest.raises(ModerationValidationError, match="objeto JSON"):
        await service.create_case(
            replace(
                ModerationCaseCreate(1, ModerationActionType.WARN, 2, 1, "motivo"),
                metadata=[],  # type: ignore[arg-type]
            )
        )
    with pytest.raises(ModerationValidationError, match="serializaveis"):
        await service.create_case(
            ModerationCaseCreate(
                1,
                ModerationActionType.WARN,
                2,
                1,
                "motivo",
                metadata={"score": float("nan")},
            )
        )
