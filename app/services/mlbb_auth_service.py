from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Never, Protocol
from uuid import UUID

from app.integrations.mlbb import MlbbClient
from app.integrations.mlbb.errors import (
    MlbbAccountNotFoundError,
    MlbbAuthenticationError,
    MlbbIntegrationError,
    MlbbInvalidVerificationCodeError,
    MlbbUnavailableError,
    MlbbVerificationExpiredError,
)
from app.models.mlbb import (
    MlbbAccountLink,
    MlbbAccountLinkStatus,
    MlbbAccountSummary,
    MlbbAuthAttemptStatus,
    MlbbAuthPurpose,
    MlbbBeginAttemptOutcome,
    MlbbClaimAttemptOutcome,
    MlbbCompleteAttemptOutcome,
    MlbbLinkConfirmationSummary,
    MlbbLinkStartSummary,
    MlbbUnlinkSummary,
)
from app.repositories.mlbb_repository import (
    MlbbRepository,
    MlbbRepositoryAccountConflictError,
    MlbbRepositoryIdentityMismatchError,
    MlbbRepositoryStateError,
)
from app.services.mlbb_token_cipher import MlbbTokenCipher, MlbbTokenCipherError

logger = logging.getLogger(__name__)


class MlbbAuditRepository(Protocol):
    async def record_audit_log(
        self,
        *,
        guild_id: int,
        actor_id: int,
        action: str,
        target_user_id: int | None = None,
        target_resource_id: str | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> object: ...


class MlbbAccountCacheInvalidator(Protocol):
    def invalidate_account(self, *, guild_id: int, discord_user_id: int) -> None: ...


class MlbbAuthServiceError(RuntimeError):
    """Erro de produto seguro no fluxo de autenticacao MLBB."""


class MlbbFeatureDisabledError(MlbbAuthServiceError):
    pass


class MlbbValidationError(MlbbAuthServiceError):
    pass


class MlbbCooldownError(MlbbAuthServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Aguarde antes de solicitar outro codigo.")
        self.retry_after_seconds = retry_after_seconds


class MlbbOperationInProgressError(MlbbAuthServiceError):
    pass


class MlbbAlreadyLinkedError(MlbbAuthServiceError):
    pass


class MlbbAccountInUseError(MlbbAuthServiceError):
    pass


class MlbbReauthenticationNotAllowedError(MlbbAuthServiceError):
    pass


class MlbbAttemptNotFoundError(MlbbAuthServiceError):
    pass


class MlbbAttemptExpiredError(MlbbAuthServiceError):
    pass


class MlbbInvalidCodeError(MlbbAuthServiceError):
    def __init__(self, attempts_remaining: int) -> None:
        super().__init__("O codigo informado e invalido.")
        self.attempts_remaining = attempts_remaining


class MlbbTooManyAttemptsError(MlbbAuthServiceError):
    pass


class MlbbAccountMismatchError(MlbbAuthServiceError):
    pass


class MlbbAccountNotLinkedError(MlbbAuthServiceError):
    pass


class MlbbProviderUnavailableError(MlbbAuthServiceError):
    pass


class MlbbProviderRejectedError(MlbbAuthServiceError):
    pass


class MlbbAuthService:
    """Orquestra vinculo, reautenticacao e revogacao sem expor credenciais."""

    def __init__(
        self,
        repository: MlbbRepository,
        client: MlbbClient,
        token_cipher: MlbbTokenCipher,
        audit_repository: MlbbAuditRepository,
        *,
        enabled: bool,
        auth_ttl_seconds: int = 300,
        send_cooldown_seconds: int = 60,
        max_confirm_attempts: int = 5,
        clock: Callable[[], datetime] | None = None,
        cache_invalidator: MlbbAccountCacheInvalidator | None = None,
    ) -> None:
        if not 1 <= auth_ttl_seconds <= 300:
            raise ValueError("auth_ttl_seconds precisa ficar entre 1 e 300.")
        if send_cooldown_seconds <= 0:
            raise ValueError("send_cooldown_seconds precisa ser positivo.")
        if max_confirm_attempts <= 0:
            raise ValueError("max_confirm_attempts precisa ser positivo.")
        if enabled and not token_cipher.configured:
            raise ValueError(
                "MLBB_TOKEN_ENCRYPTION_KEYS e obrigatoria com MLBB_ENABLED."
            )
        self._repository = repository
        self._client = client
        self._token_cipher = token_cipher
        self._audit_repository = audit_repository
        self._enabled = enabled
        self._auth_ttl_seconds = auth_ttl_seconds
        self._send_cooldown_seconds = send_cooldown_seconds
        self._max_confirm_attempts = max_confirm_attempts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._cache_invalidator = cache_invalidator
        self._user_locks: dict[tuple[int, int], asyncio.Lock] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start_link(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        role_id: int | str,
        zone_id: int | str,
    ) -> MlbbLinkStartSummary:
        self._ensure_enabled()
        normalized_role = _normalize_id(role_id, "Game ID")
        normalized_zone = _normalize_id(zone_id, "Zone ID/Area")
        _validate_owner(guild_id, discord_user_id)
        async with self._lock_for(guild_id, discord_user_id):
            return await self._start(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                role_id=normalized_role,
                zone_id=normalized_zone,
                purpose=MlbbAuthPurpose.LINK,
            )

    async def start_reauthentication(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
    ) -> MlbbLinkStartSummary:
        self._ensure_enabled()
        _validate_owner(guild_id, discord_user_id)
        async with self._lock_for(guild_id, discord_user_id):
            link = await self._repository.get_link(
                guild_id=guild_id, discord_user_id=discord_user_id
            )
            if link is None or link.status is not MlbbAccountLinkStatus.REAUTH_REQUIRED:
                raise MlbbReauthenticationNotAllowedError(
                    "Este vinculo nao precisa de reautenticacao."
                )
            return await self._start(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                role_id=link.role_id,
                zone_id=link.zone_id,
                purpose=MlbbAuthPurpose.REAUTH,
            )

    async def _start(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        purpose: MlbbAuthPurpose,
    ) -> MlbbLinkStartSummary:
        now = self._now()
        result = await self._repository.begin_attempt(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            role_id=role_id,
            zone_id=zone_id,
            purpose=purpose,
            now=now,
            expires_at=now + timedelta(seconds=self._auth_ttl_seconds),
            cooldown_seconds=self._send_cooldown_seconds,
        )
        if result.outcome is MlbbBeginAttemptOutcome.COOLDOWN:
            raise MlbbCooldownError(result.retry_after_seconds or 1)
        if result.outcome is MlbbBeginAttemptOutcome.IN_PROGRESS:
            raise MlbbOperationInProgressError(
                "Uma solicitacao MLBB ja esta em andamento."
            )
        if result.outcome is MlbbBeginAttemptOutcome.ALREADY_LINKED:
            raise MlbbAlreadyLinkedError("Voce ja possui uma conta MLBB vinculada.")
        if result.outcome is MlbbBeginAttemptOutcome.ACCOUNT_IN_USE:
            raise MlbbAccountInUseError(
                "Esta conta MLBB ja esta vinculada a outro membro."
            )
        if result.outcome is MlbbBeginAttemptOutcome.REAUTH_NOT_ALLOWED:
            raise MlbbReauthenticationNotAllowedError(
                "Este vinculo nao aceita reautenticacao."
            )
        attempt = result.attempt
        if attempt is None:
            raise MlbbProviderRejectedError("Nao foi possivel iniciar o vinculo.")
        try:
            await self._client.send_verification_code(role_id=role_id, zone_id=zone_id)
        except MlbbIntegrationError as exc:
            await self._repository.mark_send_failed(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
            )
            await self._audit(
                guild_id,
                discord_user_id,
                "mlbb.link_code_send_failed",
                str(attempt.id),
                {"purpose": purpose.value},
            )
            self._raise_provider_error(exc)
        sent = await self._repository.mark_code_sent(
            attempt_id=attempt.id,
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            sent_at=self._now(),
        )
        await self._audit(
            guild_id,
            discord_user_id,
            "mlbb.link_code_sent",
            str(attempt.id),
            {"purpose": purpose.value, "status": sent.status.value},
        )
        return MlbbLinkStartSummary(expires_at=sent.expires_at)

    async def confirm_link(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        verification_code: str,
    ) -> MlbbLinkConfirmationSummary:
        self._ensure_enabled()
        _validate_owner(guild_id, discord_user_id)
        code = verification_code.strip()
        if not code or len(code) > 32:
            raise MlbbValidationError("Informe um codigo de verificacao valido.")
        async with self._lock_for(guild_id, discord_user_id):
            return await self._confirm_locked(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                verification_code=code,
            )

    async def _confirm_locked(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        verification_code: str,
    ) -> MlbbLinkConfirmationSummary:
        claim = await self._repository.claim_confirmation(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            now=self._now(),
            max_attempts=self._max_confirm_attempts,
        )
        if claim.outcome is MlbbClaimAttemptOutcome.ALREADY_VERIFIED:
            if claim.link is None:
                raise MlbbAttemptNotFoundError("Vinculo MLBB nao encontrado.")
            return MlbbLinkConfirmationSummary(
                _account_summary(claim.link), already_verified=True
            )
        if claim.outcome is MlbbClaimAttemptOutcome.NOT_FOUND:
            raise MlbbAttemptNotFoundError(
                "Nenhuma tentativa MLBB aberta foi encontrada."
            )
        if claim.outcome is MlbbClaimAttemptOutcome.EXPIRED:
            raise MlbbAttemptExpiredError(
                "A tentativa expirou. Solicite um novo codigo."
            )
        if claim.outcome is MlbbClaimAttemptOutcome.TOO_MANY_ATTEMPTS:
            raise MlbbTooManyAttemptsError(
                "O limite de tentativas foi atingido. Solicite um novo codigo."
            )
        if claim.outcome is MlbbClaimAttemptOutcome.IN_PROGRESS:
            raise MlbbOperationInProgressError(
                "Esta confirmacao MLBB ja esta em andamento."
            )
        attempt = claim.attempt
        if attempt is None:
            raise MlbbAttemptNotFoundError("Tentativa MLBB nao encontrada.")

        try:
            login = await self._client.login(
                role_id=attempt.role_id,
                zone_id=attempt.zone_id,
                verification_code=verification_code,
            )
        except MlbbInvalidVerificationCodeError:
            failed = await self._repository.record_confirmation_failure(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
                max_attempts=self._max_confirm_attempts,
            )
            await self._audit(
                guild_id,
                discord_user_id,
                "mlbb.link_confirmation_rejected",
                str(attempt.id),
                {"attempts": failed.attempts, "status": failed.status.value},
            )
            if failed.status is MlbbAuthAttemptStatus.FAILED:
                raise MlbbTooManyAttemptsError(
                    "O limite de tentativas foi atingido. Solicite um novo codigo."
                ) from None
            raise MlbbInvalidCodeError(
                self._max_confirm_attempts - failed.attempts
            ) from None
        except MlbbVerificationExpiredError:
            await self._repository.fail_confirmation(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
            )
            raise MlbbAttemptExpiredError(
                "O codigo expirou. Solicite um novo codigo."
            ) from None
        except MlbbUnavailableError:
            await self._release_claim(attempt.id, guild_id, discord_user_id)
            raise MlbbProviderUnavailableError(
                "A API MLBB esta indisponivel. Tente novamente em instantes."
            ) from None
        except MlbbAuthenticationError:
            failed = await self._repository.record_confirmation_failure(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
                max_attempts=self._max_confirm_attempts,
            )
            if failed.status is MlbbAuthAttemptStatus.FAILED:
                raise MlbbTooManyAttemptsError(
                    "O limite de tentativas foi atingido. Solicite um novo codigo."
                ) from None
            raise MlbbInvalidCodeError(
                self._max_confirm_attempts - failed.attempts
            ) from None
        except MlbbIntegrationError as exc:
            await self._release_claim(attempt.id, guild_id, discord_user_id)
            self._raise_provider_error(exc)

        try:
            profile = await self._client.get_user_info(jwt=login.jwt)
        except MlbbUnavailableError:
            await self._release_claim(attempt.id, guild_id, discord_user_id)
            await self._safe_logout(login.jwt)
            raise MlbbProviderUnavailableError(
                "A API MLBB esta indisponivel. Tente novamente em instantes."
            ) from None
        except MlbbIntegrationError:
            await self._repository.fail_confirmation(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
            )
            await self._safe_logout(login.jwt)
            raise MlbbProviderRejectedError(
                "A API MLBB nao confirmou a identidade da conta."
            ) from None

        identity_matches = (
            login.role_id == attempt.role_id
            and login.zone_id == attempt.zone_id
            and profile.role_id == attempt.role_id
            and profile.zone_id == attempt.zone_id
        )
        if not identity_matches:
            await self._repository.fail_confirmation(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
            )
            await self._safe_logout(login.jwt)
            await self._audit(
                guild_id,
                discord_user_id,
                "mlbb.link_identity_mismatch",
                str(attempt.id),
                {"status": "FAILED"},
            )
            raise MlbbAccountMismatchError(
                "A API retornou uma conta diferente da tentativa iniciada."
            )

        try:
            encrypted_jwt = self._token_cipher.encrypt(login.jwt)
        except MlbbTokenCipherError:
            await self._release_claim(attempt.id, guild_id, discord_user_id)
            await self._safe_logout(login.jwt)
            raise MlbbProviderRejectedError(
                "Nao foi possivel proteger a sessao MLBB."
            ) from None

        try:
            completed = await self._repository.complete_confirmation(
                attempt_id=attempt.id,
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                role_id=profile.role_id,
                zone_id=profile.zone_id,
                player_name=profile.name,
                avatar_url=profile.avatar_url,
                country_code=profile.country_code,
                encrypted_jwt=encrypted_jwt,
                now=self._now(),
                max_attempts=self._max_confirm_attempts,
            )
        except MlbbRepositoryAccountConflictError:
            await self._safe_logout(login.jwt)
            raise MlbbAccountInUseError(
                "Esta conta MLBB ja esta vinculada a outro membro."
            ) from None
        except MlbbRepositoryIdentityMismatchError:
            await self._safe_logout(login.jwt)
            raise MlbbAccountMismatchError(
                "A identidade MLBB nao corresponde a tentativa."
            ) from None
        except MlbbRepositoryStateError:
            await self._safe_logout(login.jwt)
            raise MlbbAttemptExpiredError(
                "A tentativa mudou ou expirou. Solicite um novo codigo."
            ) from None

        self._invalidate_cache(guild_id, discord_user_id)
        await self._audit(
            guild_id,
            discord_user_id,
            "mlbb.link_verified",
            str(attempt.id),
            {
                "purpose": completed.attempt.purpose.value,
                "status": completed.link.status.value,
            },
        )
        return MlbbLinkConfirmationSummary(
            _account_summary(completed.link),
            already_verified=(
                completed.outcome is MlbbCompleteAttemptOutcome.ALREADY_VERIFIED
            ),
        )

    async def get_account(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountSummary:
        self._ensure_enabled()
        _validate_owner(guild_id, discord_user_id)
        link = await self._repository.get_link(
            guild_id=guild_id, discord_user_id=discord_user_id
        )
        if link is None:
            raise MlbbAccountNotLinkedError("Voce nao possui uma conta MLBB vinculada.")
        return _account_summary(link)

    async def unlink(self, *, guild_id: int, discord_user_id: int) -> MlbbUnlinkSummary:
        _validate_owner(guild_id, discord_user_id)
        async with self._lock_for(guild_id, discord_user_id):
            link = await self._repository.get_link(
                guild_id=guild_id, discord_user_id=discord_user_id
            )
            if link is None:
                raise MlbbAccountNotLinkedError(
                    "Voce nao possui uma conta MLBB vinculada."
                )
            if link.status is MlbbAccountLinkStatus.REVOKED:
                self._invalidate_cache(guild_id, discord_user_id)
                return MlbbUnlinkSummary(
                    _account_summary(link), external_logout_succeeded=False
                )

            external_logout_succeeded = False
            if self._enabled and link.encrypted_jwt:
                try:
                    jwt = self._token_cipher.decrypt(link.encrypted_jwt)
                    await self._client.logout(jwt=jwt)
                    external_logout_succeeded = True
                except (MlbbIntegrationError, MlbbTokenCipherError):
                    external_logout_succeeded = False

            revoked = await self._repository.revoke_link(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                now=self._now(),
            )
            if revoked is None:
                raise MlbbAccountNotLinkedError(
                    "Voce nao possui uma conta MLBB vinculada."
                )
            self._invalidate_cache(guild_id, discord_user_id)
            await self._audit(
                guild_id,
                discord_user_id,
                "mlbb.link_revoked",
                None,
                {
                    "status": revoked.status.value,
                    "provider_logout": external_logout_succeeded,
                },
            )
            return MlbbUnlinkSummary(
                _account_summary(revoked),
                external_logout_succeeded=external_logout_succeeded,
            )

    async def mark_reauth_required(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountSummary:
        """Uso futuro por services autenticados, somente em erro claro de sessao."""

        link = await self._repository.mark_reauth_required(
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            now=self._now(),
        )
        if link is None:
            raise MlbbAccountNotLinkedError("Vinculo MLBB nao encontrado.")
        self._invalidate_cache(guild_id, discord_user_id)
        return _account_summary(link)

    def _invalidate_cache(self, guild_id: int, discord_user_id: int) -> None:
        if self._cache_invalidator is None:
            return
        try:
            self._cache_invalidator.invalidate_account(
                guild_id=guild_id,
                discord_user_id=discord_user_id,
            )
        except Exception:
            logger.exception(
                "Falha ao invalidar cache MLBB guild_id=%s discord_user_id=%s",
                guild_id,
                discord_user_id,
            )

    async def _release_claim(
        self, attempt_id: UUID, guild_id: int, discord_user_id: int
    ) -> None:
        await self._repository.release_confirmation(
            attempt_id=attempt_id,
            guild_id=guild_id,
            discord_user_id=discord_user_id,
            now=self._now(),
        )

    async def _safe_logout(self, jwt: str) -> None:
        try:
            await self._client.logout(jwt=jwt)
        except MlbbIntegrationError:
            return

    async def _audit(
        self,
        guild_id: int,
        discord_user_id: int,
        action: str,
        resource_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        try:
            await self._audit_repository.record_audit_log(
                guild_id=guild_id,
                actor_id=discord_user_id,
                action=action,
                target_user_id=discord_user_id,
                target_resource_id=resource_id,
                after_data=metadata,
            )
        except Exception:
            logger.warning(
                "mlbb.audit.failed action=%s guild_id=%s actor_id=%s",
                action,
                guild_id,
                discord_user_id,
            )

    def _lock_for(self, guild_id: int, discord_user_id: int) -> asyncio.Lock:
        key = (guild_id, discord_user_id)
        lock = self._user_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[key] = lock
        return lock

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _ensure_enabled(self) -> None:
        if not self._enabled:
            raise MlbbFeatureDisabledError(
                "A integracao MLBB esta desabilitada neste ambiente."
            )

    @staticmethod
    def _raise_provider_error(error: MlbbIntegrationError) -> Never:
        if isinstance(error, MlbbUnavailableError):
            raise MlbbProviderUnavailableError(
                "A API MLBB esta indisponivel. Tente novamente em instantes."
            ) from None
        if isinstance(error, MlbbAccountNotFoundError):
            raise MlbbProviderRejectedError(
                "A conta MLBB informada nao foi encontrada."
            ) from None
        raise MlbbProviderRejectedError(
            "A API MLBB recusou a operacao. Confira os dados informados."
        ) from None


def _validate_owner(guild_id: int, discord_user_id: int) -> None:
    if guild_id <= 0 or discord_user_id <= 0:
        raise MlbbValidationError("Esta operacao so pode ser usada em um servidor.")


def _normalize_id(value: int | str, label: str) -> int:
    if isinstance(value, bool):
        raise MlbbValidationError(f"{label} deve conter apenas digitos.")
    raw = str(value).strip()
    if not raw or len(raw) > 19 or not raw.isascii() or not raw.isdigit():
        raise MlbbValidationError(f"{label} deve conter apenas digitos.")
    normalized = int(raw)
    if normalized <= 0 or normalized > 9_223_372_036_854_775_807:
        raise MlbbValidationError(f"{label} esta fora do intervalo permitido.")
    return normalized


def _account_summary(link: MlbbAccountLink) -> MlbbAccountSummary:
    return MlbbAccountSummary(
        role_id=link.role_id,
        zone_id=link.zone_id,
        player_name=link.player_name,
        avatar_url=link.avatar_url,
        country_code=link.country_code,
        status=link.status,
        visibility=link.visibility,
        verified_at=link.verified_at,
    )
