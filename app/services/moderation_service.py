from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import timedelta

from app.models.moderation import (
    ModerationActionType,
    ModerationCase,
    ModerationCaseCreate,
    ModerationLogChannelReference,
    ModerationPrincipal,
    ModerationRoleReference,
    ModerationSettings,
)
from app.repositories.moderation_protocol import ModerationRepositoryProtocol

logger = logging.getLogger(__name__)

MAX_MUTE_DURATION_MINUTES = 28 * 24 * 60
MAX_MUTE_DURATION = timedelta(minutes=MAX_MUTE_DURATION_MINUTES)


@dataclass(frozen=True, slots=True)
class ModerationActionPolicy:
    actor_permissions: frozenset[str]
    bot_permissions: frozenset[str]
    requires_target: bool


MODERATION_ACTION_POLICIES: dict[ModerationActionType, ModerationActionPolicy] = {
    ModerationActionType.BAN: ModerationActionPolicy(
        frozenset({"ban_members"}), frozenset({"ban_members"}), True
    ),
    ModerationActionType.KICK: ModerationActionPolicy(
        frozenset({"kick_members"}), frozenset({"kick_members"}), True
    ),
    ModerationActionType.MUTE: ModerationActionPolicy(
        frozenset({"moderate_members"}), frozenset({"moderate_members"}), True
    ),
    ModerationActionType.WARN: ModerationActionPolicy(
        frozenset({"moderate_members"}), frozenset(), True
    ),
    ModerationActionType.PURGE: ModerationActionPolicy(
        frozenset({"manage_messages"}),
        frozenset({"view_channel", "read_message_history", "manage_messages"}),
        False,
    ),
}


class ModerationAuthorizationError(PermissionError):
    """Falha de autorizacao com mensagem segura para o usuario."""


class ModerationValidationError(ValueError):
    """Dados invalidos para configuracao ou caso de moderacao."""


