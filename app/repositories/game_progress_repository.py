from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from app.models.casino import RaceMascot
from app.models.game_progress import (
    CollectiveRaceBet,
    CollectiveRaceBetCreate,
    CollectiveRaceBetStatus,
    CollectiveRaceCreate,
    CollectiveRaceSession,
    CollectiveRaceStatus,
    GameAchievement,
    JackpotState,
    SeasonalSetting,
    SeasonalTheme,
    UserGameAchievement,
)
from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.repositories.errors import RepositoryIntegrityError
from app.repositories.postgres_database import PostgresConnectionAdapter


class GameProgressRepositoryProtocol(Protocol):
    """Contrato de persistencia da fase 0.4."""

    async def ensure_achievement(
        self,
        achievement: GameAchievement,
    ) -> GameAchievement: ...

    async def update_achievement_reward(
        self,
        guild_id: int,
        achievement_key: str,
        reward_points: int,
    ) -> GameAchievement | None: ...

    async def unlock_achievement(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> tuple[UserGameAchievement | None, bool]: ...

    async def list_user_achievements(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]: ...

    async def reset_user_profile(
        self,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]: ...

    async def get_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState: ...

    async def add_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
        amount: int,
        *,
        cap: int,
    ) -> JackpotState: ...

    async def claim_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState: ...

    async def get_seasonal_theme(self, guild_id: int) -> SeasonalSetting: ...

    async def set_seasonal_theme(
        self,
        guild_id: int,
        theme: SeasonalTheme,
    ) -> SeasonalSetting: ...

    async def create_collective_race(
        self,
        data: CollectiveRaceCreate,
    ) -> CollectiveRaceSession: ...

    async def publish_collective_race(
        self,
        race_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> CollectiveRaceSession: ...

    async def get_collective_race(
        self,
        race_id: int,
    ) -> CollectiveRaceSession | None: ...

    async def list_open_collective_races(
        self,
        guild_id: int,
    ) -> list[CollectiveRaceSession]: ...

    async def create_collective_race_bet(
        self,
        data: CollectiveRaceBetCreate,
    ) -> CollectiveRaceBet: ...

    async def settle_collective_race(
        self,
        race_id: int,
        *,
        winner: RaceMascot | None,
        cancelled: bool,
    ) -> tuple[CollectiveRaceSession | None, list[CollectiveRaceBet]]: ...

    async def mark_collective_race_bet_paid(
        self,
        bet_id: int,
        *,
        transaction_id: int,
    ) -> CollectiveRaceBet | None: ...


class _GameProgressRepositoryImplementation:
    """Persistencia PostgreSQL para progresso social dos jogos."""

    async def ensure_achievement(
        self,
        achievement: GameAchievement,
    ) -> GameAchievement:
        return await asyncio.to_thread(self._ensure_achievement_sync, achievement)

    async def update_achievement_reward(
        self,
        guild_id: int,
        achievement_key: str,
        reward_points: int,
    ) -> GameAchievement | None:
        return await asyncio.to_thread(
            self._update_achievement_reward_sync,
            guild_id,
            achievement_key,
            reward_points,
        )

    async def unlock_achievement(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> tuple[UserGameAchievement | None, bool]:
        return await asyncio.to_thread(
            self._unlock_achievement_sync,
            guild_id,
            user_id,
            achievement_key,
        )

    async def list_user_achievements(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]:
        return await asyncio.to_thread(
            self._list_user_achievements_sync,
            guild_id,
            user_id,
        )

    async def reset_user_profile(
        self,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]:
        return await asyncio.to_thread(
            self._reset_user_profile_sync,
            guild_id,
            user_id,
        )

    async def get_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState:
        return await asyncio.to_thread(
            self._get_or_create_jackpot_sync,
            guild_id,
            jackpot_key,
        )

    async def add_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
        amount: int,
        *,
        cap: int,
    ) -> JackpotState:
        return await asyncio.to_thread(
            self._add_jackpot_sync,
            guild_id,
            jackpot_key,
            amount,
            cap,
        )

    async def claim_jackpot(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState:
        return await asyncio.to_thread(
            self._claim_jackpot_sync,
            guild_id,
            jackpot_key,
        )

    async def get_seasonal_theme(self, guild_id: int) -> SeasonalSetting:
        return await asyncio.to_thread(
            self._get_or_create_seasonal_theme_sync, guild_id
        )

    async def get_admin_summary(self, guild_id: int) -> dict[str, int]:
        return await asyncio.to_thread(self._get_admin_summary_sync, guild_id)

    async def set_seasonal_theme(
        self,
        guild_id: int,
        theme: SeasonalTheme,
    ) -> SeasonalSetting:
        return await asyncio.to_thread(
            self._set_seasonal_theme_sync,
            guild_id,
            theme,
        )

    async def create_collective_race(
        self,
        data: CollectiveRaceCreate,
    ) -> CollectiveRaceSession:
        return await asyncio.to_thread(self._create_collective_race_sync, data)

    async def publish_collective_race(
        self,
        race_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> CollectiveRaceSession:
        return await asyncio.to_thread(
            self._publish_collective_race_sync,
            race_id,
            channel_id,
            message_id,
        )

    async def get_collective_race(
        self,
        race_id: int,
    ) -> CollectiveRaceSession | None:
        return await asyncio.to_thread(self._get_collective_race_sync, race_id)

    async def list_open_collective_races(
        self,
        guild_id: int,
    ) -> list[CollectiveRaceSession]:
        return await asyncio.to_thread(
            self._list_open_collective_races_sync,
            guild_id,
        )

    async def create_collective_race_bet(
        self,
        data: CollectiveRaceBetCreate,
    ) -> CollectiveRaceBet:
        return await asyncio.to_thread(self._create_collective_race_bet_sync, data)

    async def settle_collective_race(
        self,
        race_id: int,
        *,
        winner: RaceMascot | None,
        cancelled: bool,
    ) -> tuple[CollectiveRaceSession | None, list[CollectiveRaceBet]]:
        return await asyncio.to_thread(
            self._settle_collective_race_sync,
            race_id,
            winner,
            cancelled,
        )

    async def mark_collective_race_bet_paid(
        self,
        bet_id: int,
        *,
        transaction_id: int,
    ) -> CollectiveRaceBet | None:
        return await asyncio.to_thread(
            self._mark_collective_race_bet_paid_sync,
            bet_id,
            transaction_id,
        )

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS game_achievements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        achievement_key TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        reward_points INTEGER NOT NULL DEFAULT 0,
                        reward_points_customized INTEGER NOT NULL DEFAULT 0,
                        badge_emoji TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        UNIQUE(guild_id, achievement_key)
                    )
                    """)
                self._ensure_column(
                    connection,
                    "game_achievements",
                    "reward_points_customized",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS user_game_achievements (
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        achievement_key TEXT NOT NULL,
                        unlocked_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id, achievement_key),
                        FOREIGN KEY(guild_id, achievement_key)
                            REFERENCES game_achievements(guild_id, achievement_key)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS game_jackpots (
                        guild_id INTEGER NOT NULL,
                        jackpot_key TEXT NOT NULL,
                        amount INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (guild_id, jackpot_key)
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS game_seasonal_settings (
                        guild_id INTEGER PRIMARY KEY,
                        theme TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS collective_races (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        stake INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        opened_by INTEGER NOT NULL,
                        opened_at TEXT NOT NULL,
                        closes_at TEXT NOT NULL,
                        winner TEXT,
                        finished_at TEXT
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS collective_race_bets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        race_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        mascot TEXT NOT NULL,
                        stake INTEGER NOT NULL,
                        potential_payout INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        debit_transaction_id INTEGER,
                        payout_transaction_id INTEGER,
                        economic_policy_json TEXT,
                        created_at TEXT NOT NULL,
                        settled_at TEXT,
                        FOREIGN KEY(race_id) REFERENCES collective_races(id)
                            ON DELETE CASCADE,
                        UNIQUE(race_id, user_id)
                    )
                    """)
                self._ensure_column(
                    connection,
                    "collective_race_bets",
                    "economic_policy_json",
                    "TEXT",
                )
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_collective_races_open
                    ON collective_races(guild_id, status, closes_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_collective_race_bets_race
                    ON collective_race_bets(race_id, status, created_at)
                    """)

    def _ensure_achievement_sync(
        self,
        achievement: GameAchievement,
    ) -> GameAchievement:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO game_achievements (
                        guild_id,
                        achievement_key,
                        name,
                        description,
                        reward_points,
                        badge_emoji,
                        is_active,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, achievement_key) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        reward_points = CASE
                            WHEN game_achievements.reward_points_customized = 1
                                THEN game_achievements.reward_points
                            ELSE excluded.reward_points
                        END,
                        badge_emoji = excluded.badge_emoji,
                        is_active = excluded.is_active
                    """,
                    (
                        achievement.guild_id,
                        achievement.achievement_key,
                        achievement.name,
                        achievement.description,
                        achievement.reward_points,
                        achievement.badge_emoji,
                        int(achievement.is_active),
                        serialize_datetime(achievement.created_at),
                    ),
                )
                connection.commit()

        ensured = self._get_achievement_sync(
            achievement.guild_id,
            achievement.achievement_key,
        )
        if ensured is None:
            raise RuntimeError("Nao foi possivel salvar a conquista.")
        return ensured

    def _update_achievement_reward_sync(
        self,
        guild_id: int,
        achievement_key: str,
        reward_points: int,
    ) -> GameAchievement | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE game_achievements
                    SET reward_points = ?,
                        reward_points_customized = 1
                    WHERE guild_id = ? AND achievement_key = ?
                    """,
                    (reward_points, guild_id, achievement_key),
                )
                connection.commit()

        if cursor.rowcount == 0:
            return None
        return self._get_achievement_sync(guild_id, achievement_key)

    def _unlock_achievement_sync(
        self,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> tuple[UserGameAchievement | None, bool]:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                achievement_row = self._get_achievement_row(
                    connection,
                    guild_id,
                    achievement_key,
                )
                if achievement_row is None or not bool(achievement_row["is_active"]):
                    connection.rollback()
                    return None, False

                existing_row = self._get_user_achievement_row(
                    connection,
                    guild_id,
                    user_id,
                    achievement_key,
                )
                if existing_row is not None:
                    connection.rollback()
                    return (
                        self._row_to_user_achievement(existing_row, achievement_row),
                        False,
                    )

                unlocked_at = serialize_datetime(utc_now())
                connection.execute(
                    """
                    INSERT INTO user_game_achievements (
                        guild_id,
                        user_id,
                        achievement_key,
                        unlocked_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (guild_id, user_id, achievement_key, unlocked_at),
                )
                connection.commit()

        achievement = self._get_achievement_sync(guild_id, achievement_key)
        if achievement is None:
            return None, False
        return (
            UserGameAchievement(
                guild_id=guild_id,
                user_id=user_id,
                achievement=achievement,
                unlocked_at=parse_datetime(unlocked_at),
            ),
            True,
        )

    def _list_user_achievements_sync(
        self,
        guild_id: int,
        user_id: int,
    ) -> list[UserGameAchievement]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        uga.guild_id,
                        uga.user_id,
                        uga.achievement_key,
                        uga.unlocked_at,
                        ga.name,
                        ga.description,
                        ga.reward_points,
                        ga.badge_emoji,
                        ga.is_active,
                        ga.created_at
                    FROM user_game_achievements uga
                    JOIN game_achievements ga
                      ON ga.guild_id = uga.guild_id
                     AND ga.achievement_key = uga.achievement_key
                    WHERE uga.guild_id = ? AND uga.user_id = ?
                    ORDER BY uga.unlocked_at ASC
                    """,
                    (guild_id, user_id),
                ).fetchall()

        return [
            UserGameAchievement(
                guild_id=int(row["guild_id"]),
                user_id=int(row["user_id"]),
                achievement=GameAchievement(
                    guild_id=int(row["guild_id"]),
                    achievement_key=str(row["achievement_key"]),
                    name=str(row["name"]),
                    description=str(row["description"]),
                    reward_points=int(row["reward_points"]),
                    badge_emoji=(
                        str(row["badge_emoji"]) if row["badge_emoji"] else None
                    ),
                    is_active=bool(row["is_active"]),
                    created_at=parse_datetime(str(row["created_at"])),
                ),
                unlocked_at=parse_datetime(str(row["unlocked_at"])),
            )
            for row in rows
        ]

    def _get_or_create_jackpot_sync(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_jackpot_row(connection, guild_id, jackpot_key)
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO game_jackpots (
                            guild_id,
                            jackpot_key,
                            amount,
                            updated_at
                        ) VALUES (?, ?, 0, ?)
                        """,
                        (guild_id, jackpot_key, now),
                    )
                    connection.commit()
                    row = self._get_jackpot_row(connection, guild_id, jackpot_key)
                else:
                    connection.rollback()
        return self._row_to_jackpot(row)

    def _add_jackpot_sync(
        self,
        guild_id: int,
        jackpot_key: str,
        amount: int,
        cap: int,
    ) -> JackpotState:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_jackpot_row(connection, guild_id, jackpot_key)
                current = int(row["amount"]) if row is not None else 0
                new_amount = min(max(0, cap), max(0, current + amount))
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO game_jackpots (
                            guild_id,
                            jackpot_key,
                            amount,
                            updated_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (guild_id, jackpot_key, new_amount, now),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE game_jackpots
                        SET amount = ?,
                            updated_at = ?
                        WHERE guild_id = ? AND jackpot_key = ?
                        """,
                        (new_amount, now, guild_id, jackpot_key),
                    )
                connection.commit()

        return self._get_or_create_jackpot_sync(guild_id, jackpot_key)

    def _claim_jackpot_sync(
        self,
        guild_id: int,
        jackpot_key: str,
    ) -> JackpotState:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_jackpot_row(connection, guild_id, jackpot_key)
                amount = int(row["amount"]) if row is not None else 0
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO game_jackpots (
                            guild_id,
                            jackpot_key,
                            amount,
                            updated_at
                        ) VALUES (?, ?, 0, ?)
                        """,
                        (guild_id, jackpot_key, now),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE game_jackpots
                        SET amount = 0,
                            updated_at = ?
                        WHERE guild_id = ? AND jackpot_key = ?
                        """,
                        (now, guild_id, jackpot_key),
                    )
                connection.commit()

        return JackpotState(
            guild_id=guild_id,
            jackpot_key=jackpot_key,
            amount=amount,
            updated_at=parse_datetime(now),
        )

    def _get_or_create_seasonal_theme_sync(self, guild_id: int) -> SeasonalSetting:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_seasonal_row(connection, guild_id)
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO game_seasonal_settings (
                            guild_id,
                            theme,
                            updated_at
                        ) VALUES (?, ?, ?)
                        """,
                        (guild_id, SeasonalTheme.NONE.value, now),
                    )
                    connection.commit()
                    row = self._get_seasonal_row(connection, guild_id)
                else:
                    connection.rollback()
        return self._row_to_seasonal(row)

    def _get_admin_summary_sync(self, guild_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as connection:
                achievement_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS unlocked_achievements,
                        COUNT(DISTINCT user_id) AS achievement_users
                    FROM user_game_achievements
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                race_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total_races,
                        COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0)
                            AS open_races,
                        COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0)
                            AS finished_races,
                        COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0)
                            AS cancelled_races
                    FROM collective_races
                    WHERE guild_id = ?
                    """,
                    (
                        CollectiveRaceStatus.OPEN.value,
                        CollectiveRaceStatus.FINISHED.value,
                        CollectiveRaceStatus.CANCELLED.value,
                        guild_id,
                    ),
                ).fetchone()
                race_bet_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS race_bets,
                        COALESCE(SUM(stake), 0) AS race_stake,
                        COALESCE(SUM(potential_payout), 0) AS race_payout
                    FROM collective_race_bets
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()

        return {
            "unlocked_achievements": int(achievement_row["unlocked_achievements"] or 0),
            "achievement_users": int(achievement_row["achievement_users"] or 0),
            "total_races": int(race_row["total_races"] or 0),
            "open_races": int(race_row["open_races"] or 0),
            "finished_races": int(race_row["finished_races"] or 0),
            "cancelled_races": int(race_row["cancelled_races"] or 0),
            "race_bets": int(race_bet_row["race_bets"] or 0),
            "race_stake": int(race_bet_row["race_stake"] or 0),
            "race_payout": int(race_bet_row["race_payout"] or 0),
        }

    def _reset_user_profile_sync(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                deleted_achievements = connection.execute(
                    """
                    DELETE FROM user_game_achievements
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                deleted_race_bets = connection.execute(
                    """
                    DELETE FROM collective_race_bets
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                connection.commit()

        return {
            "achievements": max(0, deleted_achievements),
            "collective_race_bets": max(0, deleted_race_bets),
        }

    def _set_seasonal_theme_sync(
        self,
        guild_id: int,
        theme: SeasonalTheme,
    ) -> SeasonalSetting:
        now = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO game_seasonal_settings (
                        guild_id,
                        theme,
                        updated_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        theme = excluded.theme,
                        updated_at = excluded.updated_at
                    """,
                    (guild_id, theme.value, now),
                )
                connection.commit()
        return self._get_or_create_seasonal_theme_sync(guild_id)

    def _create_collective_race_sync(
        self,
        data: CollectiveRaceCreate,
    ) -> CollectiveRaceSession:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO collective_races (
                        guild_id,
                        channel_id,
                        message_id,
                        stake,
                        status,
                        opened_by,
                        opened_at,
                        closes_at,
                        winner,
                        finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        data.guild_id,
                        data.channel_id,
                        data.message_id,
                        data.stake,
                        CollectiveRaceStatus.OPEN.value,
                        data.opened_by,
                        serialize_datetime(data.opened_at),
                        serialize_datetime(data.closes_at),
                    ),
                )
                race_id = int(cursor.lastrowid)
                connection.commit()

        race = self._get_collective_race_sync(race_id)
        if race is None:
            raise RuntimeError("Nao foi possivel recuperar a corrida criada.")
        return race

    def _publish_collective_race_sync(
        self,
        race_id: int,
        channel_id: int,
        message_id: int,
    ) -> CollectiveRaceSession:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE collective_races
                    SET channel_id = ?,
                        message_id = ?
                    WHERE id = ?
                    """,
                    (channel_id, message_id, race_id),
                )
                connection.commit()

        race = self._get_collective_race_sync(race_id)
        if race is None:
            raise RuntimeError("Nao foi possivel publicar a corrida.")
        return race

    def _get_collective_race_sync(
        self,
        race_id: int,
    ) -> CollectiveRaceSession | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_collective_race_row(connection, race_id)
        return self._row_to_collective_race(row) if row else None

    def _list_open_collective_races_sync(
        self,
        guild_id: int,
    ) -> list[CollectiveRaceSession]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM collective_races
                    WHERE guild_id = ? AND status = ?
                    ORDER BY closes_at ASC, id ASC
                    """,
                    (guild_id, CollectiveRaceStatus.OPEN.value),
                ).fetchall()
        return [self._row_to_collective_race(row) for row in rows]

    def _create_collective_race_bet_sync(
        self,
        data: CollectiveRaceBetCreate,
    ) -> CollectiveRaceBet:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                race_row = self._get_collective_race_row(connection, data.race_id)
                if race_row is None:
                    connection.rollback()
                    raise ValueError("Corrida coletiva nao encontrada.")
                race = self._row_to_collective_race(race_row)
                if race.status is not CollectiveRaceStatus.OPEN:
                    connection.rollback()
                    raise ValueError("Esta corrida nao aceita novas apostas.")

                try:
                    cursor = connection.execute(
                        """
                        INSERT INTO collective_race_bets (
                            race_id,
                            guild_id,
                            user_id,
                            mascot,
                            stake,
                            potential_payout,
                            status,
                            debit_transaction_id,
                            payout_transaction_id,
                            economic_policy_json,
                            created_at,
                            settled_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                        """,
                        (
                            data.race_id,
                            data.guild_id,
                            data.user_id,
                            data.mascot.value,
                            data.stake,
                            data.potential_payout,
                            CollectiveRaceBetStatus.OPEN.value,
                            data.debit_transaction_id,
                            json.dumps(
                                data.economic_policy_snapshot,
                                ensure_ascii=True,
                                allow_nan=False,
                            ),
                            serialize_datetime(data.created_at),
                        ),
                    )
                except RepositoryIntegrityError as exc:
                    connection.rollback()
                    raise ValueError("Voce ja apostou nesta corrida.") from exc

                bet_id = int(cursor.lastrowid)
                connection.commit()

        bet = self._get_collective_race_bet_sync(bet_id)
        if bet is None:
            raise RuntimeError("Nao foi possivel recuperar a aposta da corrida.")
        return bet

    def _settle_collective_race_sync(
        self,
        race_id: int,
        winner: RaceMascot | None,
        cancelled: bool,
    ) -> tuple[CollectiveRaceSession | None, list[CollectiveRaceBet]]:
        settled_at = serialize_datetime(utc_now())
        status = (
            CollectiveRaceStatus.CANCELLED
            if cancelled
            else CollectiveRaceStatus.FINISHED
        )
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_collective_race_row(connection, race_id)
                if row is None:
                    connection.rollback()
                    return None, []

                race = self._row_to_collective_race(row)
                if race.status is not CollectiveRaceStatus.OPEN:
                    connection.rollback()
                    return race, self._list_collective_race_bets_sync(race_id)

                connection.execute(
                    """
                    UPDATE collective_races
                    SET status = ?,
                        winner = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status.value,
                        winner.value if winner is not None else None,
                        settled_at,
                        race_id,
                    ),
                )
                if cancelled or winner is None:
                    connection.execute(
                        """
                        UPDATE collective_race_bets
                        SET status = ?,
                            settled_at = ?
                        WHERE race_id = ? AND status = ?
                        """,
                        (
                            CollectiveRaceBetStatus.REFUNDED.value,
                            settled_at,
                            race_id,
                            CollectiveRaceBetStatus.OPEN.value,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE collective_race_bets
                        SET status = CASE
                                WHEN mascot = ? THEN ?
                                ELSE ?
                            END,
                            settled_at = ?
                        WHERE race_id = ? AND status = ?
                        """,
                        (
                            winner.value,
                            CollectiveRaceBetStatus.WON.value,
                            CollectiveRaceBetStatus.LOST.value,
                            settled_at,
                            race_id,
                            CollectiveRaceBetStatus.OPEN.value,
                        ),
                    )
                connection.commit()

        return (
            self._get_collective_race_sync(race_id),
            self._list_collective_race_bets_sync(race_id),
        )

    def _mark_collective_race_bet_paid_sync(
        self,
        bet_id: int,
        transaction_id: int,
    ) -> CollectiveRaceBet | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_collective_race_bet_row(connection, bet_id)
                if row is None:
                    connection.rollback()
                    return None
                connection.execute(
                    """
                    UPDATE collective_race_bets
                    SET payout_transaction_id = ?
                    WHERE id = ?
                    """,
                    (transaction_id, bet_id),
                )
                connection.commit()

        return self._get_collective_race_bet_sync(bet_id)

    def _get_achievement_sync(
        self,
        guild_id: int,
        achievement_key: str,
    ) -> GameAchievement | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_achievement_row(
                    connection,
                    guild_id,
                    achievement_key,
                )
        return self._row_to_achievement(row) if row else None

    def _get_collective_race_bet_sync(
        self,
        bet_id: int,
    ) -> CollectiveRaceBet | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_collective_race_bet_row(connection, bet_id)
        return self._row_to_collective_race_bet(row) if row else None

    def _list_collective_race_bets_sync(
        self,
        race_id: int,
    ) -> list[CollectiveRaceBet]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM collective_race_bets
                    WHERE race_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (race_id,),
                ).fetchall()
        return [self._row_to_collective_race_bet(row) for row in rows]

    @staticmethod
    def _ensure_column(
        connection: PostgresConnectionAdapter,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(existing["name"] == column for existing in columns):
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _get_achievement_row(
        connection: PostgresConnectionAdapter,
        guild_id: int,
        achievement_key: str,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM game_achievements
            WHERE guild_id = ? AND achievement_key = ?
            """,
            (guild_id, achievement_key),
        ).fetchone()

    @staticmethod
    def _get_user_achievement_row(
        connection: PostgresConnectionAdapter,
        guild_id: int,
        user_id: int,
        achievement_key: str,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT
                uga.guild_id,
                uga.user_id,
                uga.achievement_key,
                uga.unlocked_at
            FROM user_game_achievements uga
            WHERE uga.guild_id = ?
              AND uga.user_id = ?
              AND uga.achievement_key = ?
            """,
            (guild_id, user_id, achievement_key),
        ).fetchone()

    @staticmethod
    def _get_jackpot_row(
        connection: PostgresConnectionAdapter,
        guild_id: int,
        jackpot_key: str,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM game_jackpots
            WHERE guild_id = ? AND jackpot_key = ?
            """,
            (guild_id, jackpot_key),
        ).fetchone()

    @staticmethod
    def _get_seasonal_row(
        connection: PostgresConnectionAdapter,
        guild_id: int,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM game_seasonal_settings
            WHERE guild_id = ?
            """,
            (guild_id,),
        ).fetchone()

    @staticmethod
    def _get_collective_race_row(
        connection: PostgresConnectionAdapter,
        race_id: int,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM collective_races
            WHERE id = ?
            """,
            (race_id,),
        ).fetchone()

    @staticmethod
    def _get_collective_race_bet_row(
        connection: PostgresConnectionAdapter,
        bet_id: int,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM collective_race_bets
            WHERE id = ?
            """,
            (bet_id,),
        ).fetchone()

    @staticmethod
    def _row_to_achievement(row: dict[str, Any]) -> GameAchievement:
        return GameAchievement(
            guild_id=int(row["guild_id"]),
            achievement_key=str(row["achievement_key"]),
            name=str(row["name"]),
            description=str(row["description"]),
            reward_points=int(row["reward_points"]),
            badge_emoji=str(row["badge_emoji"]) if row["badge_emoji"] else None,
            is_active=bool(row["is_active"]),
            created_at=parse_datetime(str(row["created_at"])),
        )

    def _row_to_user_achievement(
        self,
        user_row: dict[str, Any],
        achievement_row: dict[str, Any],
    ) -> UserGameAchievement:
        return UserGameAchievement(
            guild_id=int(user_row["guild_id"]),
            user_id=int(user_row["user_id"]),
            achievement=self._row_to_achievement(achievement_row),
            unlocked_at=parse_datetime(str(user_row["unlocked_at"])),
        )

    @staticmethod
    def _row_to_jackpot(row: dict[str, Any]) -> JackpotState:
        return JackpotState(
            guild_id=int(row["guild_id"]),
            jackpot_key=str(row["jackpot_key"]),
            amount=int(row["amount"]),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_seasonal(row: dict[str, Any]) -> SeasonalSetting:
        return SeasonalSetting(
            guild_id=int(row["guild_id"]),
            theme=SeasonalTheme(str(row["theme"])),
            updated_at=parse_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _row_to_collective_race(row: dict[str, Any]) -> CollectiveRaceSession:
        winner = row["winner"]
        finished_at = row["finished_at"]
        return CollectiveRaceSession(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            channel_id=(
                int(row["channel_id"]) if row["channel_id"] is not None else None
            ),
            message_id=(
                int(row["message_id"]) if row["message_id"] is not None else None
            ),
            stake=int(row["stake"]),
            status=CollectiveRaceStatus(str(row["status"])),
            opened_by=int(row["opened_by"]),
            opened_at=parse_datetime(str(row["opened_at"])),
            closes_at=parse_datetime(str(row["closes_at"])),
            winner=RaceMascot(str(winner)) if winner is not None else None,
            finished_at=parse_datetime(str(finished_at)) if finished_at else None,
        )

    @staticmethod
    def _row_to_collective_race_bet(row: dict[str, Any]) -> CollectiveRaceBet:
        settled_at = row["settled_at"]
        return CollectiveRaceBet(
            id=int(row["id"]),
            race_id=int(row["race_id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            mascot=RaceMascot(str(row["mascot"])),
            stake=int(row["stake"]),
            potential_payout=int(row["potential_payout"]),
            status=CollectiveRaceBetStatus(str(row["status"])),
            debit_transaction_id=(
                int(row["debit_transaction_id"])
                if row["debit_transaction_id"] is not None
                else None
            ),
            payout_transaction_id=(
                int(row["payout_transaction_id"])
                if row["payout_transaction_id"] is not None
                else None
            ),
            economic_policy_snapshot=(
                json.loads(str(row["economic_policy_json"]))
                if row.get("economic_policy_json") is not None
                else None
            ),
            created_at=parse_datetime(str(row["created_at"])),
            settled_at=parse_datetime(str(settled_at)) if settled_at else None,
        )
