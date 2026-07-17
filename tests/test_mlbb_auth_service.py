from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.integrations.mlbb.dto import MlbbLoginResult, MlbbPlayerProfile
from app.integrations.mlbb.errors import (
    MlbbInvalidVerificationCodeError,
    MlbbUnavailableError,
)
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
from app.services.mlbb_auth_service import (
    MlbbAccountInUseError,
    MlbbAccountMismatchError,
    MlbbAttemptExpiredError,
    MlbbAuthService,
    MlbbCooldownError,
    MlbbInvalidCodeError,
    MlbbProviderUnavailableError,
    MlbbTooManyAttemptsError,
    MlbbValidationError,
)
from app.services.mlbb_token_cipher import MlbbTokenCipher


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


class FakeMlbbClient:
    def __init__(self) -> None:
        self.jwt = "jwt-super-secreto"
        self.send_error: Exception | None = None
        self.login_error: Exception | None = None
        self.logout_error: Exception | None = None
        self.login_calls = 0
        self.logout_calls = 0
        self.sent_accounts: list[tuple[int, int]] = []
        self.login_started: asyncio.Event | None = None
        self.login_release: asyncio.Event | None = None
        self.login_result = MlbbLoginResult(
            jwt=self.jwt,
            role_id=123456789,
            zone_id=1234,
            authenticated_at=None,
        )
        self.profile = MlbbPlayerProfile(
            role_id=123456789,
            zone_id=1234,
            name="Jogador Teste",
            avatar_url="https://example.test/avatar.png",
            level=50,
            current_rank_code=None,
            highest_rank_code=None,
            country_code="BR",
        )

    async def send_verification_code(self, *, role_id: int, zone_id: int) -> None:
        self.sent_accounts.append((role_id, zone_id))
        if self.send_error is not None:
            raise self.send_error

    async def login(
        self, *, role_id: int, zone_id: int, verification_code: str
    ) -> MlbbLoginResult:
        self.login_calls += 1
        if self.login_started is not None:
            self.login_started.set()
        if self.login_release is not None:
            await self.login_release.wait()
        if self.login_error is not None:
            raise self.login_error
        return self.login_result

    async def get_user_info(self, *, jwt: str) -> MlbbPlayerProfile:
        return self.profile

    async def logout(self, *, jwt: str) -> None:
        self.logout_calls += 1
        if self.logout_error is not None:
            raise self.logout_error


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def record_audit_log(self, **kwargs: object) -> object:
        self.entries.append(kwargs)
        return object()


class FailingAuditRepository:
    async def record_audit_log(self, **kwargs: object) -> object:
        raise RuntimeError("jwt-super-secreto codigo-super-secreto")


class FakeCacheInvalidator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def invalidate_account(self, *, guild_id: int, discord_user_id: int) -> None:
        self.calls.append((guild_id, discord_user_id))


