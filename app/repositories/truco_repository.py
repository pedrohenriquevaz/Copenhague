from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.models.truco import TrucoActionType, TrucoGameStatus, TrucoSession


class TrucoRepositoryProtocol(Protocol):
    async def create_game(self, session: TrucoSession) -> TrucoSession: ...

    async def update_game(self, session: TrucoSession) -> TrucoSession: ...

    async def get_game(self, game_id: int) -> TrucoSession | None: ...

    async def get_game_by_message_id(self, message_id: int) -> TrucoSession | None: ...

    async def list_active_games_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[TrucoSession]: ...

    async def record_action(
        self,
        *,
        game_id: int,
        user_id: int | None,
        action_type: TrucoActionType,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def reset_user_profile(
        self, guild_id: int, user_id: int
    ) -> dict[str, int]: ...


class _TrucoRepositoryImplementation:
    """Persistencia de partidas de Truco."""

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS truco_games (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER,
                        status TEXT NOT NULL,
                        created_by INTEGER NOT NULL,
                        stake INTEGER NOT NULL,
                        player_ids_json TEXT NOT NULL,
                        accepted_user_ids_json TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        finished_at TEXT
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS truco_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        game_id INTEGER NOT NULL,
                        user_id INTEGER,
                        action_type TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(game_id) REFERENCES truco_games(id)
                    )
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_truco_games_guild_status
                    ON truco_games(guild_id, status, updated_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_truco_games_message
                    ON truco_games(message_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_truco_actions_game
                    ON truco_actions(game_id, created_at)
                    """)

    async def create_game(self, session: TrucoSession) -> TrucoSession:
        return await asyncio.to_thread(self._create_game_sync, session)

    async def update_game(self, session: TrucoSession) -> TrucoSession:
        return await asyncio.to_thread(self._update_game_sync, session)

    async def get_game(self, game_id: int) -> TrucoSession | None:
        return await asyncio.to_thread(self._get_game_sync, game_id)

    async def get_game_by_message_id(self, message_id: int) -> TrucoSession | None:
        return await asyncio.to_thread(self._get_game_by_message_id_sync, message_id)

    async def list_active_games_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[TrucoSession]:
        return await asyncio.to_thread(
            self._list_active_games_for_user_sync,
            guild_id,
            user_id,
        )

    async def record_action(
        self,
        *,
        game_id: int,
        user_id: int | None,
        action_type: TrucoActionType,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_action_sync,
            game_id,
            user_id,
            action_type,
            metadata or {},
        )

    async def reset_user_profile(self, guild_id: int, user_id: int) -> dict[str, int]:
        return await asyncio.to_thread(self._reset_user_profile_sync, guild_id, user_id)

    def _create_game_sync(self, session: TrucoSession) -> TrucoSession:
        now = utc_now()
        session.created_at = now
        session.updated_at = now
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO truco_games (
                        guild_id,
                        channel_id,
                        message_id,
                        status,
                        created_by,
                        stake,
                        player_ids_json,
                        accepted_user_ids_json,
                        snapshot_json,
                        created_at,
                        updated_at,
                        finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._game_params(session),
                )
                session.id = int(cursor.lastrowid)
                connection.execute(
                    """
                    UPDATE truco_games
                    SET snapshot_json = ?
                    WHERE id = ?
                    """,
                    (self._snapshot(session), session.id),
                )
        created = self._get_game_sync(session.id)
        if created is None:
            raise RuntimeError("Nao foi possivel criar a partida de Truco.")
        return created

    def _update_game_sync(self, session: TrucoSession) -> TrucoSession:
        if session.id is None:
            raise ValueError("Partida sem ID nao pode ser atualizada.")

        session.updated_at = utc_now()
        if session.status in {TrucoGameStatus.FINISHED, TrucoGameStatus.CANCELLED}:
            session.finished_at = session.finished_at or session.updated_at

        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE truco_games
                    SET guild_id = ?,
                        channel_id = ?,
                        message_id = ?,
                        status = ?,
                        created_by = ?,
                        stake = ?,
                        player_ids_json = ?,
                        accepted_user_ids_json = ?,
                        snapshot_json = ?,
                        created_at = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (*self._game_params(session), session.id),
                )
                if cursor.rowcount == 0:
                    raise ValueError("Partida de Truco nao encontrada.")

        updated = self._get_game_sync(session.id)
        if updated is None:
            raise RuntimeError("Nao foi possivel recuperar a partida de Truco.")
        return updated

    def _get_game_sync(self, game_id: int) -> TrucoSession | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM truco_games
                    WHERE id = ?
                    """,
                    (game_id,),
                ).fetchone()
        return self._row_to_game(row) if row else None

    def _get_game_by_message_id_sync(self, message_id: int) -> TrucoSession | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM truco_games
                    WHERE message_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (message_id,),
                ).fetchone()
        return self._row_to_game(row) if row else None

    def _list_active_games_for_user_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[TrucoSession]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM truco_games
                    WHERE guild_id = ?
                      AND status IN ('LOBBY', 'PLAYING')
                      AND player_ids_json LIKE ?
                    ORDER BY updated_at DESC
                    """,
                    (guild_id, f"%{user_id}%"),
                ).fetchall()
        games = [self._row_to_game(row) for row in rows]
        return [game for game in games if user_id in game.player_ids]

    def _record_action_sync(
        self,
        game_id: int,
        user_id: int | None,
        action_type: TrucoActionType,
        metadata: dict[str, Any],
    ) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO truco_actions (
                        game_id,
                        user_id,
                        action_type,
                        metadata_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        game_id,
                        user_id,
                        action_type.value,
                        json.dumps(metadata, ensure_ascii=False),
                        serialize_datetime(utc_now()),
                    ),
                )

    def _reset_user_profile_sync(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as connection:
                active_rows = connection.execute(
                    """
                    SELECT id
                    FROM truco_games
                    WHERE guild_id = ?
                      AND status IN ('LOBBY', 'PLAYING')
                      AND player_ids_json LIKE ?
                    """,
                    (guild_id, f"%{user_id}%"),
                ).fetchall()
        return {"active_games": len(active_rows)}

    def _game_params(self, session: TrucoSession) -> tuple[Any, ...]:
        return (
            session.guild_id,
            session.channel_id,
            session.message_id,
            session.status.value,
            session.created_by,
            session.stake,
            json.dumps(session.player_ids),
            json.dumps(sorted(session.accepted_user_ids)),
            self._snapshot(session),
            serialize_datetime(session.created_at or utc_now()),
            serialize_datetime(session.updated_at or utc_now()),
            (
                serialize_datetime(session.finished_at)
                if session.finished_at is not None
                else None
            ),
        )

    @staticmethod
    def _snapshot(session: TrucoSession) -> str:
        return json.dumps(session.to_dict(), ensure_ascii=False)

    @staticmethod
    def _row_to_game(row: dict[str, Any]) -> TrucoSession:
        data = json.loads(str(row["snapshot_json"]))
        data["id"] = int(row["id"])
        data["message_id"] = (
            int(row["message_id"]) if row["message_id"] is not None else None
        )
        data["status"] = str(row["status"])
        data["updated_at"] = parse_datetime(str(row["updated_at"])).isoformat()
        data["created_at"] = parse_datetime(str(row["created_at"])).isoformat()
        data["finished_at"] = (
            parse_datetime(str(row["finished_at"])).isoformat()
            if row["finished_at"] is not None
            else None
        )
        return TrucoSession.from_dict(data)
