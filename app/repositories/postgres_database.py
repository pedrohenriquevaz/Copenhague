from __future__ import annotations

import asyncio
import re
import selectors
import sqlite3
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from typing import Any

try:
    from psycopg import errors, sql
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
except ModuleNotFoundError:  # pragma: no cover - surfaced when postgres is selected.
    errors = None
    sql = None
    dict_row = None
    AsyncConnectionPool = None


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PRAGMA_TABLE_INFO_RE = re.compile(r"^PRAGMA\s+table_info\((?P<table>\w+)\)$", re.I)
_PRAGMA_INDEX_INFO_RE = re.compile(r"^PRAGMA\s+index_info\((?P<index>\w+)\)$", re.I)
_SERIAL_ID_TABLES = {
    "admin_audit_logs",
    "bolao_events",
    "bolao_guesses",
    "collective_race_bets",
    "collective_races",
    "economy_transactions",
    "form_responses",
    "forms",
    "game_achievements",
    "giveaway_claims",
    "giveaway_codes",
    "giveaway_events",
    "match_bet_matches",
    "match_bet_tickets",
    "native_voice_sessions",
    "reward_items",
    "reward_purchases",
    "truco_actions",
    "truco_games",
    "uno_actions",
    "uno_games",
    "user_level_upgrades",
}