class ModerationService:
    """Configuracao e autorizacao de moderacao, independente dos cogs."""

    def __init__(self, repository: ModerationRepositoryProtocol) -> None:
        self._repository = repository

    async def get_settings(self, guild_id: int) -> ModerationSettings:
        self._validate_discord_id(guild_id, "guild")
        return await self._repository.get_settings(guild_id)

    async def get_case(self, guild_id: int, case_id: int) -> ModerationCase | None:
        self._validate_discord_id(guild_id, "guild")
        self._validate_discord_id(case_id, "caso")
        return await self._repository.get_case(guild_id, case_id)

    async def create_case(self, case: ModerationCaseCreate) -> ModerationCase:
        self._validate_discord_id(case.guild_id, "guild")
        self._validate_discord_id(case.target_user_id, "usuario afetado")
        self._validate_discord_id(case.moderator_user_id, "moderador")
        reason = self.normalize_case_reason(case.reason)
        if (
            case.action_type is ModerationActionType.MUTE
            and case.duration is not None
            and case.duration > MAX_MUTE_DURATION
        ):
            raise ModerationValidationError(
                "A duracao do mute nao pode passar de 28 dias."
            )
        duration = self._normalize_duration(case.duration)
        if case.action_type is ModerationActionType.MUTE:
            if duration is None:
                raise ModerationValidationError("A duracao do mute e obrigatoria.")
        elif duration is not None:
            raise ModerationValidationError(
                "Somente casos de mute podem possuir duracao."
            )
        if not isinstance(case.metadata, dict):
            raise ModerationValidationError(
                "Os metadados do caso precisam formar um objeto JSON."
            )
        try:
            encoded_metadata = json.dumps(
                case.metadata, ensure_ascii=True, allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ModerationValidationError(
                "Os metadados do caso precisam ser serializaveis em JSON."
            ) from exc
        if len(encoded_metadata.encode("utf-8")) > 16_384:
            raise ModerationValidationError(
                "Os metadados do caso excedem o limite de 16 KiB."
            )
        created = await self._repository.create_case(
            replace(case, reason=reason, duration=duration)
        )
        logger.info(
            "moderation.case.created guild_id=%s case_id=%s action=%s "
            "target_user_id=%s moderator_user_id=%s status=%s origin=%s",
            created.guild_id,
            created.id,
            created.action_type.value,
            created.target_user_id,
            created.moderator_user_id,
            created.status.value,
            created.origin.value,
        )
        return created

    async def authorize_configuration(
        self, guild_id: int, actor: ModerationPrincipal
    ) -> ModerationSettings:
        self._validate_discord_id(guild_id, "guild")
        self._validate_discord_id(actor.user_id, "usuario")
        self._require_same_guild(guild_id, actor, "usuario")
        settings = await self._repository.get_settings(guild_id)
        has_native_permission = (
            actor.is_owner
            or actor.is_administrator
            or "manage_guild" in actor.native_permissions
        )
        if not has_native_permission:
            raise ModerationAuthorizationError(
                "Voce precisa da permissao nativa Gerenciar Servidor."
            )
        has_configured_role = bool(
            actor.role_ids.intersection(settings.authorized_role_ids)
        )
        if not (actor.is_owner or actor.is_administrator or has_configured_role):
            raise ModerationAuthorizationError(
                "Voce nao possui um cargo autorizado para administrar a moderacao."
            )
        return settings

    async def authorize_action(
        self,
        guild_id: int,
        actor: ModerationPrincipal,
        target: ModerationPrincipal | None,
        bot: ModerationPrincipal,
        *,
        action_type: ModerationActionType,
    ) -> None:
        self._validate_discord_id(guild_id, "guild")
        self._validate_discord_id(actor.user_id, "moderador")
        self._validate_discord_id(bot.user_id, "bot")
        policy = MODERATION_ACTION_POLICIES.get(action_type)
        if policy is None:
            raise ModerationValidationError(
                "A acao de moderacao nao possui uma politica de autorizacao."
            )
        self._require_same_guild(guild_id, actor, "moderador")
        self._require_same_guild(guild_id, bot, "bot")
        if target is None:
            if policy.requires_target:
                raise ModerationValidationError(
                    "A acao de moderacao exige um usuario afetado."
                )
        else:
            self._validate_discord_id(target.user_id, "usuario afetado")
            self._require_same_guild(guild_id, target, "usuario afetado")
        settings = await self._repository.get_settings(guild_id)
        if not (
            actor.is_owner
            or actor.is_administrator
            or actor.role_ids.intersection(settings.authorized_role_ids)
        ):
            raise ModerationAuthorizationError(
                "Voce nao possui um cargo autorizado para esta acao."
            )
        if not (
            actor.is_owner
            or actor.is_administrator
            or policy.actor_permissions.issubset(actor.native_permissions)
        ):
            raise ModerationAuthorizationError(
                "Voce nao possui a permissao nativa necessaria para esta acao."
            )
        if not (
            bot.is_administrator
            or policy.bot_permissions.issubset(bot.native_permissions)
        ):
            raise ModerationAuthorizationError(
                "O bot nao possui a permissao nativa necessaria para esta acao."
            )
        if target is None:
            return
        if target.is_owner:
            raise ModerationAuthorizationError(
                "O proprietario do servidor nao pode ser alvo de moderacao."
            )
        if action_type is ModerationActionType.MUTE and target.is_administrator:
            raise ModerationAuthorizationError(
                "Administradores do servidor nao podem receber mute."
            )
        if target.user_id == actor.user_id:
            raise ModerationAuthorizationError("Voce nao pode agir sobre si mesmo.")
        if not actor.is_owner and target.hierarchy_rank >= actor.hierarchy_rank:
            raise ModerationAuthorizationError(
                "O alvo possui cargo igual ou superior ao seu."
            )
        if target.hierarchy_rank >= bot.hierarchy_rank:
            raise ModerationAuthorizationError(
                "O cargo do bot precisa estar acima do cargo do alvo."
            )

    async def add_authorized_role(
        self,
        guild_id: int,
        actor: ModerationPrincipal,
        role: ModerationRoleReference,
    ) -> bool:
        await self.authorize_configuration(guild_id, actor)
        self._validate_role_reference(guild_id, role)
        changed = await self._repository.add_authorized_role(guild_id, role.role_id)
        logger.info(
            "moderation.config.role_added guild_id=%s actor_id=%s "
            "role_id=%s changed=%s",
            guild_id,
            actor.user_id,
            role.role_id,
            changed,
        )
        return changed

    async def remove_authorized_role(
        self,
        guild_id: int,
        actor: ModerationPrincipal,
        role: ModerationRoleReference,
    ) -> bool:
        await self.authorize_configuration(guild_id, actor)
        self._validate_role_reference(guild_id, role)
        changed = await self._repository.remove_authorized_role(guild_id, role.role_id)
        logger.info(
            "moderation.config.role_removed guild_id=%s actor_id=%s "
            "role_id=%s changed=%s",
            guild_id,
            actor.user_id,
            role.role_id,
            changed,
        )
        return changed

    async def set_log_channel(
        self,
        guild_id: int,
        actor: ModerationPrincipal,
        channel: ModerationLogChannelReference | None,
    ) -> ModerationSettings:
        await self.authorize_configuration(guild_id, actor)
        channel_id: int | None = None
        if channel is not None:
            self._validate_discord_id(channel.channel_id, "canal")
            if channel.guild_id != guild_id:
                raise ModerationValidationError(
                    "O canal de logs precisa pertencer ao mesmo servidor."
                )
            if (
                not channel.bot_can_view
                or not channel.bot_can_send
                or not channel.bot_can_embed
            ):
                raise ModerationAuthorizationError(
                    "O bot precisa ver o canal, enviar mensagens e inserir links."
                )
            channel_id = channel.channel_id
        settings = await self._repository.set_log_channel(guild_id, channel_id)
        logger.info(
            "moderation.config.log_channel_updated guild_id=%s actor_id=%s "
            "channel_id=%s",
            guild_id,
            actor.user_id,
            channel_id,
        )
        return settings

    @staticmethod
    def _validate_discord_id(value: int, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ModerationValidationError(
                f"O ID de {label} precisa ser um inteiro positivo."
            )

    @staticmethod
    def _normalize_duration(duration: timedelta | None) -> timedelta | None:
        if duration is None:
            return None
        seconds = int(duration.total_seconds())
        if seconds <= 0:
            raise ModerationValidationError(
                "A duracao do caso precisa ser maior que zero."
            )
        return timedelta(seconds=seconds)

    @staticmethod
    def normalize_case_reason(reason: str) -> str:
        normalized = " ".join(reason.split())
        if not normalized:
            raise ModerationValidationError("O motivo do caso e obrigatorio.")
        if len(normalized) > 500:
            raise ModerationValidationError(
                "O motivo do caso nao pode passar de 500 caracteres."
            )
        return normalized

    @staticmethod
    def normalize_mute_duration(minutes: int) -> timedelta:
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise ModerationValidationError(
                "A duracao do mute precisa ser informada em minutos inteiros."
            )
        if not 1 <= minutes <= MAX_MUTE_DURATION_MINUTES:
            raise ModerationValidationError(
                "A duracao do mute precisa ficar entre 1 minuto e 28 dias."
            )
        return timedelta(minutes=minutes)

    @classmethod
    def _validate_role_reference(
        cls, guild_id: int, role: ModerationRoleReference
    ) -> None:
        cls._validate_discord_id(role.role_id, "cargo")
        if role.guild_id != guild_id:
            raise ModerationValidationError(
                "O cargo precisa pertencer ao mesmo servidor."
            )
        if role.is_default or role.role_id == guild_id:
            raise ModerationValidationError(
                "O cargo @everyone nao pode ser autorizado."
            )

    @staticmethod
    def _require_same_guild(
        guild_id: int, principal: ModerationPrincipal, label: str
    ) -> None:
        if principal.guild_id != guild_id:
            raise ModerationValidationError(
                f"O contexto de {label} pertence a outro servidor."
            )
