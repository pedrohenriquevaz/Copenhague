from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import aiohttp
import pytest

from app.integrations.mlbb.client import MlbbClient
from app.integrations.mlbb.errors import (
    MlbbInvalidResponseError,
    MlbbInvalidVerificationCodeError,
    MlbbRateLimitedError,
    MlbbSessionExpiredError,
    MlbbTimeoutError,
    MlbbUnavailableError,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "mlbb"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass(slots=True)
class FakeResponse:
    status: int
    payload: object
    headers: Mapping[str, str] = field(default_factory=dict)

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self, *, content_type: object = None) -> object:
        del content_type
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


@dataclass(slots=True)
class RaisingContext:
    error: BaseException

    async def __aenter__(self) -> None:
        raise self.error

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> object:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.outcomes:
            raise AssertionError("Nenhum resultado HTTP falso disponivel.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            return RaisingContext(outcome)
        return outcome


class StubSharedHttpClient:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.get_session_calls = 0

    async def get_session(self) -> FakeSession:
        self.get_session_calls += 1
        return self.session


def build_client(
    outcomes: list[FakeResponse | BaseException],
    *,
    max_retries: int = 0,
) -> tuple[MlbbClient, FakeSession, list[float]]:
    session = FakeSession(outcomes)
    shared = StubSharedHttpClient(session)
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    client = MlbbClient(
        shared,  # type: ignore[arg-type]
        base_url="https://mlbb.example.test/api",
        timeout_seconds=3,
        max_concurrent_requests=2,
        max_retries=max_retries,
        sleep=record_sleep,
        jitter=lambda _start, _end: 0.0,
    )
    return client, session, delays


@pytest.mark.asyncio
async def test_client_successfully_calls_every_phase_zero_endpoint() -> None:
    client, session, _ = build_client(
        [
            FakeResponse(200, load_fixture("auth_success.json")),
            FakeResponse(200, load_fixture("login_success.json")),
            FakeResponse(200, load_fixture("auth_success.json")),
            FakeResponse(200, load_fixture("user_info_success.json")),
            FakeResponse(200, load_fixture("user_stats_success.json")),
            FakeResponse(200, load_fixture("seasons_success.json")),
            FakeResponse(200, load_fixture("matches_success.json")),
            FakeResponse(200, load_fixture("match_details_success.json")),
            FakeResponse(200, load_fixture("frequent_heroes_success.json")),
        ]
    )

    await client.send_verification_code(role_id=123456789, zone_id=1234)
    login = await client.login(
        role_id=123456789,
        zone_id=1234,
        verification_code="fixture-vc-never-real",
    )
    await client.logout(jwt=login.jwt)
    profile = await client.get_user_info(jwt=login.jwt)
    stats = await client.get_user_stats(jwt=login.jwt)
    seasons = await client.get_seasons(jwt=login.jwt)
    matches = await client.get_matches(
        jwt=login.jwt,
        season_id=40,
        limit=10,
        cursor="9007199254740995",
    )
    details = await client.get_match_details(
        jwt=login.jwt,
        season_id=40,
        match_id="9007199254740993",
    )
    heroes = await client.get_frequent_heroes(
        jwt=login.jwt,
        season_id=40,
        limit=5,
        cursor=None,
    )

    assert profile.name == "Jogador Ficticio"
    assert stats.matches == 30
    assert seasons == (40, 39, 38)
    assert matches.matches[0].battle_id == "9007199254740993"
    assert details.participants[0].kills == 14
    assert heroes.heroes[0].wins == 7
    assert len(session.calls) == 9
    assert "Authorization" not in session.calls[0]["headers"]
    assert "Authorization" not in session.calls[1]["headers"]
    assert session.calls[2]["headers"]["Authorization"].startswith("Bearer ")
    assert session.calls[3]["params"] == {"lang": "pt"}
    assert session.calls[6]["params"]["last_cursor"] == "9007199254740995"
    assert session.calls[7]["url"].endswith("/user/matches/9007199254740993")
    assert "CopenhagueBot" in session.calls[0]["headers"]["User-Agent"]


@pytest.mark.asyncio
async def test_http_200_with_external_code_raises_typed_error() -> None:
    client, session, _ = build_client(
        [FakeResponse(200, load_fixture("error_code.json"))]
    )

    with pytest.raises(MlbbInvalidVerificationCodeError):
        await client.login(
            role_id=123456789,
            zone_id=1234,
            verification_code="fixture-invalid-vc",
        )

    assert len(session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_http_authentication_status_means_session_expired(status: int) -> None:
    client, _, _ = build_client([FakeResponse(status, {})])

    with pytest.raises(MlbbSessionExpiredError):
        await client.get_user_info(jwt="fixture.jwt.never-real")


@pytest.mark.asyncio
async def test_http_429_exposes_retry_after() -> None:
    client, session, _ = build_client([FakeResponse(429, {}, {"Retry-After": "3.5"})])

    with pytest.raises(MlbbRateLimitedError) as captured:
        await client.get_user_info(jwt="fixture.jwt.never-real")

    assert captured.value.retry_after == 3.5
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_http_429_is_retried_for_get_and_respects_retry_after() -> None:
    client, session, delays = build_client(
        [
            FakeResponse(429, {}, {"Retry-After": "2"}),
            FakeResponse(200, load_fixture("user_info_success.json")),
        ],
        max_retries=1,
    )

    profile = await client.get_user_info(jwt="fixture.jwt.never-real")

    assert profile.role_id == 123456789
    assert len(session.calls) == 2
    assert delays == [2.0]


@pytest.mark.asyncio
async def test_http_500_is_unavailable_without_retry() -> None:
    client, session, delays = build_client(
        [
            FakeResponse(500, {}),
            FakeResponse(200, load_fixture("user_info_success.json")),
        ],
        max_retries=2,
    )

    with pytest.raises(MlbbUnavailableError):
        await client.get_user_info(jwt="fixture.jwt.never-real")

    assert len(session.calls) == 1
    assert delays == []


@pytest.mark.asyncio
async def test_timeout_raises_typed_error() -> None:
    client, session, _ = build_client([TimeoutError()])

    with pytest.raises(MlbbTimeoutError):
        await client.get_user_info(jwt="fixture.jwt.never-real")

    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_invalid_json_raises_invalid_response() -> None:
    invalid_json = JSONDecodeError("invalid", "{", 0)
    client, _, _ = build_client([FakeResponse(200, invalid_json)])

    with pytest.raises(MlbbInvalidResponseError, match="JSON invalido"):
        await client.get_user_info(jwt="fixture.jwt.never-real")


@pytest.mark.asyncio
async def test_missing_required_field_raises_invalid_response() -> None:
    client, _, _ = build_client(
        [FakeResponse(200, {"code": 0, "data": {"roleId": 1, "zoneId": 2}})]
    )

    with pytest.raises(MlbbInvalidResponseError, match="name"):
        await client.get_user_info(jwt="fixture.jwt.never-real")


@pytest.mark.asyncio
async def test_retry_occurs_for_transient_get_only() -> None:
    get_client, get_session, get_delays = build_client(
        [
            FakeResponse(503, {}),
            FakeResponse(200, load_fixture("user_info_success.json")),
        ],
        max_retries=1,
    )

    profile = await get_client.get_user_info(jwt="fixture.jwt.never-real")

    assert profile.name == "Jogador Ficticio"
    assert len(get_session.calls) == 2
    assert get_delays == [0.25]

    post_client, post_session, post_delays = build_client(
        [
            FakeResponse(503, {}),
            FakeResponse(200, load_fixture("auth_success.json")),
        ],
        max_retries=2,
    )
    with pytest.raises(MlbbUnavailableError):
        await post_client.send_verification_code(role_id=123456789, zone_id=1234)

    assert len(post_session.calls) == 1
    assert post_delays == []


@pytest.mark.asyncio
async def test_login_is_never_retried() -> None:
    client, session, delays = build_client(
        [
            FakeResponse(503, {}),
            FakeResponse(200, load_fixture("login_success.json")),
        ],
        max_retries=2,
    )

    with pytest.raises(MlbbUnavailableError):
        await client.login(
            role_id=123456789,
            zone_id=1234,
            verification_code="fixture-vc-never-real",
        )

    assert len(session.calls) == 1
    assert delays == []


@pytest.mark.asyncio
async def test_network_error_is_retried_only_for_get() -> None:
    client, session, delays = build_client(
        [
            aiohttp.ClientConnectionError("fixture network failure"),
            FakeResponse(200, load_fixture("seasons_success.json")),
        ],
        max_retries=1,
    )

    seasons = await client.get_seasons(jwt="fixture.jwt.never-real")

    assert seasons == (40, 39, 38)
    assert len(session.calls) == 2
    assert delays == [0.25]


@pytest.mark.asyncio
async def test_logs_never_contain_credentials_or_verification_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = load_fixture("login_success.json")
    client, _, _ = build_client([FakeResponse(200, payload)])
    verification_code = "fixture-vc-must-not-be-logged"
    caplog.set_level(logging.INFO, logger="app.integrations.mlbb.client")

    result = await client.login(
        role_id=123456789,
        zone_id=1234,
        verification_code=verification_code,
    )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert result.jwt == "fixture.jwt.never-real"
    assert verification_code not in messages
    assert result.jwt not in messages
    assert payload["data"]["token"] not in messages
    assert "Authorization" not in messages
    assert "fixture-login-trace" in messages
