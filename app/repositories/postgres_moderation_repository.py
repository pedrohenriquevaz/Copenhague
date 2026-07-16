from __future__ import annotations

import asyncio
import json
import threading
from datetime import timedelta
from typing import Any

from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.models.moderation import (
    ModerationActionType,
    ModerationCase,
    ModerationCaseCreate,
    ModerationCaseOrigin,
    ModerationCaseStatus,
    ModerationSettings,
)
from app.repositories.postgres_database import PostgresDatabase


class PostgresModerationRepository:
    """Persistencia PostgreSQL isolada por guild para moderacao."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database
        self._lock = threading.RLock()

    def _connect(self):
        return self._database.connection()

    async def get_settings(self, guild_id: int) -> ModerationSettings:
        return await asyncio.to_thread(self._get_settings_sync, guild_id)

    async def add_authorized_role(self, guild_id: int, role_id: int) -> bool:
        return await asyncio.to_thread(self._add_role_sync, guild_id, role_id)

    async def remove_authorized_role(self, guild_id: int, role_id: int) -> bool:
        return await asyncio.to_thread(self._remove_role_sync, guild_id, role_id)

    async def set_log_channel(
        self, guild_id: int, channel_id: int | None
    ) -> ModerationSettings:
        return await asyncio.to_thread(self._set_log_channel_sync, guild_id, channel_id)

    async def create_case(self, case: ModerationCaseCreate) -> ModerationCase:
        return await asyncio.to_thread(self._create_case_sync, case)

    async def get_case(self, guild_id: int, case_id: int) -> ModerationCase | None:
        return await asyncio.to_thread(self._get_case_sync, guild_id, case_id)

    def _get_settings_sync(self, guild_id: int) -> ModerationSettings:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT log_channel_id FROM moderation_settings WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            roles = connection.execute(
                "SELECT role_id FROM moderation_authorized_roles "
                "WHERE guild_id = ? ORDER BY role_id",
                (guild_id,),
            ).fetchall()
        return ModerationSettings(
            guild_id=guild_id,
            authorized_role_ids=tuple(int(item["role_id"]) for item in roles),
            log_channel_id=(
                int(row["log_channel_id"])
                if row and row["log_channel_id"] is not None
                else None
            ),
        )

    def _ensure_settings(self, connection, guild_id: int) -> None:
        connection.execute(
            "INSERT INTO moderation_settings (guild_id, updated_at) VALUES (?, ?) "
            "ON CONFLICT (guild_id) DO NOTHING",
            (guild_id, serialize_datetime(utc_now())),
        )

    def _add_role_sync(self, guild_id: int, role_id: int) -> bool:
        with self._lock, self._connect() as connection:
            self._ensure_settings(connection, guild_id)
            cursor = connection.execute(
                """
                INSERT INTO moderation_authorized_roles (guild_id, role_id, created_at)
                VALUES (?, ?, ?) ON CONFLICT (guild_id, role_id) DO NOTHING
                """,
                (guild_id, role_id, serialize_datetime(utc_now())),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _remove_role_sync(self, guild_id: int, role_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM moderation_authorized_roles
                WHERE guild_id = ? AND role_id = ?
                """,
                (guild_id, role_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _set_log_channel_sync(
        self, guild_id: int, channel_id: int | None
    ) -> ModerationSettings:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO moderation_settings (guild_id, log_channel_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    log_channel_id = EXCLUDED.log_channel_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (guild_id, channel_id, serialize_datetime(utc_now())),
            )
            roles = connection.execute(
                "SELECT role_id FROM moderation_authorized_roles "
                "WHERE guild_id = ? ORDER BY role_id",
                (guild_id,),
            ).fetchall()
            settings = ModerationSettings(
                guild_id=guild_id,
                authorized_role_ids=tuple(int(item["role_id"]) for item in roles),
                log_channel_id=channel_id,
            )
            connection.commit()
            return settings

    def _create_case_sync(self, case: ModerationCaseCreate) -> ModerationCase:
        with self._lock, self._connect() as connection:
            created_at = serialize_datetime(utc_now())
            cursor = connection.execute(
                """
                INSERT INTO moderation_cases (
                    guild_id, action_type, target_user_id, moderator_user_id,
                    reason, created_at, duration_seconds, status, origin, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb)
                RETURNING *
                """,
                (
                    case.guild_id,
                    case.action_type.value,
                    case.target_user_id,
                    case.moderator_user_id,
                    case.reason,
                    created_at,
                    (
                        int(case.duration.total_seconds())
                        if case.duration is not None
                        else None
                    ),
                    case.status.value,
                    case.origin.value,
                    json.dumps(case.metadata),
                ),
            )
            row = cursor.fetchone()
            if row is None:  # pragma: no cover - protegido pelo RETURNING.
                connection.rollback()
                raise RuntimeError("Nao foi possivel criar o caso de moderacao.")
            created = self._row_to_case(row)
            connection.commit()
        return created

    def _get_case_sync(self, guild_id: int, case_id: int) -> ModerationCase | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM moderation_cases WHERE guild_id = ? AND id = ?",
                (guild_id, case_id),
            ).fetchone()
        return self._row_to_case(row) if row else None

    @staticmethod
    def _row_to_case(row: dict[str, Any]) -> ModerationCase:
        seconds = row["duration_seconds"]
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return ModerationCase(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            action_type=ModerationActionType(str(row["action_type"])),
            target_user_id=int(row["target_user_id"]),
            moderator_user_id=int(row["moderator_user_id"]),
            reason=str(row["reason"]),
            created_at=parse_datetime(str(row["created_at"])),
            duration=timedelta(seconds=int(seconds)) if seconds is not None else None,
            status=ModerationCaseStatus(str(row["status"])),
            origin=ModerationCaseOrigin(str(row["origin"])),
            metadata=dict(metadata or {}),
        )
