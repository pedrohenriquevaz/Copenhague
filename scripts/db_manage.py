from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
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
DEFAULT_CHUNK_SIZE = 500
MIGRATIONS_DIR = Path("sql/postgres/migrations")


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    env_var: str
    default_path: str
    serial: bool = False

    @property
    def path(self) -> Path:
        return Path(os.getenv(self.env_var, self.default_path))


TABLE_MANIFEST: tuple[TableSpec, ...] = (
    TableSpec("guild_settings", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("user_wallets", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("activity_claim_cursors", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("economy_reward_claims", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("economy_transactions", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("shop_level_configs", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("user_level_upgrades", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("native_message_stats", "ECONOMY_DB_PATH", "data/economy.sqlite3"),
    TableSpec("native_voice_sessions", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("reward_items", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("reward_purchases", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("reward_codes", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("admin_audit_logs", "ECONOMY_DB_PATH", "data/economy.sqlite3", True),
    TableSpec("game_achievements", "GAME_PROGRESS_DB_PATH", "data/bot.db", True),
    TableSpec("user_game_achievements", "GAME_PROGRESS_DB_PATH", "data/bot.db"),
    TableSpec("game_jackpots", "GAME_PROGRESS_DB_PATH", "data/bot.db"),
    TableSpec("game_seasonal_settings", "GAME_PROGRESS_DB_PATH", "data/bot.db"),
    TableSpec("collective_races", "GAME_PROGRESS_DB_PATH", "data/bot.db", True),
    TableSpec("collective_race_bets", "GAME_PROGRESS_DB_PATH", "data/bot.db", True),
    TableSpec("match_bet_matches", "MATCH_BET_DB_PATH", "data/bot.db", True),
    TableSpec("match_bet_tickets", "MATCH_BET_DB_PATH", "data/bot.db", True),
    TableSpec("bolao_events", "BOLAO_DB_PATH", "data/bot.db", True),
    TableSpec("bolao_guesses", "BOLAO_DB_PATH", "data/bot.db", True),
    TableSpec("forms", "FORM_DB_PATH", "data/bot.db", True),
    TableSpec("form_responses", "FORM_DB_PATH", "data/bot.db", True),
    TableSpec("giveaway_events", "GIVEAWAY_DB_PATH", "data/giveaways.sqlite3", True),
    TableSpec("giveaway_codes", "GIVEAWAY_DB_PATH", "data/giveaways.sqlite3", True),
    TableSpec("giveaway_claims", "GIVEAWAY_DB_PATH", "data/giveaways.sqlite3", True),
    TableSpec("giveaway_user_tickets", "GIVEAWAY_DB_PATH", "data/giveaways.sqlite3"),
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
        if args.command == "migrate-sqlite":
            return command_migrate_sqlite(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerencia schema e migracao PostgreSQL do bot Copenhague.",
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

    migrate = subparsers.add_parser(
        "migrate-sqlite",
        help="Copia dados SQLite para Postgres com validacao de contagens.",
    )
    migrate.add_argument(
        "--replace",
        action="store_true",
        help="Remove e recria o schema antes de migrar.",
    )
    migrate.add_argument(
        "--no-backup",
        action="store_true",
        help="Nao cria ZIP dos arquivos SQLite antes da migracao.",
    )
    migrate.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Diretorio para o ZIP de backup SQLite.",
    )
    migrate.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Linhas copiadas por lote.",
    )
    migrate.add_argument(
        "--skip-schema-refresh",
        action="store_true",
        help="Nao inicializa os schemas SQLite antes da copia.",
    )
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
            migration.name
            for migration in migrations
            if migration.name not in applied
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


def command_migrate_sqlite(args: argparse.Namespace) -> int:
    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size precisa ser maior que zero.")

    with connect(args.postgres_dsn, args.schema) as connection:
        health_check(connection)

    if not args.skip_schema_refresh:
        refresh_sqlite_schemas()

    existing_sources = existing_sqlite_sources()
    if not existing_sources:
        raise SystemExit("Nenhum arquivo SQLite encontrado para migrar.")

    if not args.no_backup:
        backup_path = backup_sqlite_files(existing_sources, args.backup_dir)
        print(f"Backup SQLite criado em: {backup_path}")

    with connect(args.postgres_dsn, args.schema, replace=args.replace) as connection:
        apply_migrations(connection)
        copy_manifest_data(connection, args.chunk_size)
        reset_sequences(connection)
        validate_schema(connection)
        validate_row_counts(connection)

    print("Migracao SQLite -> Postgres concluida com contagens conferidas.")
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
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


def refresh_sqlite_schemas() -> None:
    from app.repositories.bolao_repository import SQLiteBolaoRepository
    from app.repositories.economy_repository import SQLiteEconomyRepository
    from app.repositories.form_repository import SQLiteFormRepository
    from app.repositories.game_progress_repository import SQLiteGameProgressRepository
    from app.repositories.giveaway_repository import SQLiteGiveawayRepository
    from app.repositories.match_bet_repository import SQLiteMatchBetRepository

    factories = (
        (
            Path(os.getenv("ECONOMY_DB_PATH", "data/economy.sqlite3")),
            SQLiteEconomyRepository,
        ),
        (Path(os.getenv("BOLAO_DB_PATH", "data/bot.db")), SQLiteBolaoRepository),
        (Path(os.getenv("MATCH_BET_DB_PATH", "data/bot.db")), SQLiteMatchBetRepository),
        (
            Path(os.getenv("GAME_PROGRESS_DB_PATH", "data/bot.db")),
            SQLiteGameProgressRepository,
        ),
        (Path(os.getenv("FORM_DB_PATH", "data/bot.db")), SQLiteFormRepository),
        (
            Path(os.getenv("GIVEAWAY_DB_PATH", "data/giveaways.sqlite3")),
            SQLiteGiveawayRepository,
        ),
    )
    for path, factory in factories:
        if path.exists():
            factory(path)


def existing_sqlite_sources() -> list[Path]:
    paths: dict[Path, Path] = {}
    for table in TABLE_MANIFEST:
        path = table.path
        if path.exists():
            paths[path.resolve()] = path
    return list(paths.values())


def backup_sqlite_files(paths: Sequence[Path], backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"sqlite-before-postgres-{timestamp}.zip"
    cwd = Path.cwd().resolve()
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for db_path in paths:
            for file_path in sqlite_related_files(db_path):
                archive.write(file_path, arcname=archive_name(file_path, cwd))
    return backup_path


def sqlite_related_files(db_path: Path) -> Iterable[Path]:
    yield from (
        candidate
        for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
        if candidate.exists()
    )


def archive_name(path: Path, cwd: Path) -> str:
    try:
        return str(path.resolve().relative_to(cwd)).replace("\\", "/")
    except ValueError:
        return path.name


def copy_manifest_data(connection: Any, chunk_size: int) -> None:
    for table in TABLE_MANIFEST:
        copied = copy_table(connection, table, chunk_size)
        print(f"{table.name}: {copied} linha(s) copiadas.")
    connection.commit()


def copy_table(connection: Any, table: TableSpec, chunk_size: int) -> int:
    if not table.path.exists() or not sqlite_table_exists(table.path, table.name):
        return 0
    with sqlite3.connect(table.path) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        columns = sqlite_columns(sqlite_connection, table.name)
        if not columns:
            return 0
        selected_columns = ", ".join(quote_sqlite_identifier(c) for c in columns)
        select_sql = (
            f"SELECT {selected_columns} "
            f"FROM {quote_sqlite_identifier(table.name)}"
        )
        rows = sqlite_connection.execute(select_sql)
        inserted = 0
        while True:
            batch = rows.fetchmany(chunk_size)
            if not batch:
                break
            insert_rows(connection, table.name, columns, batch)
            inserted += len(batch)
        return inserted


def sqlite_table_exists(path: Path, table_name: str) -> bool:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
    return row is not None


def sqlite_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(
        f"PRAGMA table_info({quote_sqlite_identifier(table_name)})"
    ).fetchall()
    return [str(row["name"]) for row in rows]


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def insert_rows(
    connection: Any,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[sqlite3.Row],
) -> None:
    values = [tuple(row[column] for column in columns) for row in rows]
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        placeholders,
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, values)


def reset_sequences(connection: Any) -> None:
    with connection.cursor() as cursor:
        for table in TABLE_MANIFEST:
            if not table.serial:
                continue
            cursor.execute(
                sql.SQL(
                    """
                    SELECT setval(
                        pg_get_serial_sequence(%s, 'id'),
                        GREATEST(COALESCE(MAX(id), 0), 1),
                        COALESCE(MAX(id), 0) > 0
                    )
                    FROM {}
                    """
                ).format(sql.Identifier(table.name)),
                (table.name,),
            )
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
    "idx_native_voice_sessions_guild_user",
    "idx_native_voice_sessions_open",
    "idx_native_message_stats_guild_user",
    "idx_reward_items_guild_active",
    "idx_shop_level_configs_active",
    "idx_user_level_upgrades_user",
    "idx_reward_purchases_guild_user_created",
    "idx_reward_purchases_reward_user",
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


def validate_row_counts(connection: Any) -> None:
    divergences: list[str] = []
    with connection.cursor() as cursor:
        for table in TABLE_MANIFEST:
            sqlite_count = sqlite_row_count(table)
            cursor.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table.name))
            )
            postgres_count = int(cursor.fetchone()[0])
            if sqlite_count != postgres_count:
                divergences.append(
                    f"{table.name}: sqlite={sqlite_count}, postgres={postgres_count}"
                )
    if divergences:
        raise RuntimeError("Divergencia de contagens: " + "; ".join(divergences))


def sqlite_row_count(table: TableSpec) -> int:
    if not table.path.exists() or not sqlite_table_exists(table.path, table.name):
        return 0
    with sqlite3.connect(table.path) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {quote_sqlite_identifier(table.name)}"
        ).fetchone()
    return int(row[0])


if __name__ == "__main__":
    raise SystemExit(main())