class InMemoryMlbbRepository:
    def __init__(self) -> None:
        self.attempt: MlbbAuthAttempt | None = None
        self.link: MlbbAccountLink | None = None
        self.account_in_use = False
        self.persisted_values: list[object] = []
        self._lock = asyncio.Lock()

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
        async with self._lock:
            if self.account_in_use:
                return MlbbBeginAttemptResult(MlbbBeginAttemptOutcome.ACCOUNT_IN_USE)
            if (
                self.attempt is not None
                and self.attempt.status is MlbbAuthAttemptStatus.CODE_SENT
                and self.attempt.expires_at > now
                and self.attempt.code_sent_at is not None
                and now
                < self.attempt.code_sent_at + timedelta(seconds=cooldown_seconds)
            ):
                remaining = int(
                    (
                        self.attempt.code_sent_at
                        + timedelta(seconds=cooldown_seconds)
                        - now
                    ).total_seconds()
                )
                return MlbbBeginAttemptResult(
                    MlbbBeginAttemptOutcome.COOLDOWN,
                    self.attempt,
                    max(1, remaining),
                )
            self.attempt = MlbbAuthAttempt(
                id=uuid4(),
                guild_id=guild_id,
                discord_user_id=discord_user_id,
                role_id=role_id,
                zone_id=zone_id,
                purpose=purpose,
                status=MlbbAuthAttemptStatus.CREATED,
                attempts=0,
                expires_at=expires_at,
                code_sent_at=None,
                created_at=now,
                updated_at=now,
            )
            self.persisted_values.append(self.attempt)
            if purpose is MlbbAuthPurpose.LINK:
                self.link = _make_link(
                    now=now,
                    guild_id=guild_id,
                    user_id=discord_user_id,
                    role_id=role_id,
                    zone_id=zone_id,
                    status=MlbbAccountLinkStatus.PENDING,
                    encrypted_jwt=None,
                    verified_at=None,
                )
            return MlbbBeginAttemptResult(MlbbBeginAttemptOutcome.CREATED, self.attempt)

    async def mark_code_sent(
        self,
        *,
        attempt_id: UUID,
        guild_id: int,
        discord_user_id: int,
        sent_at: datetime,
    ) -> MlbbAuthAttempt:
        assert self.attempt is not None
        self.attempt = replace(
            self.attempt,
            status=MlbbAuthAttemptStatus.CODE_SENT,
            code_sent_at=sent_at,
            updated_at=sent_at,
        )
        return self.attempt

    async def mark_send_failed(self, *, now: datetime, **kwargs: object) -> None:
        assert self.attempt is not None
        self.attempt = replace(
            self.attempt, status=MlbbAuthAttemptStatus.FAILED, updated_at=now
        )
        if self.link is not None and self.link.status is MlbbAccountLinkStatus.PENDING:
            self.link = replace(
                self.link, status=MlbbAccountLinkStatus.REVOKED, updated_at=now
            )

    async def claim_confirmation(
        self,
        *,
        guild_id: int,
        discord_user_id: int,
        now: datetime,
        max_attempts: int,
    ) -> MlbbClaimAttemptResult:
        async with self._lock:
            if self.attempt is None:
                return MlbbClaimAttemptResult(MlbbClaimAttemptOutcome.NOT_FOUND)
            if self.attempt.status is MlbbAuthAttemptStatus.VERIFIED:
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.ALREADY_VERIFIED,
                    self.attempt,
                    self.link,
                )
            if self.attempt.expires_at <= now:
                self.attempt = replace(
                    self.attempt,
                    status=MlbbAuthAttemptStatus.EXPIRED,
                    updated_at=now,
                )
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.EXPIRED, self.attempt
                )
            if self.attempt.attempts >= max_attempts:
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.TOO_MANY_ATTEMPTS, self.attempt
                )
            if self.attempt.status is MlbbAuthAttemptStatus.VERIFYING:
                return MlbbClaimAttemptResult(
                    MlbbClaimAttemptOutcome.IN_PROGRESS, self.attempt
                )
            if self.attempt.status is not MlbbAuthAttemptStatus.CODE_SENT:
                return MlbbClaimAttemptResult(MlbbClaimAttemptOutcome.NOT_FOUND)
            self.attempt = replace(
                self.attempt,
                status=MlbbAuthAttemptStatus.VERIFYING,
                updated_at=now,
            )
            return MlbbClaimAttemptResult(MlbbClaimAttemptOutcome.CLAIMED, self.attempt)

    async def record_confirmation_failure(
        self, *, now: datetime, max_attempts: int, **kwargs: object
    ) -> MlbbAuthAttempt:
        assert self.attempt is not None
        attempts = self.attempt.attempts + 1
        status = (
            MlbbAuthAttemptStatus.FAILED
            if attempts >= max_attempts
            else MlbbAuthAttemptStatus.CODE_SENT
        )
        self.attempt = replace(
            self.attempt, attempts=attempts, status=status, updated_at=now
        )
        return self.attempt

    async def release_confirmation(self, *, now: datetime, **kwargs: object) -> None:
        assert self.attempt is not None
        if self.attempt.status is MlbbAuthAttemptStatus.VERIFYING:
            self.attempt = replace(
                self.attempt,
                status=MlbbAuthAttemptStatus.CODE_SENT,
                updated_at=now,
            )

    async def fail_confirmation(self, *, now: datetime, **kwargs: object) -> None:
        assert self.attempt is not None
        self.attempt = replace(
            self.attempt, status=MlbbAuthAttemptStatus.FAILED, updated_at=now
        )

    async def complete_confirmation(
        self,
        *,
        role_id: int,
        zone_id: int,
        player_name: str,
        avatar_url: str | None,
        country_code: str | None,
        encrypted_jwt: str,
        now: datetime,
        **kwargs: object,
    ) -> MlbbCompleteAttemptResult:
        async with self._lock:
            assert self.attempt is not None
            if self.attempt.status is MlbbAuthAttemptStatus.VERIFIED:
                assert self.link is not None
                return MlbbCompleteAttemptResult(
                    MlbbCompleteAttemptOutcome.ALREADY_VERIFIED,
                    self.attempt,
                    self.link,
                )
            visibility = (
                self.link.visibility
                if self.link is not None
                else MlbbProfileVisibility.GUILD
            )
            created_at = self.link.created_at if self.link is not None else now
            self.link = MlbbAccountLink(
                guild_id=self.attempt.guild_id,
                discord_user_id=self.attempt.discord_user_id,
                role_id=role_id,
                zone_id=zone_id,
                player_name=player_name,
                avatar_url=avatar_url,
                country_code=country_code,
                encrypted_jwt=encrypted_jwt,
                status=MlbbAccountLinkStatus.ACTIVE,
                visibility=visibility,
                verified_at=now,
                last_validated_at=now,
                last_used_at=None,
                created_at=created_at,
                updated_at=now,
            )
            self.persisted_values.append(encrypted_jwt)
            self.attempt = replace(
                self.attempt,
                status=MlbbAuthAttemptStatus.VERIFIED,
                updated_at=now,
            )
            return MlbbCompleteAttemptResult(
                MlbbCompleteAttemptOutcome.COMPLETED,
                self.attempt,
                self.link,
            )

    async def get_link(
        self, *, guild_id: int, discord_user_id: int
    ) -> MlbbAccountLink | None:
        return self.link

    async def revoke_link(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        if self.link is None:
            return None
        self.link = replace(
            self.link,
            status=MlbbAccountLinkStatus.REVOKED,
            encrypted_jwt=None,
            updated_at=now,
        )
        return self.link

    async def mark_reauth_required(
        self, *, guild_id: int, discord_user_id: int, now: datetime
    ) -> MlbbAccountLink | None:
        if self.link is not None:
            self.link = replace(
                self.link,
                status=MlbbAccountLinkStatus.REAUTH_REQUIRED,
                updated_at=now,
            )
        return self.link


def _make_link(
    *,
    now: datetime,
    guild_id: int = 1,
    user_id: int = 2,
    role_id: int = 123456789,
    zone_id: int = 1234,
    status: MlbbAccountLinkStatus = MlbbAccountLinkStatus.ACTIVE,
    visibility: MlbbProfileVisibility = MlbbProfileVisibility.GUILD,
    encrypted_jwt: str | None = "encrypted",
    verified_at: datetime | None = None,
) -> MlbbAccountLink:
    return MlbbAccountLink(
        guild_id=guild_id,
        discord_user_id=user_id,
        role_id=role_id,
        zone_id=zone_id,
        player_name="Jogador Teste",
        avatar_url=None,
        country_code="BR",
        encrypted_jwt=encrypted_jwt,
        status=status,
        visibility=visibility,
        verified_at=verified_at or now,
        last_validated_at=verified_at or now,
        last_used_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def auth_parts() -> tuple[
    MlbbAuthService,
    InMemoryMlbbRepository,
    FakeMlbbClient,
    MlbbTokenCipher,
    MutableClock,
    FakeAuditRepository,
]:
    clock = MutableClock()
    repository = InMemoryMlbbRepository()
    client = FakeMlbbClient()
    cipher = MlbbTokenCipher([Fernet.generate_key().decode("ascii")])
    audit = FakeAuditRepository()
    service = MlbbAuthService(
        repository,
        client,  # type: ignore[arg-type]
        cipher,
        audit,
        enabled=True,
        clock=clock,
    )
    return service, repository, client, cipher, clock, audit


async def _start(service: MlbbAuthService) -> None:
    await service.start_link(
        guild_id=1,
        discord_user_id=2,
        role_id="123456789",
        zone_id="1234",
    )


@pytest.mark.asyncio
async def test_start_link_is_valid_and_does_not_persist_code(auth_parts) -> None:
    service, repository, client, _, _, audit = auth_parts

    result = await service.start_link(
        guild_id=1,
        discord_user_id=2,
        role_id="123456789",
        zone_id="1234",
    )

    assert result.expires_at.minute == 5
    assert client.sent_accounts == [(123456789, 1234)]
    assert repository.attempt is not None
    assert repository.attempt.status is MlbbAuthAttemptStatus.CODE_SENT
    assert all(
        "verification" not in repr(value).lower()
        for value in repository.persisted_values
    )
    assert audit.entries[-1]["action"] == "mlbb.link_code_sent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role_id", "zone_id"),
    [("", "1234"), ("abc", "1234"), ("1", "0"), ("1" * 20, "2")],
)
async def test_start_rejects_invalid_ids(
    auth_parts, role_id: str, zone_id: str
) -> None:
    service = auth_parts[0]
    with pytest.raises(MlbbValidationError):
        await service.start_link(
            guild_id=1,
            discord_user_id=2,
            role_id=role_id,
            zone_id=zone_id,
        )


