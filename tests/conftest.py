from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest
from dotenv import load_dotenv

from app.repositories.postgres_database import PostgresDatabase
from tests.postgres_support import set_test_database

load_dotenv()

_POSTGRES_MODULES = {
    "tests.test_blackjack_service",
    "tests.test_bolao_service",
    "tests.test_casino_service",
    "tests.test_economy_features",
    "tests.test_form_service",
    "tests.test_giveaway_service",
    "tests.test_match_bet_service",
    "tests.test_phase04_services",
    "tests.test_truco_service",
    "tests.test_uno_service",
}


@pytest.fixture(autouse=True)
async def isolated_postgres_schema(request: pytest.FixtureRequest):
    if request.module.__name__ not in _POSTGRES_MODULES:
        yield
        return

    psycopg = pytest.importorskip("psycopg")
    dsn = _postgres_test_dsn()
    schema = f"copenhague_test_{uuid.uuid4().hex}"
    database = PostgresDatabase(dsn, schema=schema, min_size=1, max_size=4)
    try:
        try:
            database.open_sync()
        except Exception as exc:
            pytest.skip(f"PostgreSQL de teste indisponivel: {exc}")
        set_test_database(database)
        yield
    finally:
        set_test_database(None)
        await database.close()
        try:
            with psycopg.connect(dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                connection.commit()
        except Exception:
            pass


def _postgres_test_dsn() -> str:
    explicit = os.getenv("POSTGRES_TEST_DSN") or os.getenv("POSTGRES_MIGRATION_DSN")
    if explicit:
        return explicit

    dsn = os.getenv(
        "POSTGRES_DSN",
        "postgresql://copenhague:copenhague@postgres:5432/copenhague",
    )
    parsed = urlsplit(dsn)
    username = parsed.username or "copenhague"
    password = parsed.password or "copenhague"
    port = os.getenv("POSTGRES_PORT", "5432")
    netloc = f"{username}:{password}@127.0.0.1:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