class PostgresDatabase:
    """Shared PostgreSQL access backed by psycopg's async connection pool.

    The current repositories keep their public async API but run their sync
    persistence blocks in worker threads. This bridge keeps one async pool on a
    dedicated event loop and exposes a small DB-API-like surface to those blocks.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "copenhague",
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        if AsyncConnectionPool is None:
            raise RuntimeError(
                "Instale a dependencia `psycopg[binary,pool]>=3.2.0` "
                "para usar PostgreSQL."
            )
        if not _IDENTIFIER_RE.match(schema):
            raise ValueError(
                "POSTGRES_SCHEMA deve conter apenas letras, numeros e underscore."
            )
        self._dsn = dsn
        self._schema = schema
        self._min_size = min_size
        self._max_size = max(min_size, max_size)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pool: Any | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._start_lock = threading.Lock()
        self._closed = False

    @property
    def schema(self) -> str:
        return self._schema

    async def open(self) -> None:
        await asyncio.to_thread(self.open_sync)

    def open_sync(self) -> None:
        with self._start_lock:
            if self._closed:
                raise RuntimeError("Pool PostgreSQL ja foi encerrado.")
            if self._pool is not None:
                return
            self._thread = threading.Thread(
                target=self._run_loop,
                name="postgres-async-pool",
                daemon=True,
            )
            self._thread.start()
            self._started.wait(timeout=10)
            if self._loop is None:
                raise RuntimeError("Nao foi possivel iniciar o loop PostgreSQL.")
            self._run_coro(self._open_pool())

    async def close(self) -> None:
        await asyncio.to_thread(self.close_sync)

    def close_sync(self) -> None:
        with self._start_lock:
            self._closed = True
            if self._loop is None:
                return
            if self._pool is not None:
                self._run_coro(self._pool.close())
                self._pool = None
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=10)
                self._thread = None
            self._loop = None

    def connection(self) -> PostgresConnectionAdapter:
        self.open_sync()
        return PostgresConnectionAdapter(self)

    def _run_loop(self) -> None:
        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._started.set()
        loop.run_forever()
        loop.close()

    async def _open_pool(self) -> None:
        self._pool = AsyncConnectionPool(  # type: ignore[misc]
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await self._pool.open(wait=True)
        async with self._pool.connection() as connection:
            await connection.set_autocommit(True)
            await connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(  # type: ignore[union-attr]
                    sql.Identifier(self._schema)  # type: ignore[union-attr]
                )
            )
            await connection.execute(
                sql.SQL("SET search_path TO {}, public").format(  # type: ignore[union-attr]
                    sql.Identifier(self._schema)  # type: ignore[union-attr]
                )
            )
            await connection.set_autocommit(False)

    async def _get_connection(self) -> Any:
        if self._pool is None:
            raise RuntimeError("Pool PostgreSQL nao foi iniciado.")
        connection = await self._pool.getconn()
        await connection.set_autocommit(True)
        await connection.execute(
            sql.SQL("SET search_path TO {}, public").format(  # type: ignore[union-attr]
                sql.Identifier(self._schema)  # type: ignore[union-attr]
            )
        )
        await connection.set_autocommit(False)
        return connection

    async def _put_connection(self, connection: Any) -> None:
        if self._pool is None:
            return
        await self._pool.putconn(connection)

    def _run_coro(self, coro: Any) -> Any:
        if self._loop is None:
            raise RuntimeError("Loop PostgreSQL nao foi iniciado.")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()


class PostgresConnectionAdapter:
    """Minimal sqlite3-compatible connection facade over a pooled PG connection."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database
        self._connection: Any | None = None

    def __enter__(self) -> PostgresConnectionAdapter:
        self._connection = self._database._run_coro(self._database._get_connection())
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._connection is None:
            return
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            connection = self._connection
            self._connection = None
            self._database._run_coro(self._database._put_connection(connection))

    def execute(
        self,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> PostgresCursorAdapter:
        if self._connection is None:
            raise RuntimeError("Conexao PostgreSQL nao esta aberta.")

        pragma_cursor = self._handle_pragma(query)
        if pragma_cursor is not None:
            return pragma_cursor

        translated = _translate_sqlite_query(query)
        translated, captures_lastrowid = _add_returning_id_if_needed(translated)
        translated = _add_row_lock_if_needed(translated)
        try:
            cursor = self._database._run_coro(
                self._connection.execute(translated, tuple(params or ()))
            )
            return PostgresCursorAdapter(
                cursor,
                database=self._database,
                captures_lastrowid=captures_lastrowid,
            )
        except errors.IntegrityError as exc:  # type: ignore[union-attr]
            self.rollback()
            raise sqlite3.IntegrityError(str(exc)) from exc

    def executemany(
        self,
        query: str,
        param_sets: Sequence[Sequence[Any]],
    ) -> PostgresCursorAdapter:
        cursor = PostgresCursorAdapter.empty()
        for params in param_sets:
            cursor = self.execute(query, params)
        return cursor

    def commit(self) -> None:
        if self._connection is not None:
            self._database._run_coro(self._connection.commit())

    def rollback(self) -> None:
        if self._connection is not None:
            self._database._run_coro(self._connection.rollback())

    def _handle_pragma(self, query: str) -> PostgresCursorAdapter | None:
        normalized = " ".join(query.strip().split())
        if not normalized.upper().startswith("PRAGMA"):
            return None
        table_match = _PRAGMA_TABLE_INFO_RE.match(normalized)
        if table_match:
            rows = self._load_columns(table_match.group("table"))
            return PostgresCursorAdapter.from_rows(rows)
        if normalized.upper().startswith("PRAGMA INDEX_LIST"):
            return PostgresCursorAdapter.from_rows([])
        if _PRAGMA_INDEX_INFO_RE.match(normalized):
            return PostgresCursorAdapter.from_rows([])
        return PostgresCursorAdapter.from_rows([])

    def _load_columns(self, table_name: str) -> list[dict[str, Any]]:
        if self._connection is None:
            raise RuntimeError("Conexao PostgreSQL nao esta aberta.")
        cursor = self._database._run_coro(
            self._connection.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
        )
        return list(self._database._run_coro(cursor.fetchall()))


class PostgresCursorAdapter:
    def __init__(
        self,
        cursor: Any,
        database: PostgresDatabase | None = None,
        rows: list[dict[str, Any]] | None = None,
        *,
        captures_lastrowid: bool = False,
    ) -> None:
        self._cursor = cursor
        self._database = database
        self._rows = rows
        self._index = 0
        self._lastrowid: int | None = None
        if (
            captures_lastrowid
            and rows is None
            and cursor is not None
            and cursor.description is not None
        ):
            if database is None:
                raise RuntimeError("Cursor PostgreSQL sem database associado.")
            first = database._run_coro(cursor.fetchone())
            if first is not None and "id" in first:
                self._lastrowid = int(first["id"])
                self._rows = [first]

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> PostgresCursorAdapter:
        return cls(None, rows=rows)

    @classmethod
    def empty(cls) -> PostgresCursorAdapter:
        return cls(None, rows=[])

    @property
    def rowcount(self) -> int:
        if self._cursor is None:
            return len(self._rows or [])
        return int(self._cursor.rowcount)

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    def fetchone(self) -> dict[str, Any] | None:
        if self._rows is not None:
            if self._index >= len(self._rows):
                return None
            row = self._rows[self._index]
            self._index += 1
            return row
        if self._cursor is None:
            return None
        if self._database is None:
            raise RuntimeError("Cursor PostgreSQL sem database associado.")
        return self._database._run_coro(self._cursor.fetchone())

    def fetchall(self) -> list[dict[str, Any]]:
        if self._rows is not None:
            rows = self._rows[self._index :]
            self._index = len(self._rows)
            return rows
        if self._cursor is None:
            return []
        if self._database is None:
            raise RuntimeError("Cursor PostgreSQL sem database associado.")
        return list(self._database._run_coro(self._cursor.fetchall()))


def _translate_sqlite_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    upper = normalized.upper()
    if upper == "BEGIN IMMEDIATE":
        return "BEGIN"

    translated = query
    if upper.startswith("CREATE TABLE") or upper.startswith("ALTER TABLE"):
        translated = translated.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT",
            "BIGSERIAL PRIMARY KEY",
        )
        translated = re.sub(r"\bINTEGER\b", "BIGINT", translated)
    translated = translated.replace(
        "message_count = message_count + 1",
        "message_count = native_message_stats.message_count + 1",
    )
    translated = translated.replace(
        "extra_tickets = extra_tickets + excluded.extra_tickets",
        "extra_tickets = giveaway_user_tickets.extra_tickets "
        "+ excluded.extra_tickets",
    )
    translated = translated.replace("?", "%s")
    return translated


