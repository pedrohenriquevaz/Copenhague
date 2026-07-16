from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from app.models.giveaway import parse_datetime, serialize_datetime, utc_now
from app.models.match_bet import (
    MatchBetCreate,
    MatchBetMatch,
    MatchBetTeam,
    MatchBetTicket,
    MatchBetTicketCreate,
    MatchBetTicketStatus,
)
from app.repositories.postgres_database import PostgresConnectionAdapter


class MatchBetRepositoryProtocol(Protocol):
    """Contrato de persistencia do sistema de bets de partidas."""

    async def create_match(self, data: MatchBetCreate) -> MatchBetMatch: ...

    async def publish_match(
        self,
        match_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> MatchBetMatch: ...

    async def get_match(self, match_id: int) -> MatchBetMatch | None: ...

    async def get_match_by_message_id(
        self, message_id: int
    ) -> MatchBetMatch | None: ...

    async def list_active_matches(self, guild_id: int) -> list[MatchBetMatch]: ...

    async def reset_user_profile(
        self,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]: ...

    async def update_odds(
        self,
        match_id: int,
        *,
        odd_team_1_bps: int,
        odd_team_2_bps: int,
    ) -> MatchBetMatch | None: ...

    async def create_ticket(self, data: MatchBetTicketCreate) -> MatchBetTicket: ...

    async def settle_match(
        self,
        match_id: int,
        *,
        winner: MatchBetTeam | None,
    ) -> tuple[MatchBetMatch | None, list[MatchBetTicket]]: ...

    async def mark_ticket_paid(
        self,
        ticket_id: int,
        *,
        transaction_id: int,
    ) -> MatchBetTicket | None: ...


class _MatchBetRepositoryImplementation:
    """Persistencia PostgreSQL para partidas e apostas com odds."""

    async def create_match(self, data: MatchBetCreate) -> MatchBetMatch:
        return await asyncio.to_thread(self._create_match_sync, data)

    async def publish_match(
        self,
        match_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> MatchBetMatch:
        return await asyncio.to_thread(
            self._publish_match_sync,
            match_id,
            channel_id,
            message_id,
        )

    async def get_match(self, match_id: int) -> MatchBetMatch | None:
        return await asyncio.to_thread(self._get_match_sync, match_id)

    async def get_match_by_message_id(self, message_id: int) -> MatchBetMatch | None:
        return await asyncio.to_thread(self._get_match_by_message_id_sync, message_id)

    async def list_active_matches(self, guild_id: int) -> list[MatchBetMatch]:
        return await asyncio.to_thread(self._list_active_matches_sync, guild_id)

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

    async def get_admin_summary(self, guild_id: int) -> dict[str, int]:
        return await asyncio.to_thread(self._get_admin_summary_sync, guild_id)

    async def update_odds(
        self,
        match_id: int,
        *,
        odd_team_1_bps: int,
        odd_team_2_bps: int,
    ) -> MatchBetMatch | None:
        return await asyncio.to_thread(
            self._update_odds_sync,
            match_id,
            odd_team_1_bps,
            odd_team_2_bps,
        )

    async def create_ticket(self, data: MatchBetTicketCreate) -> MatchBetTicket:
        return await asyncio.to_thread(self._create_ticket_sync, data)

    async def settle_match(
        self,
        match_id: int,
        *,
        winner: MatchBetTeam | None,
    ) -> tuple[MatchBetMatch | None, list[MatchBetTicket]]:
        return await asyncio.to_thread(self._settle_match_sync, match_id, winner)

    async def mark_ticket_paid(
        self,
        ticket_id: int,
        *,
        transaction_id: int,
    ) -> MatchBetTicket | None:
        return await asyncio.to_thread(
            self._mark_ticket_paid_sync,
            ticket_id,
            transaction_id,
        )

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_bet_matches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        team_1 TEXT NOT NULL,
                        team_2 TEXT NOT NULL,
                        odd_team_1_bps INTEGER NOT NULL,
                        odd_team_2_bps INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        resolved_winner TEXT,
                        resolved_at TEXT
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS match_bet_tickets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        match_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        team TEXT NOT NULL,
                        team_name_snapshot TEXT NOT NULL,
                        stake INTEGER NOT NULL,
                        odd_bps INTEGER NOT NULL,
                        potential_payout INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        debit_transaction_id INTEGER,
                        payout_transaction_id INTEGER,
                        economic_policy_json TEXT,
                        created_at TEXT NOT NULL,
                        settled_at TEXT,
                        FOREIGN KEY(match_id) REFERENCES match_bet_matches(id)
                            ON DELETE CASCADE
                    )
                    """)
                connection.execute(
                    "ALTER TABLE match_bet_tickets "
                    "ADD COLUMN IF NOT EXISTS economic_policy_json TEXT"
                )
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_match_bet_matches_active
                    ON match_bet_matches(guild_id, is_active, created_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_match_bet_matches_message
                    ON match_bet_matches(message_id)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_match_bet_tickets_match
                    ON match_bet_tickets(match_id, status, created_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_match_bet_tickets_user
                    ON match_bet_tickets(guild_id, user_id, created_at)
                    """)

    def _create_match_sync(self, data: MatchBetCreate) -> MatchBetMatch:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO match_bet_matches (
                        guild_id,
                        title,
                        team_1,
                        team_2,
                        odd_team_1_bps,
                        odd_team_2_bps,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        resolved_winner,
                        resolved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, 1, NULL, NULL)
                    """,
                    (
                        data.guild_id,
                        data.title,
                        data.team_1,
                        data.team_2,
                        data.odd_team_1_bps,
                        data.odd_team_2_bps,
                        data.created_by,
                        serialize_datetime(data.created_at),
                    ),
                )
                match_id = int(cursor.lastrowid)
                connection.commit()

        match = self._get_match_sync(match_id)
        if match is None:
            raise RuntimeError("Nao foi possivel recuperar a partida criada.")
        return match

    def _publish_match_sync(
        self,
        match_id: int,
        channel_id: int,
        message_id: int,
    ) -> MatchBetMatch:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE match_bet_matches
                    SET channel_id = ?,
                        message_id = ?
                    WHERE id = ?
                    """,
                    (channel_id, message_id, match_id),
                )
                connection.commit()

        match = self._get_match_sync(match_id)
        if match is None:
            raise RuntimeError("Nao foi possivel publicar a partida.")
        return match

    def _get_match_sync(self, match_id: int) -> MatchBetMatch | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_match_row(connection, match_id)
        return self._row_to_match(row) if row else None

    def _get_match_by_message_id_sync(
        self,
        message_id: int,
    ) -> MatchBetMatch | None:
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM match_bet_matches
                    WHERE message_id = ?
                    """,
                    (message_id,),
                ).fetchone()
        return self._row_to_match(row) if row else None

    def _list_active_matches_sync(self, guild_id: int) -> list[MatchBetMatch]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM match_bet_matches
                    WHERE guild_id = ? AND is_active = 1
                    ORDER BY created_at DESC, id DESC
                    """,
                    (guild_id,),
                ).fetchall()
        return [self._row_to_match(row) for row in rows]

    def _get_admin_summary_sync(self, guild_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as connection:
                match_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total_matches,
                        COALESCE(SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), 0)
                            AS active_matches
                    FROM match_bet_matches
                    WHERE guild_id = ?
                    """,
                    (guild_id,),
                ).fetchone()
                ticket_rows = connection.execute(
                    """
                    SELECT
                        status,
                        COUNT(*) AS ticket_count,
                        COALESCE(SUM(stake), 0) AS total_stake,
                        COALESCE(SUM(potential_payout), 0) AS total_payout
                    FROM match_bet_tickets
                    WHERE guild_id = ?
                    GROUP BY status
                    """,
                    (guild_id,),
                ).fetchall()

        summary = {
            "total_matches": int(match_row["total_matches"] or 0),
            "active_matches": int(match_row["active_matches"] or 0),
            "total_tickets": 0,
            "open_tickets": 0,
            "won_tickets": 0,
            "lost_tickets": 0,
            "refunded_tickets": 0,
            "total_stake": 0,
            "potential_payout": 0,
        }
        status_key = {
            MatchBetTicketStatus.OPEN.value: "open_tickets",
            MatchBetTicketStatus.WON.value: "won_tickets",
            MatchBetTicketStatus.LOST.value: "lost_tickets",
            MatchBetTicketStatus.REFUNDED.value: "refunded_tickets",
        }
        for row in ticket_rows:
            ticket_count = int(row["ticket_count"] or 0)
            summary["total_tickets"] += ticket_count
            summary["total_stake"] += int(row["total_stake"] or 0)
            summary["potential_payout"] += int(row["total_payout"] or 0)
            key = status_key.get(str(row["status"]))
            if key:
                summary[key] = ticket_count
        return summary

    def _reset_user_profile_sync(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                deleted_tickets = connection.execute(
                    """
                    DELETE FROM match_bet_tickets
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                ).rowcount
                connection.commit()

        return {"match_bet_tickets": max(0, deleted_tickets)}

    def _update_odds_sync(
        self,
        match_id: int,
        odd_team_1_bps: int,
        odd_team_2_bps: int,
    ) -> MatchBetMatch | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_match_row(connection, match_id)
                if row is None:
                    connection.rollback()
                    return None
                match = self._row_to_match(row)
                if not match.is_active:
                    connection.rollback()
                    return match

                connection.execute(
                    """
                    UPDATE match_bet_matches
                    SET odd_team_1_bps = ?,
                        odd_team_2_bps = ?
                    WHERE id = ?
                    """,
                    (odd_team_1_bps, odd_team_2_bps, match_id),
                )
                connection.commit()

        return self._get_match_sync(match_id)

    def _create_ticket_sync(self, data: MatchBetTicketCreate) -> MatchBetTicket:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                match_row = self._get_match_row(connection, data.match_id)
                if match_row is None:
                    connection.rollback()
                    raise ValueError("Partida de apostas nao encontrada.")
                match = self._row_to_match(match_row)
                if not match.is_active:
                    connection.rollback()
                    raise ValueError("Esta partida nao aceita novas apostas.")

                cursor = connection.execute(
                    """
                    INSERT INTO match_bet_tickets (
                        match_id,
                        guild_id,
                        user_id,
                        team,
                        team_name_snapshot,
                        stake,
                        odd_bps,
                        potential_payout,
                        status,
                        debit_transaction_id,
                        payout_transaction_id,
                        economic_policy_json,
                        created_at,
                        settled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                    """,
                    (
                        data.match_id,
                        data.guild_id,
                        data.user_id,
                        data.team.value,
                        data.team_name_snapshot,
                        data.stake,
                        data.odd_bps,
                        data.potential_payout,
                        MatchBetTicketStatus.OPEN.value,
                        data.debit_transaction_id,
                        json.dumps(
                            data.economic_policy_snapshot,
                            ensure_ascii=True,
                            allow_nan=False,
                        ),
                        serialize_datetime(data.created_at),
                    ),
                )
                ticket_id = int(cursor.lastrowid)
                connection.commit()

        ticket = self._get_ticket_sync(ticket_id)
        if ticket is None:
            raise RuntimeError("Nao foi possivel recuperar a aposta criada.")
        return ticket

    def _settle_match_sync(
        self,
        match_id: int,
        winner: MatchBetTeam | None,
    ) -> tuple[MatchBetMatch | None, list[MatchBetTicket]]:
        settled_at = serialize_datetime(utc_now())
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_match_row(connection, match_id)
                if row is None:
                    connection.rollback()
                    return None, []

                match = self._row_to_match(row)
                if not match.is_active:
                    connection.rollback()
                    tickets = self._list_tickets_sync(match_id)
                    return match, tickets

                connection.execute(
                    """
                    UPDATE match_bet_matches
                    SET is_active = 0,
                        resolved_winner = ?,
                        resolved_at = ?
                    WHERE id = ?
                    """,
                    (winner.value if winner else None, settled_at, match_id),
                )

                if winner is None:
                    connection.execute(
                        """
                        UPDATE match_bet_tickets
                        SET status = ?,
                            settled_at = ?
                        WHERE match_id = ? AND status = ?
                        """,
                        (
                            MatchBetTicketStatus.REFUNDED.value,
                            settled_at,
                            match_id,
                            MatchBetTicketStatus.OPEN.value,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE match_bet_tickets
                        SET status = CASE
                                WHEN team = ? THEN ?
                                ELSE ?
                            END,
                            settled_at = ?
                        WHERE match_id = ? AND status = ?
                        """,
                        (
                            winner.value,
                            MatchBetTicketStatus.WON.value,
                            MatchBetTicketStatus.LOST.value,
                            settled_at,
                            match_id,
                            MatchBetTicketStatus.OPEN.value,
                        ),
                    )
                connection.commit()

        return self._get_match_sync(match_id), self._list_tickets_sync(match_id)

    def _mark_ticket_paid_sync(
        self,
        ticket_id: int,
        transaction_id: int,
    ) -> MatchBetTicket | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_ticket_row(connection, ticket_id)
                if row is None:
                    connection.rollback()
                    return None

                connection.execute(
                    """
                    UPDATE match_bet_tickets
                    SET payout_transaction_id = ?
                    WHERE id = ?
                    """,
                    (transaction_id, ticket_id),
                )
                connection.commit()

        return self._get_ticket_sync(ticket_id)

    def _get_ticket_sync(self, ticket_id: int) -> MatchBetTicket | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_ticket_row(connection, ticket_id)
        return self._row_to_ticket(row) if row else None

    def _list_tickets_sync(self, match_id: int) -> list[MatchBetTicket]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM match_bet_tickets
                    WHERE match_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (match_id,),
                ).fetchall()
        return [self._row_to_ticket(row) for row in rows]

    @staticmethod
    def _get_match_row(
        connection: PostgresConnectionAdapter,
        match_id: int,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM match_bet_matches
            WHERE id = ?
            """,
            (match_id,),
        ).fetchone()

    @staticmethod
    def _get_ticket_row(
        connection: PostgresConnectionAdapter,
        ticket_id: int,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT *
            FROM match_bet_tickets
            WHERE id = ?
            """,
            (ticket_id,),
        ).fetchone()

    @staticmethod
    def _row_to_match(row: dict[str, Any]) -> MatchBetMatch:
        resolved_winner = row["resolved_winner"]
        return MatchBetMatch(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            title=str(row["title"]),
            team_1=str(row["team_1"]),
            team_2=str(row["team_2"]),
            odd_team_1_bps=int(row["odd_team_1_bps"]),
            odd_team_2_bps=int(row["odd_team_2_bps"]),
            channel_id=(
                int(row["channel_id"]) if row["channel_id"] is not None else None
            ),
            message_id=(
                int(row["message_id"]) if row["message_id"] is not None else None
            ),
            created_by=int(row["created_by"]),
            created_at=parse_datetime(str(row["created_at"])),
            is_active=bool(row["is_active"]),
            resolved_winner=(
                MatchBetTeam(str(resolved_winner))
                if resolved_winner is not None
                else None
            ),
            resolved_at=(
                parse_datetime(str(row["resolved_at"]))
                if row["resolved_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _row_to_ticket(row: dict[str, Any]) -> MatchBetTicket:
        settled_at = row["settled_at"]
        return MatchBetTicket(
            id=int(row["id"]),
            match_id=int(row["match_id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            team=MatchBetTeam(str(row["team"])),
            team_name_snapshot=str(row["team_name_snapshot"]),
            stake=int(row["stake"]),
            odd_bps=int(row["odd_bps"]),
            potential_payout=int(row["potential_payout"]),
            status=MatchBetTicketStatus(str(row["status"])),
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
