from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.models.mlbb import (
    MlbbAccountLink,
    MlbbAccountLinkStatus,
    MlbbAuthAttempt,
    MlbbAuthAttemptStatus,
    MlbbAuthPurpose,
    MlbbBeginAttemptOutcome,
    MlbbBeginAttemptResult,
    MlbbClaimAttemptOutcome,
    MlbbClaimAttemptResult,
    MlbbCompleteAttemptOutcome,
    MlbbCompleteAttemptResult,
    MlbbProfileVisibility,
)
from app.repositories.errors import RepositoryIntegrityError
from app.repositories.postgres_database import (
    PostgresConnectionAdapter,
    PostgresDatabase,
)


class MlbbRepositoryError(RuntimeError):
    """Falha segura da persistencia do dominio MLBB."""


class MlbbRepositoryStateError(MlbbRepositoryError):
    """A tentativa mudou de estado antes da operacao ser concluida."""


class MlbbRepositoryAccountConflictError(MlbbRepositoryError):
    """A conta do jogo ja pertence a outro membro da guild."""


class MlbbRepositoryIdentityMismatchError(MlbbRepositoryError):
    """A identidade retornada nao corresponde a tentativa persistida."""


class MlbbRepository(Protocol):
    async def begin_attempt(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        purpose: MlbbAuthPurpose,
        now: datetime,
        expires_at: datetime,
        cooldown_seconds: int,
    ) -> MlbbBeginAttemptResult: ...

    async def mark_code_sent(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        sent_at: datetime,
    ) -> MlbbAuthAttempt: ...

    async def mark_send_failed(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None: ...

    async def claim_confirmation(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbClaimAttemptResult: ...

    async def record_confirmation_failure(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbAuthAttempt: ...

    async def release_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None: ...

    async def fail_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None: ...

    async def complete_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        encrypted_jwt: str,
        now: datetime,
        max_attempts: int,
    ) -> MlbbCompleteAttemptResult: ...

    async def get_link(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountLink | None: ...

    async def update_profile_metadata(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        now: datetime,
    ) -> MlbbAccountLink | None: ...

    async def update_visibility(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        visibility: MlbbProfileVisibility,
        now: datetime,
    ) -> MlbbAccountLink | None: ...

    async def revoke_link(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None: ...

    async def mark_reauth_required(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None: ...


class PostgresMlbbRepository:
    """Persistencia MLBB sobre o pool PostgreSQL compartilhado do projeto."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    async def begin_attempt(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        purpose: MlbbAuthPurpose,
        now: datetime,
        expires_at: datetime,
        cooldown_seconds: int,
    ) -> MlbbBeginAttemptResult:
        return await asyncio.to_thread(
            self._begin_attempt_sync,
            guild_id,
            discord_user_id,
            role_id,
            zone_id,
            purpose,
            now,
            expires_at,
            cooldown_seconds,
        )

    def _begin_attempt_sync(
        self,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        purpose: MlbbAuthPurpose,
        now: datetime,
        expires_at: datetime,
        cooldown_seconds: int,
    ) -> MlbbBeginAttemptResult:
        attempt_id = uuid4()
        try:
            with self._database.connection() as connection:
                self._advisory_lock(
                    connection, f"mlbb:user:{guild_id}:{discord_user_id}"
                )
                self._advisory_lock(
                    connection,
                    f"mlbb:account:{guild_id}:{role_id}:{zone_id}",
                )
                open_row = connection.execute(
                    """
                    SELECT * FROM mlbb_auth_attempts
                    WHERE guild_id = ? AND discord_user_id = ?
                      AND status IN ('CREATED', 'CODE_SENT', 'VERIFYING')
                    ORDER BY created_at DESC LIMIT 1 FOR UPDATE
                    """,
                    (guild_id, discord_user_id),
                ).fetchone()
                if open_row is not None:
                    existing = _attempt_from_row(open_row)
                    if existing.expires_at <= now:
                        self._set_attempt_status(
                            connection, existing.id, MlbbAuthAttemptStatus.EXPIRED, now
                        )
                    elif existing.status in {
                        MlbbAuthAttemptStatus.CREATED,
                        MlbbAuthAttemptStatus.VERIFYING,
                    }:
                        return MlbbBeginAttemptResult(
                            MlbbBeginAttemptOutcome.IN_PROGRESS, attempt=existing
                        )
                    else:
                        cooldown_until = (
                            existing.code_sent_at or existing.created_at
                        ) + timedelta(seconds=cooldown_seconds)
                        if now < cooldown_until:
                            return MlbbBeginAttemptResult(
                                MlbbBeginAttemptOutcome.COOLDOWN,
                                attempt=existing,
                                retry_after_seconds=max(
                                    1, math.ceil((cooldown_until - now).total_seconds())
                                ),
                            )
                        self._set_attempt_status(
                            connection,
                            existing.id,
                            MlbbAuthAttemptStatus.CANCELLED,
                            now,
                        )

                account_row = connection.execute(
                    """
                    SELECT * FROM mlbb_account_links
                    WHERE guild_id = ? AND role_id = ? AND zone_id = ?
                    FOR UPDATE
                    """,
                    (guild_id, role_id, zone_id),
                ).fetchone()
                if account_row is not None:
                    account_link = _link_from_row(account_row)
                    if account_link.discord_user_id != discord_user_id:
                        if self._can_discard_stale_link(connection, account_link, now):
                            connection.execute(
                                """
                                DELETE FROM mlbb_account_links
                                WHERE guild_id = ? AND discord_user_id = ?
                                """,
                                (guild_id, account_link.discord_user_id),
                            )
                        else:
                            return MlbbBeginAttemptResult(
                                MlbbBeginAttemptOutcome.ACCOUNT_IN_USE
                            )

                owner_row = connection.execute(
                    """
                    SELECT * FROM mlbb_account_links
                    WHERE guild_id = ? AND discord_user_id = ?
                    FOR UPDATE
                    """,
                    (guild_id, discord_user_id),
                ).fetchone()
                owner_link = (
                    _link_from_row(owner_row) if owner_row is not None else None
                )
                if purpose is MlbbAuthPurpose.REAUTH:
                    if (
                        owner_link is None
                        or owner_link.status
                        is not MlbbAccountLinkStatus.REAUTH_REQUIRED
                        or owner_link.role_id != role_id
                        or owner_link.zone_id != zone_id
                    ):
                        return MlbbBeginAttemptResult(
                            MlbbBeginAttemptOutcome.REAUTH_NOT_ALLOWED
                        )
                elif owner_link is not None and owner_link.status in {
                    MlbbAccountLinkStatus.ACTIVE,
                    MlbbAccountLinkStatus.REAUTH_REQUIRED,
                }:
                    return MlbbBeginAttemptResult(
                        MlbbBeginAttemptOutcome.ALREADY_LINKED
                    )

                connection.execute(
                    """
                    INSERT INTO mlbb_auth_attempts (
                        id, guild_id, discord_user_id, role_id, zone_id,
                        purpose, status, attempts, expires_at,
                        code_sent_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'CREATED', 0, ?, NULL, ?, ?)
                    """,
                    (
                        attempt_id,
                        guild_id,
                        discord_user_id,
                        role_id,
                        zone_id,
                        purpose.value,
                        expires_at,
                        now,
                        now,
                    ),
                )
                if purpose is MlbbAuthPurpose.LINK:
                    connection.execute(
                        """
                        INSERT INTO mlbb_account_links (
                            guild_id, discord_user_id, role_id, zone_id,
                            player_name, avatar_url, country_code, encrypted_jwt,
                            status, visibility, verified_at, last_validated_at,
                            last_used_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL,
                                  'PENDING', 'GUILD', NULL, NULL, NULL, ?, ?)
                        ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                            role_id = excluded.role_id, zone_id = excluded.zone_id,
                            player_name = NULL, avatar_url = NULL,
                            country_code = NULL, encrypted_jwt = NULL,
                            status = 'PENDING', verified_at = NULL,
                            last_validated_at = NULL, last_used_at = NULL,
                            updated_at = excluded.updated_at
                        """,
                        (guild_id, discord_user_id, role_id, zone_id, now, now),
                    )
                row = connection.execute(
                    "SELECT * FROM mlbb_auth_attempts WHERE id = ?", (attempt_id,)
                ).fetchone()
        except RepositoryIntegrityError as exc:
            raise MlbbRepositoryAccountConflictError(
                "A conta MLBB ja esta vinculada nesta guild."
            ) from exc
        if row is None:
            raise MlbbRepositoryStateError("A tentativa MLBB nao foi criada.")
        return MlbbBeginAttemptResult(
            MlbbBeginAttemptOutcome.CREATED, attempt=_attempt_from_row(row)
        )

    async def mark_code_sent(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        sent_at: datetime,
    ) -> MlbbAuthAttempt:
        return await asyncio.to_thread(
            self._mark_code_sent_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            sent_at,
        )

    def _mark_code_sent_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        sent_at: datetime,
    ) -> MlbbAuthAttempt:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mlbb_auth_attempts
                WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                FOR UPDATE
                """,
                (attempt_id, guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                raise MlbbRepositoryStateError("Tentativa MLBB nao encontrada.")
            attempt = _attempt_from_row(row)
            if attempt.status is MlbbAuthAttemptStatus.CODE_SENT:
                return attempt
            if attempt.status is not MlbbAuthAttemptStatus.CREATED:
                raise MlbbRepositoryStateError("Tentativa MLBB nao aceita envio.")
            updated = connection.execute(
                """
                UPDATE mlbb_auth_attempts
                SET status = 'CODE_SENT', code_sent_at = ?, updated_at = ?
                WHERE id = ? RETURNING *
                """,
                (sent_at, sent_at, attempt_id),
            ).fetchone()
        if updated is None:
            raise MlbbRepositoryStateError("Tentativa MLBB nao foi atualizada.")
        return _attempt_from_row(updated)

    async def mark_send_failed(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._mark_send_failed_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            now,
        )

    def _mark_send_failed_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mlbb_auth_attempts
                WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                FOR UPDATE
                """,
                (attempt_id, guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                return
            attempt = _attempt_from_row(row)
            if attempt.status in {
                MlbbAuthAttemptStatus.CREATED,
                MlbbAuthAttemptStatus.CODE_SENT,
            }:
                self._set_attempt_status(
                    connection, attempt.id, MlbbAuthAttemptStatus.FAILED, now
                )
                self._revoke_pending_link(connection, attempt, now)

    async def claim_confirmation(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbClaimAttemptResult:
        return await asyncio.to_thread(
            self._claim_confirmation_sync,
            guild_id,
            discord_user_id,
            now,
            max_attempts,
        )

    def _claim_confirmation_sync(
        self,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbClaimAttemptResult:
        with self._database.connection() as connection:
            self._advisory_lock(connection, f"mlbb:user:{guild_id}:{discord_user_id}")
            row = connection.execute(
                """
                SELECT * FROM mlbb_auth_attempts
                WHERE guild_id = ? AND discord_user_id = ?
                ORDER BY created_at DESC LIMIT 1 FOR UPDATE
                """,
                (guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                return MlbbClaimAttemptResult(MlbbClaimAttemptOutcome.NOT_FOUND)
            attempt = _attempt_from_row(row)
            if attempt.status is MlbbAuthAttemptStatus.VERIFIED:
                link = self._get_link_with_connection(
                    connection, guild_id, discord_user_id
                )
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.ALREADY_VERIFIED,
                    attempt=attempt,
                    link=link,
                )
            if attempt.expires_at <= now:
                self._set_attempt_status(
                    connection, attempt.id, MlbbAuthAttemptStatus.EXPIRED, now
                )
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.EXPIRED, attempt=attempt
                )
            if attempt.attempts >= max_attempts:
                self._set_attempt_status(
                    connection, attempt.id, MlbbAuthAttemptStatus.FAILED, now
                )
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.TOO_MANY_ATTEMPTS, attempt=attempt
                )
            if attempt.status is MlbbAuthAttemptStatus.VERIFYING:
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.IN_PROGRESS, attempt=attempt
                )
            if attempt.status is not MlbbAuthAttemptStatus.CODE_SENT:
                outcome = (
                    MlbbClaimAttemptOutcome.TOO_MANY_ATTEMPTS
                    if attempt.status is MlbbAuthAttemptStatus.FAILED
                    and attempt.attempts >= max_attempts
                    else MlbbClaimAttemptOutcome.NOT_FOUND
                )
                return MlbbClaimAttemptResult(outcome, attempt=attempt)
            updated = connection.execute(
                """
                UPDATE mlbb_auth_attempts
                SET status = 'VERIFYING', updated_at = ?
                WHERE id = ? RETURNING *
                """,
                (now, attempt.id),
            ).fetchone()
        if updated is None:
            raise MlbbRepositoryStateError("Tentativa MLBB nao foi reservada.")
        return MlbbClaimAttemptResult(
            MlbbClaimAttemptOutcome.CLAIMED, attempt=_attempt_from_row(updated)
        )

    async def record_confirmation_failure(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbAuthAttempt:
        return await asyncio.to_thread(
            self._record_confirmation_failure_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            now,
            max_attempts,
        )

    def _record_confirmation_failure_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbAuthAttempt:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mlbb_auth_attempts
                WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                FOR UPDATE
                """,
                (attempt_id, guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                raise MlbbRepositoryStateError("Tentativa MLBB nao encontrada.")
            attempt = _attempt_from_row(row)
            if attempt.status is not MlbbAuthAttemptStatus.VERIFYING:
                return attempt
            attempts = attempt.attempts + 1
            status = (
                MlbbAuthAttemptStatus.FAILED
                if attempts >= max_attempts
                else MlbbAuthAttemptStatus.CODE_SENT
            )
            updated = connection.execute(
                """
                UPDATE mlbb_auth_attempts
                SET status = ?, attempts = ?, updated_at = ?
                WHERE id = ? RETURNING *
                """,
                (status.value, attempts, now, attempt.id),
            ).fetchone()
            if status is MlbbAuthAttemptStatus.FAILED:
                self._revoke_pending_link(connection, attempt, now)
        if updated is None:
            raise MlbbRepositoryStateError("Tentativa MLBB nao foi atualizada.")
        return _attempt_from_row(updated)

    async def release_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._release_confirmation_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            now,
        )

    def _release_confirmation_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE mlbb_auth_attempts
                SET status = 'CODE_SENT', updated_at = ?
                WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                  AND status = 'VERIFYING'
                """,
                (now, attempt_id, guild_id, discord_user_id),
            )

    async def fail_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._fail_confirmation_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            now,
        )

    def _fail_confirmation_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
    ) -> None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mlbb_auth_attempts
                WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                FOR UPDATE
                """,
                (attempt_id, guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                return
            attempt = _attempt_from_row(row)
            if attempt.status is MlbbAuthAttemptStatus.VERIFYING:
                self._set_attempt_status(
                    connection, attempt.id, MlbbAuthAttemptStatus.FAILED, now
                )
                self._revoke_pending_link(connection, attempt, now)

    async def complete_confirmation(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        encrypted_jwt: str,
        now: datetime,
        max_attempts: int,
    ) -> MlbbCompleteAttemptResult:
        return await asyncio.to_thread(
            self._complete_confirmation_sync,
            attempt_id,
            guild_id,
            discord_user_id,
            role_id,
            zone_id,
            player_name,
            avatar_url,
            country_code,
            encrypted_jwt,
            now,
            max_attempts,
        )

    def _complete_confirmation_sync(
        self,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        role_id: int,
        zone_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        encrypted_jwt: str,
        now: datetime,
        max_attempts: int,
    ) -> MlbbCompleteAttemptResult:
        try:
            with self._database.connection() as connection:
                self._advisory_lock(
                    connection, f"mlbb:account:{guild_id}:{role_id}:{zone_id}"
                )
                row = connection.execute(
                    """
                    SELECT * FROM mlbb_auth_attempts
                    WHERE id = ? AND guild_id = ? AND discord_user_id = ?
                    FOR UPDATE
                    """,
                    (attempt_id, guild_id, discord_user_id),
                ).fetchone()
                if row is None:
                    raise MlbbRepositoryStateError("Tentativa MLBB nao encontrada.")
                attempt = _attempt_from_row(row)
                if attempt.status is MlbbAuthAttemptStatus.VERIFIED:
                    existing = self._get_link_with_connection(
                        connection, guild_id, discord_user_id
                    )
                    if existing is None:
                        raise MlbbRepositoryStateError("Vinculo MLBB nao encontrado.")
                    return MlbbCompleteAttemptResult(
                        MlbbCompleteAttemptOutcome.ALREADY_VERIFIED,
                        attempt,
                        existing,
                    )
                if (
                    attempt.status is not MlbbAuthAttemptStatus.VERIFYING
                    or attempt.expires_at <= now
                    or attempt.attempts >= max_attempts
                ):
                    raise MlbbRepositoryStateError("Tentativa MLBB nao esta valida.")
                if attempt.role_id != role_id or attempt.zone_id != zone_id:
                    raise MlbbRepositoryIdentityMismatchError(
                        "Identidade MLBB divergente."
                    )

                account_row = connection.execute(
                    """
                    SELECT * FROM mlbb_account_links
                    WHERE guild_id = ? AND role_id = ? AND zone_id = ?
                    FOR UPDATE
                    """,
                    (guild_id, role_id, zone_id),
                ).fetchone()
                if account_row is not None:
                    account_link = _link_from_row(account_row)
                    if account_link.discord_user_id != discord_user_id:
                        if account_link.status is MlbbAccountLinkStatus.REVOKED:
                            connection.execute(
                                """
                                DELETE FROM mlbb_account_links
                                WHERE guild_id = ? AND discord_user_id = ?
                                """,
                                (guild_id, account_link.discord_user_id),
                            )
                        else:
                            raise MlbbRepositoryAccountConflictError(
                                "A conta MLBB ja esta vinculada nesta guild."
                            )

                owner_link = self._get_link_with_connection(
                    connection, guild_id, discord_user_id, for_update=True
                )
                if attempt.purpose is MlbbAuthPurpose.REAUTH and (
                    owner_link is None
                    or owner_link.status is not MlbbAccountLinkStatus.REAUTH_REQUIRED
                    or owner_link.role_id != role_id
                    or owner_link.zone_id != zone_id
                ):
                    raise MlbbRepositoryStateError(
                        "O vinculo MLBB nao aceita reautenticacao."
                    )

                link_row = connection.execute(
                    """
                    INSERT INTO mlbb_account_links (
                        guild_id, discord_user_id, role_id, zone_id,
                        player_name, avatar_url, country_code, encrypted_jwt,
                        status, visibility, verified_at, last_validated_at,
                        last_used_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 'GUILD',
                              ?, ?, NULL, ?, ?)
                    ON CONFLICT (guild_id, discord_user_id) DO UPDATE SET
                        role_id = excluded.role_id,
                        zone_id = excluded.zone_id,
                        player_name = excluded.player_name,
                        avatar_url = excluded.avatar_url,
                        country_code = excluded.country_code,
                        encrypted_jwt = excluded.encrypted_jwt,
                        status = 'ACTIVE',
                        verified_at = excluded.verified_at,
                        last_validated_at = excluded.last_validated_at,
                        updated_at = excluded.updated_at
                    RETURNING *
                    """,
                    (
                        guild_id,
                        discord_user_id,
                        role_id,
                        zone_id,
                        player_name,
                        avatar_url,
                        country_code,
                        encrypted_jwt,
                        now,
                        now,
                        now,
                        now,
                    ),
                ).fetchone()
                attempt_row = connection.execute(
                    """
                    UPDATE mlbb_auth_attempts
                    SET status = 'VERIFIED', updated_at = ?
                    WHERE id = ? RETURNING *
                    """,
                    (now, attempt_id),
                ).fetchone()
        except RepositoryIntegrityError as exc:
            raise MlbbRepositoryAccountConflictError(
                "A conta MLBB ja esta vinculada nesta guild."
            ) from exc
        if link_row is None or attempt_row is None:
            raise MlbbRepositoryStateError("Vinculo MLBB nao foi concluido.")
        return MlbbCompleteAttemptResult(
            MlbbCompleteAttemptOutcome.COMPLETED,
            _attempt_from_row(attempt_row),
            _link_from_row(link_row),
        )

    async def get_link(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountLink | None:
        return await asyncio.to_thread(self._get_link_sync, guild_id, discord_user_id)

    def _get_link_sync(
        self, guild_id: int, discord_user_id: int
    ) -> MlbbAccountLink | None:
        with self._database.connection() as connection:
            return self._get_link_with_connection(connection, guild_id, discord_user_id)

    async def update_profile_metadata(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        now: datetime,
    ) -> MlbbAccountLink | None:
        return await asyncio.to_thread(
            self._update_profile_metadata_sync,
            guild_id,
            discord_user_id,
            player_name,
            avatar_url,
            country_code,
            now,
        )

    def _update_profile_metadata_sync(
        self,
        guild_id: int,
        discord_user_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        now: datetime,
    ) -> MlbbAccountLink | None:
        with self._database.connection() as connection:
            current = self._get_link_with_connection(
                connection,
                guild_id,
                discord_user_id,
                for_update=True,
            )
            if current is None or current.status is not MlbbAccountLinkStatus.ACTIVE:
                return current
            updated = connection.execute(
                """
                UPDATE mlbb_account_links
                SET player_name = ?, avatar_url = ?, country_code = ?,
                    last_validated_at = ?, last_used_at = ?, updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ? AND status = 'ACTIVE'
                RETURNING *
                """,
                (
                    player_name,
                    avatar_url,
                    country_code,
                    now,
                    now,
                    now,
                    guild_id,
                    discord_user_id,
                ),
            ).fetchone()
        return _link_from_row(updated) if updated is not None else None

    async def update_visibility(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        visibility: MlbbProfileVisibility,
        now: datetime,
    ) -> MlbbAccountLink | None:
        if visibility not in {
            MlbbProfileVisibility.PRIVATE,
            MlbbProfileVisibility.GUILD,
        }:
            raise ValueError("A visibilidade MLBB deve ser PRIVATE ou GUILD.")
        return await asyncio.to_thread(
            self._update_visibility_sync,
            guild_id,
            discord_user_id,
            visibility,
            now,
        )

    def _update_visibility_sync(
        self,
        guild_id: int,
        discord_user_id: int,
        visibility: MlbbProfileVisibility,
        now: datetime,
    ) -> MlbbAccountLink | None:
        with self._database.connection() as connection:
            current = self._get_link_with_connection(
                connection,
                guild_id,
                discord_user_id,
                for_update=True,
            )
            if current is None or current.status is not MlbbAccountLinkStatus.ACTIVE:
                return current
            updated = connection.execute(
                """
                UPDATE mlbb_account_links
                SET visibility = ?, updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ? AND status = 'ACTIVE'
                RETURNING *
                """,
                (
                    visibility.value,
                    now,
                    guild_id,
                    discord_user_id,
                ),
            ).fetchone()
        return _link_from_row(updated) if updated is not None else None

    async def revoke_link(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        return await asyncio.to_thread(
            self._revoke_link_sync, guild_id, discord_user_id, now
        )

    def _revoke_link_sync(
        self, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mlbb_account_links
                WHERE guild_id = ? AND discord_user_id = ? FOR UPDATE
                """,
                (guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                return None
            link = _link_from_row(row)
            if link.status is MlbbAccountLinkStatus.REVOKED:
                return link
            updated = connection.execute(
                """
                UPDATE mlbb_account_links
                SET status = 'REVOKED', encrypted_jwt = NULL, updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ? RETURNING *
                """,
                (now, guild_id, discord_user_id),
            ).fetchone()
        return _link_from_row(updated) if updated is not None else None

    async def mark_reauth_required(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        return await asyncio.to_thread(
            self._mark_reauth_required_sync, guild_id, discord_user_id, now
        )

    def _mark_reauth_required_sync(
        self, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        with self._database.connection() as connection:
            row = connection.execute(
                """
                UPDATE mlbb_account_links
                SET status = 'REAUTH_REQUIRED', updated_at = ?
                WHERE guild_id = ? AND discord_user_id = ? AND status = 'ACTIVE'
                RETURNING *
                """,
                (now, guild_id, discord_user_id),
            ).fetchone()
            if row is None:
                return self._get_link_with_connection(
                    connection, guild_id, discord_user_id
                )
        return _link_from_row(row)

    @staticmethod
    def _advisory_lock(connection: PostgresConnectionAdapter, key: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (key,)
        )

    @staticmethod
    def _set_attempt_status(
        connection: PostgresConnectionAdapter,
        attempt_id: UUID,
        status: MlbbAuthAttemptStatus,
        now: datetime,
    ) -> None:
        connection.execute(
            """
            UPDATE mlbb_auth_attempts
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status.value, now, attempt_id),
        )

    @staticmethod
    def _revoke_pending_link(
        connection: PostgresConnectionAdapter,
        attempt: MlbbAuthAttempt,
        now: datetime,
    ) -> None:
        if attempt.purpose is not MlbbAuthPurpose.LINK:
            return
        connection.execute(
            """
            UPDATE mlbb_account_links
            SET status = 'REVOKED', updated_at = ?
            WHERE guild_id = ? AND discord_user_id = ?
              AND role_id = ? AND zone_id = ? AND status = 'PENDING'
            """,
            (
                now,
                attempt.guild_id,
                attempt.discord_user_id,
                attempt.role_id,
                attempt.zone_id,
            ),
        )

    @staticmethod
    def _get_link_with_connection(
        connection: PostgresConnectionAdapter,
        guild_id: int,
        discord_user_id: int,
        *,
        for_update: bool = False,
    ) -> MlbbAccountLink | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = connection.execute(
            """
            SELECT * FROM mlbb_account_links
            WHERE guild_id = ? AND discord_user_id = ?
            """ + suffix,
            (guild_id, discord_user_id),
        ).fetchone()
        return _link_from_row(row) if row is not None else None

    @staticmethod
    def _can_discard_stale_link(
        connection: PostgresConnectionAdapter,
        link: MlbbAccountLink,
        now: datetime,
    ) -> bool:
        if link.status is MlbbAccountLinkStatus.REVOKED:
            return True
        if link.status is not MlbbAccountLinkStatus.PENDING:
            return False
        row = connection.execute(
            """
            SELECT 1 FROM mlbb_auth_attempts
            WHERE guild_id = ? AND discord_user_id = ?
              AND role_id = ? AND zone_id = ?
              AND status IN ('CREATED', 'CODE_SENT', 'VERIFYING')
              AND expires_at > ?
            LIMIT 1
            """,
            (
                link.guild_id,
                link.discord_user_id,
                link.role_id,
                link.zone_id,
                now,
            ),
        ).fetchone()
        return row is None


def _attempt_from_row(row: dict[str, Any]) -> MlbbAuthAttempt:
    return MlbbAuthAttempt(
        id=UUID(str(row["id"])),
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        role_id=int(row["role_id"]),
        zone_id=int(row["zone_id"]),
        purpose=MlbbAuthPurpose(str(row["purpose"])),
        status=MlbbAuthAttemptStatus(str(row["status"])),
        attempts=int(row["attempts"]),
        expires_at=_as_datetime(row["expires_at"]),
        code_sent_at=(
            _as_datetime(row["code_sent_at"])
            if row.get("code_sent_at") is not None
            else None
        ),
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
    )


def _link_from_row(row: dict[str, Any]) -> MlbbAccountLink:
    return MlbbAccountLink(
        guild_id=int(row["guild_id"]),
        discord_user_id=int(row["discord_user_id"]),
        role_id=int(row["role_id"]),
        zone_id=int(row["zone_id"]),
        player_name=_optional_str(row.get("player_name")),
        avatar_url=_optional_str(row.get("avatar_url")),
        country_code=_optional_str(row.get("country_code")),
        encrypted_jwt=_optional_str(row.get("encrypted_jwt")),
        status=MlbbAccountLinkStatus(str(row["status"])),
        visibility=MlbbProfileVisibility(str(row["visibility"])),
        verified_at=_optional_datetime(row.get("verified_at")),
        last_validated_at=_optional_datetime(row.get("last_validated_at")),
        last_used_at=_optional_datetime(row.get("last_used_at")),
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
    )


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _optional_datetime(value: object | None) -> datetime | None:
    return _as_datetime(value) if value is not None else None


def _optional_str(value: object | None) -> str | None:
    return str(value) if value is not None else None
