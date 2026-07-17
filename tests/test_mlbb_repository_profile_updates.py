from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.models.mlbb import MlbbAccountLinkStatus, MlbbProfileVisibility
from app.repositories.mlbb_repository import PostgresMlbbRepository


class _Cursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _RecordingConnection:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> _RecordingConnection:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> _Cursor:
        self.calls.append((" ".join(query.split()), params or ()))
        return _Cursor(self._responses.pop(0))


class _RecordingDatabase:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self.connection_adapter = _RecordingConnection(responses)
        self.connection_calls = 0

    def connection(self) -> _RecordingConnection:
        self.connection_calls += 1
        return self.connection_adapter


def _link_row(
    *,
    status: MlbbAccountLinkStatus = MlbbAccountLinkStatus.ACTIVE,
    visibility: MlbbProfileVisibility = MlbbProfileVisibility.GUILD,
    player_name: str = "Jogador antigo",
    avatar_url: str | None = None,
    country_code: str | None = None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = updated_at or datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "guild_id": 101,
        "discord_user_id": 202,
        "role_id": 303,
        "zone_id": 404,
        "player_name": player_name,
        "avatar_url": avatar_url,
        "country_code": country_code,
        "encrypted_jwt": "ciphertext-only",
        "status": status.value,
        "visibility": visibility.value,
        "verified_at": timestamp,
        "last_validated_at": timestamp,
        "last_used_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


@pytest.mark.asyncio
async def test_update_profile_metadata_locks_active_link_and_returns_update() -> None:
    now = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)
    updated_row = _link_row(
        player_name="Jogador novo",
        avatar_url="https://example.invalid/avatar.png",
        country_code="BR",
        updated_at=now,
    )
    database = _RecordingDatabase([_link_row(), updated_row])
    repository = PostgresMlbbRepository(database)  # type: ignore[arg-type]

    result = await repository.update_profile_metadata(
        guild_id=101,
        discord_user_id=202,
        player_name="Jogador novo",
        avatar_url="https://example.invalid/avatar.png",
        country_code="BR",
        now=now,
    )

    assert result is not None
    assert result.player_name == "Jogador novo"
    assert result.avatar_url == "https://example.invalid/avatar.png"
    assert result.country_code == "BR"
    assert result.last_validated_at == now
    assert result.last_used_at == now
    assert result.updated_at == now
    select_query, select_params = database.connection_adapter.calls[0]
    update_query, update_params = database.connection_adapter.calls[1]
    assert "FOR UPDATE" in select_query
    assert "guild_id = ? AND discord_user_id = ?" in select_query
    assert select_params == (101, 202)
    assert "last_validated_at = ?, last_used_at = ?, updated_at = ?" in update_query
    assert "status = 'ACTIVE'" in update_query
    assert update_params == (
        "Jogador novo",
        "https://example.invalid/avatar.png",
        "BR",
        now,
        now,
        now,
        101,
        202,
    )


@pytest.mark.asyncio
async def test_update_profile_metadata_does_not_reanimate_revoked_link() -> None:
    database = _RecordingDatabase([_link_row(status=MlbbAccountLinkStatus.REVOKED)])
    repository = PostgresMlbbRepository(database)  # type: ignore[arg-type]

    result = await repository.update_profile_metadata(
        guild_id=101,
        discord_user_id=202,
        player_name="Nao deve persistir",
        avatar_url=None,
        country_code=None,
        now=datetime(2026, 2, 3, tzinfo=UTC),
    )

    assert result is not None
    assert result.status is MlbbAccountLinkStatus.REVOKED
    assert len(database.connection_adapter.calls) == 1
    assert "FOR UPDATE" in database.connection_adapter.calls[0][0]


@pytest.mark.asyncio
async def test_update_visibility_locks_active_link_and_accepts_private() -> None:
    now = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)
    updated_row = _link_row(
        visibility=MlbbProfileVisibility.PRIVATE,
        updated_at=now,
    )
    database = _RecordingDatabase([_link_row(), updated_row])
    repository = PostgresMlbbRepository(database)  # type: ignore[arg-type]

    result = await repository.update_visibility(
        guild_id=101,
        discord_user_id=202,
        visibility=MlbbProfileVisibility.PRIVATE,
        now=now,
    )

    assert result is not None
    assert result.visibility is MlbbProfileVisibility.PRIVATE
    assert result.updated_at == now
    select_query, _ = database.connection_adapter.calls[0]
    update_query, update_params = database.connection_adapter.calls[1]
    assert "FOR UPDATE" in select_query
    assert "SET visibility = ?, updated_at = ?" in update_query
    assert "status = 'ACTIVE'" in update_query
    assert update_params == ("PRIVATE", now, 101, 202)


@pytest.mark.asyncio
async def test_update_visibility_rejects_unsupported_public_value() -> None:
    database = _RecordingDatabase([])
    repository = PostgresMlbbRepository(database)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="PRIVATE ou GUILD"):
        await repository.update_visibility(
            guild_id=101,
            discord_user_id=202,
            visibility=MlbbProfileVisibility.PUBLIC,
            now=datetime(2026, 2, 3, tzinfo=UTC),
        )

    assert database.connection_calls == 0


@pytest.mark.asyncio
async def test_update_visibility_does_not_change_reauth_required_link() -> None:
    database = _RecordingDatabase(
        [_link_row(status=MlbbAccountLinkStatus.REAUTH_REQUIRED)]
    )
    repository = PostgresMlbbRepository(database)  # type: ignore[arg-type]

    result = await repository.update_visibility(
        guild_id=101,
        discord_user_id=202,
        visibility=MlbbProfileVisibility.PRIVATE,
        now=datetime(2026, 2, 3, tzinfo=UTC),
    )

    assert result is not None
    assert result.status is MlbbAccountLinkStatus.REAUTH_REQUIRED
    assert result.visibility is MlbbProfileVisibility.GUILD
    assert len(database.connection_adapter.calls) == 1
