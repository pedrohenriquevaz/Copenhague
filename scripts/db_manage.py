from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import psycopg
    from psycopg import sql
except ModuleNotFoundError:  # pragma: no cover - reported at command runtime.
    psycopg = None
    sql = None


DEFAULT_POSTGRES_DSN = "postgresql://copenhague:copenhague@127.0.0.1:5432/copenhague"
DEFAULT_SCHEMA = "copenhague"
MIGRATIONS_DIR = Path("sql/postgres/migrations")


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    serial: bool = False


TABLE_MANIFEST: tuple[TableSpec, ...] = (
    TableSpec("guild_settings"),
    TableSpec("user_wallets"),
    TableSpec("user_savings_accounts"),
    TableSpec("user_credit_protection"),
    TableSpec("activity_claim_cursors"),
    TableSpec("economy_reward_claims"),
    TableSpec("economy_transactions", True),
    TableSpec("shop_level_configs"),
    TableSpec("user_level_upgrades", True),
    TableSpec("native_message_stats"),
    TableSpec("native_voice_sessions", True),
    TableSpec("reward_items", True),
    TableSpec("reward_purchases", True),
    TableSpec("reward_codes", True),
    TableSpec("truco_games", True),
    TableSpec("truco_actions", True),
    TableSpec("uno_games", True),
    TableSpec("uno_actions", True),
    TableSpec("admin_audit_logs", True),
    TableSpec("game_achievements", True),
    TableSpec("user_game_achievements"),
    TableSpec("game_jackpots"),
    TableSpec("game_seasonal_settings"),
    TableSpec("collective_races", True),
    TableSpec("collective_race_bets", True),
    TableSpec("match_bet_matches", True),
    TableSpec("match_bet_tickets", True),
    TableSpec("bolao_events", True),
    TableSpec("bolao_guesses", True),
    TableSpec("forms", True),
    TableSpec("form_responses", True),
    TableSpec("giveaway_events", True),
    TableSpec("giveaway_codes", True),
    TableSpec("giveaway_claims", True),
    TableSpec("giveaway_user_tickets"),
)


def main() -> int:
    load_dotenv()
    args = parse_args()
    if psycopg is None or sql is None:
        print(
            "Dependencia ausente: instale `psycopg[binary,pool]>=3.2.0`.",
            file=sys.stderr,
        )
        return 2

    try:
        if args.command == "status":
            return command_status(args)
        if args.command == "upgrade":
            return command_upgrade(args)
        if args.command == "validate":
            return command_validate(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerencia o schema PostgreSQL do bot Copenhague.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.getenv("POSTGRES_MIGRATION_DSN") or DEFAULT_POSTGRES_DSN,
        help="DSN do Postgres de destino.",
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("POSTGRES_SCHEMA", DEFAULT_SCHEMA),
        help="Schema PostgreSQL de destino.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Mostra migrations aplicadas e pendentes.")
    subparsers.add_parser("upgrade", help="Aplica migrations pendentes.")
    subparsers.add_parser("validate", help="Valida tabelas, indices e sequencias.")

    return parser.parse_args()


def command_status(args: argparse.Namespace) -> int:
    with connect(args.postgres_dsn, args.schema) as connection:
        ensure_migrations_table(connection)
        applied = load_applied_migrations(connection)
        migrations = load_migrations()
        print(f"Schema: {args.schema}")
        if applied:
            latest = sorted(applied)[-1]
            print(f"Ultima migration aplicada: {latest}")
        else:
            print("Nenhuma migration aplicada.")
        pending = [
            migration.name for migration in migrations if migration.name not in applied
        ]
        if pending:
            print("Pendentes:")
            for version in pending:
                print(f"  - {version}")
        else:
            print("Sem migrations pendentes.")
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    with connect(args.postgres_dsn, args.schema) as connection:
        apply_migrations(connection)
    print(f"Schema `{args.schema}` atualizado.")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    with connect(args.postgres_dsn, args.schema) as connection:
        validate_schema(connection)
    print(f"Schema `{args.schema}` validado com sucesso.")
    return 0


@dataclass(frozen=True, slots=True)
class MigrationFile:
    name: str
    path: Path
    checksum: str


def load_migrations() -> list[MigrationFile]:
    if not MIGRATIONS_DIR.exists():
        raise SystemExit(f"Diretorio de migrations nao encontrado: {MIGRATIONS_DIR}")
    migrations: list[MigrationFile] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        content = path.read_bytes()
        migrations.append(
            MigrationFile(
                name=path.stem,
                path=path,
                checksum=hashlib.sha256(content).hexdigest(),
            )
        )
    if not migrations:
        raise SystemExit("Nenhuma migration PostgreSQL encontrada.")
    return migrations