@pytest.mark.asyncio
async def test_start_enforces_cooldown(auth_parts) -> None:
    service = auth_parts[0]
    await _start(service)

    with pytest.raises(MlbbCooldownError) as exc_info:
        await _start(service)

    assert exc_info.value.retry_after_seconds == 60


@pytest.mark.asyncio
async def test_send_failure_marks_attempt_and_surfaces_unavailable(auth_parts) -> None:
    service, repository, client, *_ = auth_parts
    client.send_error = MlbbUnavailableError("provider down")

    with pytest.raises(MlbbProviderUnavailableError):
        await _start(service)

    assert repository.attempt is not None
    assert repository.attempt.status is MlbbAuthAttemptStatus.FAILED
    assert repository.link is not None
    assert repository.link.status is MlbbAccountLinkStatus.REVOKED


@pytest.mark.asyncio
async def test_confirmation_expires_after_five_minutes(auth_parts) -> None:
    service, repository, _, _, clock, _ = auth_parts
    await _start(service)
    clock.value += timedelta(seconds=301)

    with pytest.raises(MlbbAttemptExpiredError):
        await service.confirm_link(
            guild_id=1, discord_user_id=2, verification_code="000000"
        )

    assert repository.attempt is not None
    assert repository.attempt.status is MlbbAuthAttemptStatus.EXPIRED