def _add_returning_id_if_needed(query: str) -> tuple[str, bool]:
    if "RETURNING" in query.upper():
        return query, False
    match = re.search(r"\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\b", query, re.I)
    if match is None:
        return query, False
    table = match.group(1).lower()
    if table not in _SERIAL_ID_TABLES:
        return query, False
    if " VALUES " not in f" {query.upper()} ":
        return query, False
    return f"{query.rstrip().rstrip(';')} RETURNING id", True


def _add_row_lock_if_needed(query: str) -> str:
    normalized = " ".join(query.strip().split())
    upper = normalized.upper()
    if not upper.startswith("SELECT") or " FOR UPDATE" in upper:
        return query
    if "COUNT(" in upper or "SUM(" in upper or "GROUP BY" in upper:
        return query
    lock_tables = (
        "FROM USER_WALLETS",
        "FROM USER_CREDIT_PROTECTION",
        "FROM USER_SAVINGS_ACCOUNTS",
        "FROM REWARD_ITEMS",
        "FROM GIVEAWAY_USER_TICKETS",
        "FROM MATCH_BET_MATCHES",
        "FROM COLLECTIVE_RACES",
        "FROM TRUCO_GAMES",
        "FROM UNO_GAMES",
        "FROM SHOP_LEVEL_CONFIGS",
        "FROM USER_LEVEL_UPGRADES",
    )
    if any(table in upper for table in lock_tables):
        return f"{query.rstrip().rstrip(';')} FOR UPDATE"
    if "FROM GIVEAWAY_CODES" in upper and "IS_CLAIMED = 0" in upper:
        return f"{query.rstrip().rstrip(';')} FOR UPDATE SKIP LOCKED"
    return query