def connect(
    dsn: str,
    schema: str,
    *,
    replace: bool = False,
) -> Any:
    connection = psycopg.connect(dsn)  # type: ignore[union-attr]
    with connection.cursor() as cursor:
        if replace:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
        )
        cursor.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
        )
    connection.commit()
    return connection


def health_check(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone()[0] != 1:
            raise RuntimeError("Postgres nao respondeu ao health check.")


def ensure_migrations_table(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """)
    connection.commit()


def load_applied_migrations(connection: Any) -> dict[str, str]:
    ensure_migrations_table(connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT version, checksum FROM schema_migrations")
        return {str(row[0]): str(row[1]) for row in cursor.fetchall()}


def apply_migrations(connection: Any) -> None:
    ensure_migrations_table(connection)
    applied = load_applied_migrations(connection)
    migrations = load_migrations()
    with connection.cursor() as cursor:
        for migration in migrations:
            current_checksum = applied.get(migration.name)
            if current_checksum == migration.checksum:
                continue
            if current_checksum is not None:
                raise RuntimeError(
                    "Checksum divergente para migration "
                    f"{migration.name}: banco={current_checksum}, "
                    f"arquivo={migration.checksum}."
                )
            cursor.execute(migration.path.read_text(encoding="utf-8"))
            cursor.execute(
                """
                INSERT INTO schema_migrations (version, checksum)
                VALUES (%s, %s)
                """,
                (migration.name, migration.checksum),
            )
            print(f"Migration aplicada: {migration.name}")
    connection.commit()


def validate_schema(connection: Any) -> None:
    missing_tables = find_missing_tables(connection)
    if missing_tables:
        raise RuntimeError("Tabelas ausentes: " + ", ".join(missing_tables))
    missing_indexes = find_missing_indexes(connection)
    if missing_indexes:
        raise RuntimeError("Indices ausentes: " + ", ".join(missing_indexes))
    validate_sequences(connection)


def find_missing_tables(connection: Any) -> list[str]:
    with connection.cursor() as cursor:
        missing = []
        for table in TABLE_MANIFEST:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = %s
                """,
                (table.name,),
            )
            if cursor.fetchone() is None:
                missing.append(table.name)
        return missing


EXPECTED_INDEXES = (
    "idx_economy_transactions_guild_user_created",
    "idx_economy_reward_claims_user",
    "idx_user_credit_protection_guild",
    "idx_user_savings_accounts_guild",
    "idx_native_voice_sessions_guild_user",
    "idx_native_voice_sessions_open",
    "idx_native_message_stats_guild_user",
    "idx_reward_items_guild_active",
    "idx_shop_level_configs_active",
    "idx_user_level_upgrades_user",
    "idx_reward_purchases_guild_user_created",
    "idx_reward_purchases_reward_user",
    "idx_truco_games_guild_status",
    "idx_truco_games_message",
    "idx_truco_actions_game",
    "idx_uno_games_guild_status",
    "idx_uno_games_channel",
    "idx_uno_games_message",
    "idx_uno_actions_game",
    "idx_collective_races_open",
    "idx_collective_race_bets_race",
    "idx_match_bet_matches_active",
    "idx_match_bet_matches_message",
    "idx_match_bet_tickets_match",
    "idx_match_bet_tickets_user",
    "idx_bolao_events_active",
    "idx_bolao_events_message",
    "idx_bolao_guesses_event_user",
    "idx_bolao_guesses_winning",
    "idx_forms_active",
    "idx_forms_active_published",
    "idx_form_responses_form_user",
    "idx_giveaway_codes_event_claimed",
    "idx_giveaway_claims_user_latest",
    "idx_giveaway_claims_event_user",
    "idx_giveaway_claims_event_reward",
    "idx_giveaway_tickets_event_user",
    "idx_giveaway_events_expires_at",
    "idx_giveaway_events_active_created",
    "idx_giveaway_events_active_published",
)


def find_missing_indexes(connection: Any) -> list[str]:
    with connection.cursor() as cursor:
        missing = []
        for index_name in EXPECTED_INDEXES:
            cursor.execute(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = %s
                """,
                (index_name,),
            )
            if cursor.fetchone() is None:
                missing.append(index_name)
        return missing


def validate_sequences(connection: Any) -> None:
    with connection.cursor() as cursor:
        for table in TABLE_MANIFEST:
            if not table.serial:
                continue
            cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table.name,))
            if cursor.fetchone()[0] is None:
                raise RuntimeError(f"Sequence ausente para {table.name}.id")


if __name__ == "__main__":
    raise SystemExit(main())