@pytest.mark.asyncio
async def test_invalid_code_increments_attempt_without_persisting_it(
    auth_parts,
) -> None:
    service, repository, client, *_ = auth_parts
    await _start(service)
    client.login_error = MlbbInvalidVerificationCodeError("rejected")

    with pytest.raises(MlbbInvalidCodeError) as exc_info:
        await service.confirm_link(
            guild_id=1,
            discord_user_id=2,
            verification_code="codigo-ultrassecreto",
        )

    assert exc_info.value.attempts_remaining == 4
    assert repository.attempt is not None
    assert repository.attempt.attempts == 1
    assert "codigo-ultrassecreto" not in repr(repository.persisted_values)


@pytest.mark.asyncio
async def test_confirmation_enforces_attempt_limit(auth_parts) -> None:
    service, repository, client, *_ = auth_parts
    await _start(service)
    assert repository.attempt is not None
    repository.attempt = replace(repository.attempt, attempts=4)
    client.login_error = MlbbInvalidVerificationCodeError("rejected")

    with pytest.raises(MlbbTooManyAttemptsError):
        await service.confirm_link(
            guild_id=1, discord_user_id=2, verification_code="000000"
        )

    assert repository.attempt.attempts == 5
    assert repository.attempt.status is MlbbAuthAttemptStatus.FAILED


@pytest.mark.asyncio
async def test_success_encrypts_jwt_and_returns_only_safe_summary(auth_parts) -> None:
    service, repository, client, cipher, _, audit = auth_parts
    await _start(service)

    result = await service.confirm_link(
        guild_id=1, discord_user_id=2, verification_code="000000"
    )

    assert result.account.player_name == "Jogador Teste"
    assert not hasattr(result.account, "encrypted_jwt")
    assert repository.link is not None
    assert repository.link.encrypted_jwt != client.jwt
    assert cipher.decrypt(repository.link.encrypted_jwt or "") == client.jwt
    assert audit.entries[-1]["action"] == "mlbb.link_verified"
    assert client.jwt not in repr(audit.entries)


@pytest.mark.asyncio
async def test_mismatch_rejects_link_and_logs_out_issued_session(auth_parts) -> None:
    service, repository, client, *_ = auth_parts
    await _start(service)
    client.profile = replace(client.profile, zone_id=9999)

    with pytest.raises(MlbbAccountMismatchError):
        await service.confirm_link(
            guild_id=1, discord_user_id=2, verification_code="000000"
        )

    assert repository.attempt is not None
    assert repository.attempt.status is MlbbAuthAttemptStatus.FAILED
    assert client.logout_calls == 1


@pytest.mark.asyncio
async def test_double_confirmation_is_idempotent(auth_parts) -> None:
    service, _, client, *_ = auth_parts
    await _start(service)

    first = await service.confirm_link(
        guild_id=1, discord_user_id=2, verification_code="000000"
    )
    second = await service.confirm_link(
        guild_id=1, discord_user_id=2, verification_code="000000"
    )

    assert first.already_verified is False
    assert second.already_verified is True
    assert client.login_calls == 1


