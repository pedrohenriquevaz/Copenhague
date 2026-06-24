from __future__ import annotations

import gc
from pathlib import Path

import pytest

from app.models.bolao import BolaoGuessStatus
from app.repositories.bolao_repository import SQLiteBolaoRepository
from app.services.bolao_service import BolaoService, BolaoValidationError


async def test_bolao_service_creates_publishes_and_registers_guess() -> None:
    db_path = Path("tests") / "tmp_bolao.sqlite3"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = SQLiteBolaoRepository(db_path)
        service = BolaoService(repository)

        event = await service.create_event(
            title="Final da Copa",
            description="Palpite do placar final",
            prize="R$ 100",
            team_1="Brasil",
            team_2="Argentina",
            created_by=10,
            receiver_user_id=20,
        )
        assert event.id > 0
        assert event.is_active is True

        published = await service.publish_event(
            event.id,
            channel_id=123,
            message_id=456,
        )
        assert published.channel_id == 123
        assert published.message_id == 456

        result = await service.create_guess(event.id, 30, 2, 1)
        assert result.status is BolaoGuessStatus.SUCCESS
        assert result.guess is not None
        assert result.guess.score_team_1 == 2
        assert result.guess.score_team_2 == 1

        duplicate = await service.create_guess(event.id, 30, 3, 0)
        assert duplicate.status is BolaoGuessStatus.ALREADY_GUESSED
        assert duplicate.guess is not None
        assert duplicate.guess.score_team_1 == 2
        assert duplicate.guess.score_team_2 == 1
    finally:
        repository = None
        service = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_bolao_service_closes_and_lists_active_events() -> None:
    db_path = Path("tests") / "tmp_bolao_close.sqlite3"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = SQLiteBolaoRepository(db_path)
        service = BolaoService(repository)

        event = await service.create_event(
            title="Jogo",
            description="Descricao",
            prize="Premio",
            team_1="Time A",
            team_2="Time B",
            created_by=10,
            receiver_user_id=20,
        )

        active_events = await service.list_active_events()
        assert [item.id for item in active_events] == [event.id]

        closed = await service.close_event(event.id)
        assert closed.is_active is False

        active_events = await service.list_active_events()
        assert active_events == []

        result = await service.create_guess(event.id, 30, 1, 1)
        assert result.status is BolaoGuessStatus.EVENT_CLOSED
    finally:
        repository = None
        service = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_bolao_service_validates_input() -> None:
    db_path = Path("tests") / "tmp_bolao_validation.sqlite3"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = SQLiteBolaoRepository(db_path)
        service = BolaoService(repository)

        with pytest.raises(BolaoValidationError, match="titulo"):
            await service.create_event(
                title=" ",
                description="Descricao",
                prize="Premio",
                team_1="Time A",
                team_2="Time B",
                created_by=10,
                receiver_user_id=20,
            )

        with pytest.raises(BolaoValidationError, match="diferentes"):
            await service.create_event(
                title="Jogo",
                description="Descricao",
                prize="Premio",
                team_1="Time A",
                team_2="time a",
                created_by=10,
                receiver_user_id=20,
            )

        event = await service.create_event(
            title="Jogo",
            description="Descricao",
            prize="Premio",
            team_1="Time A",
            team_2="Time B",
            created_by=10,
            receiver_user_id=20,
        )

        with pytest.raises(BolaoValidationError, match="maximo"):
            await service.create_guess(event.id, 30, 100, 0)
    finally:
        repository = None
        service = None
        gc.collect()
        _cleanup_sqlite(db_path)


def _cleanup_sqlite(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