@pytest.mark.asyncio
async def test_concurrent_confirmation_calls_login_only_once(auth_parts) -> None:
    service, _, client, *_ = auth_parts
    await _start(service)
    client.login_started = asyncio.Event()
    client.login_release = asyncio.Event()

    first_task = asyncio.create_task(
        service.confirm_link(guild_id=1, discord_user_id=2, verification_code="000000")
    )
    await client.login_started.wait()
    second_task = asyncio.create_task(
        service.confirm_link(guild_id=1, discord_user_id=2, verification_code="000000")
    )
    await asyncio.sleep(0)
    client.login_release.set()
    results = await asyncio.gather(first_task, second_task)

    assert client.login_calls == 1
    assert sorted(result.already_verified for result in results) == [False, True]


@pytest.mark.asyncio
async def test_duplicate_game_account_is_rejected_before_send(auth_parts) -> None:
    service, repository, client, *_ = auth_parts
    repository.account_in_use = True

    with pytest.raises(MlbbAccountInUseError):
        await _start(service)

    assert client.sent_accounts == []


@pytest.mark.asyncio
async def test_reauthentication_preserves_visibility(auth_parts) -> None:
    service, repository, _, cipher, clock, _ = auth_parts
    invalidator = FakeCacheInvalidator()
    service._cache_invalidator = invalidator
    repository.link = _make_link(
        now=clock.value,
        status=MlbbAccountLinkStatus.REAUTH_REQUIRED,
        visibility=MlbbProfileVisibility.PRIVATE,
        encrypted_jwt=cipher.encrypt("old-jwt"),
    )

    await service.start_reauthentication(guild_id=1, discord_user_id=2)
    result = await service.confirm_link(
        guild_id=1, discord_user_id=2, verification_code="000000"
    )

    assert result.account.status is MlbbAccountLinkStatus.ACTIVE
    assert result.account.visibility is MlbbProfileVisibility.PRIVATE
    assert invalidator.calls == [(1, 2)]


@pytest.mark.asyncio
async def test_unlink_revokes_locally_when_external_logout_fails(auth_parts) -> None:
    service, repository, client, cipher, clock, _ = auth_parts
    invalidator = FakeCacheInvalidator()
    service._cache_invalidator = invalidator
    repository.link = _make_link(
        now=clock.value, encrypted_jwt=cipher.encrypt(client.jwt)
    )
    client.logout_error = MlbbUnavailableError("provider down")

    result = await service.unlink(guild_id=1, discord_user_id=2)

    assert result.external_logout_succeeded is False
    assert repository.link is not None
    assert repository.link.status is MlbbAccountLinkStatus.REVOKED
    assert repository.link.encrypted_jwt is None
    assert invalidator.calls == [(1, 2)]


def test_token_cipher_does_not_expose_plaintext() -> None:
    cipher = MlbbTokenCipher([Fernet.generate_key().decode("ascii")])
    encrypted = cipher.encrypt("jwt-super-secreto")

    assert encrypted != "jwt-super-secreto"
    assert "jwt-super-secreto" not in encrypted
    assert cipher.decrypt(encrypted) == "jwt-super-secreto"


@pytest.mark.asyncio
async def test_disabled_feature_allows_local_unlink_without_external_call(
    auth_parts,
) -> None:
    _, repository, client, cipher, clock, audit = auth_parts
    repository.link = _make_link(
        now=clock.value, encrypted_jwt=cipher.encrypt(client.jwt)
    )
    service = MlbbAuthService(
        repository,
        client,  # type: ignore[arg-type]
        cipher,
        audit,
        enabled=False,
        clock=clock,
    )

    result = await service.unlink(guild_id=1, discord_user_id=2)

    assert result.account.status is MlbbAccountLinkStatus.REVOKED
    assert client.logout_calls == 0


@pytest.mark.asyncio
async def test_audit_failure_log_never_contains_provider_secrets(
    auth_parts, caplog
) -> None:
    _, repository, client, cipher, clock, _ = auth_parts
    service = MlbbAuthService(
        repository,
        client,  # type: ignore[arg-type]
        cipher,
        FailingAuditRepository(),
        enabled=True,
        clock=clock,
    )

    await _start(service)

    output = " ".join(record.getMessage() for record in caplog.records)
    assert "jwt-super-secreto" not in output
    assert "codigo-super-secreto" not in output
