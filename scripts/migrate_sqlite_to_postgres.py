from __future__ import annotations

import argparse
import os
import re
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
except ModuleNotFoundError:  # pragma: no cover - exercised before migration only.
    psycopg = None
    sql = None


DEFAULT_POSTGRES_DSN = "postgresql://copenhague:copenhague@localhost:5432/copenhague"
DEFAULT_SCHEMA = "copenhague"
DEFAULT_CHUNK_SIZE = 500


@dataclass(frozen=True, slots=True)
class SQLiteSource:
    label: str
    path: Path


@dataclass(frozen=True, slots=True)
class SQLiteTable:
    source: SQLiteSource
    name: str
    create_sql: str
    columns: tuple[str, ...]
    serial_column: str | None


def main() -> int:
    load_dotenv()
    args = parse_args()
    if psycopg is None or sql is None:
        print(
            "Dependencia ausente: instale `psycopg[binary]` antes de migrar.",
            file=sys.stderr,
        )
        return 2

    sources = discover_sources(args.source)
    if not sources:
        print("Nenhum banco SQLite encontrado para migrar.", file=sys.stderr)
        return 1

    if not args.skip_schema_refresh:
        refresh_sqlite_schemas(sources)

    if not args.no_backup:
        backup_path = backup_sqlite_files(sources, args.backup_dir)
        print(f"Backup SQLite criado em: {backup_path}")

    tables = read_sqlite_tables(sources)
    ensure_unique_table_names(tables)
    migrate_to_postgres(
        dsn=args.postgres_dsn,
        schema=args.schema,
        tables=tables,
        replace=args.replace,
        chunk_size=args.chunk_size,
    )
    print(
        f"Migracao concluida: {len(tables)} tabela(s) copiadas "
        f"para o schema `{args.schema}`."
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra os bancos SQLite locais do bot para PostgreSQL.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.getenv("POSTGRES_MIGRATION_DSN")
        or os.getenv("POSTGRES_DSN")
        or DEFAULT_POSTGRES_DSN,
        help=(
            "DSN do Postgres. No host local, use algo como "
            "postgresql://copenhague:copenhague@localhost:5432/copenhague."
        ),
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("POSTGRES_SCHEMA", DEFAULT_SCHEMA),
        help="Schema de destino no Postgres.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Remove as tabelas de destino antes de recria-las.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Nao cria ZIP dos arquivos SQLite antes da migracao.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Diretorio onde o backup SQLite sera salvo.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Quantidade de linhas inseridas por lote.",
    )
    parser.add_argument(
        "--skip-schema-refresh",
        action="store_true",
        help="Nao inicializa/migra schemas SQLite antes de copiar.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help=(
            "Origem SQLite adicional ou sobrescrita. Pode ser usado mais de "
            "uma vez, por exemplo: --source economy=data/economy.sqlite3."
        ),
    )
    return parser.parse_args()


def discover_sources(raw_sources: Sequence[str]) -> list[SQLiteSource]:
    if raw_sources:
        return dedupe_sources(parse_source(value) for value in raw_sources)

    candidates = [
        SQLiteSource(
            "economy",
            Path(os.getenv("ECONOMY_DB_PATH", "data/economy.sqlite3")),
        ),
        SQLiteSource(
            "bot",
            Path(os.getenv("BOLAO_DB_PATH", "data/bot.db")),
        ),
        SQLiteSource(
            "match_bet",
            Path(os.getenv("MATCH_BET_DB_PATH", "data/bot.db")),
        ),
        SQLiteSource(
            "game_progress",
            Path(os.getenv("GAME_PROGRESS_DB_PATH", "data/bot.db")),
        ),
        SQLiteSource(
            "forms",
            Path(os.getenv("FORM_DB_PATH", "data/bot.db")),
        ),
        SQLiteSource(
            "giveaways",
            Path(os.getenv("GIVEAWAY_DB_PATH", "data/giveaways.sqlite3")),
        ),
    ]
    return dedupe_sources(source for source in candidates if source.path.exists())


def parse_source(value: str) -> SQLiteSource:
    label, separator, path = value.partition("=")
    if not separator or not label.strip() or not path.strip():
        raise SystemExit(f"Origem invalida: {value!r}. Use LABEL=PATH.")
    return SQLiteSource(label.strip(), Path(path.strip()))


def dedupe_sources(sources: Iterable[SQLiteSource]) -> list[SQLiteSource]:
    by_path: dict[Path, SQLiteSource] = {}
    for source in sources:
        path = source.path
        resolved = path.resolve() if path.exists() else path
        by_path.setdefault(resolved, SQLiteSource(source.label, path))
    return list(by_path.values())


def refresh_sqlite_schemas(sources: Sequence[SQLiteSource]) -> None:
    existing_paths = {
        source.path.resolve() for source in sources if source.path.exists()
    }
    if not existing_paths:
        return

    from app.repositories.bolao_repository import SQLiteBolaoRepository
    from app.repositories.economy_repository import SQLiteEconomyRepository
    from app.repositories.form_repository import SQLiteFormRepository
    from app.repositories.game_progress_repository import SQLiteGameProgressRepository
    from app.repositories.giveaway_repository import SQLiteGiveawayRepository
    from app.repositories.match_bet_repository import SQLiteMatchBetRepository

    repository_factories = [
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
    ]
    for path, factory in repository_factories:
        if path.exists() and path.resolve() in existing_paths:
            factory(path)


def backup_sqlite_files(
    sources: Sequence[SQLiteSource],
    backup_dir: Path,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"sqlite-before-postgres-{timestamp}.zip"
    cwd = Path.cwd()

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
            for file_path in sqlite_related_files(source.path):
                archive.write(file_path, arcname=archive_name(file_path, cwd))
    return backup_path


def sqlite_related_files(db_path: Path) -> Iterable[Path]:
    for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if candidate.exists():
            yield candidate


def archive_name(path: Path, cwd: Path) -> str:
    try:
        return str(path.resolve().relative_to(cwd.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def read_sqlite_tables(sources: Sequence[SQLiteSource]) -> list[SQLiteTable]:
    tables: list[SQLiteTable] = []
    for source in sources:
        with sqlite3.connect(source.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'table'
                    AND name NOT LIKE 'sqlite_%'
                    AND sql IS NOT NULL
                ORDER BY rowid
                """
            ).fetchall()
            for row in rows:
                table_name = str(row["name"])
                columns = tuple(
                    str(column["name"])
                    for column in connection.execute(
                        f'PRAGMA table_info("{table_name}")'
                    ).fetchall()
                )
                tables.append(
                    SQLiteTable(
                        source=source,
                        name=table_name,
                        create_sql=str(row["sql"]),
                        columns=columns,
                        serial_column=find_serial_column(str(row["sql"])),
                    )
                )
    return tables


def find_serial_column(create_sql: str) -> str | None:
    match = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        create_sql,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def ensure_unique_table_names(tables: Sequence[SQLiteTable]) -> None:
    seen: dict[str, SQLiteTable] = {}
    for table in tables:
        if table.name in seen:
            first = seen[table.name]
            raise SystemExit(
                "Tabela duplicada encontrada em bancos diferentes: "
                f"{table.name} ({first.source.path} e {table.source.path})."
            )
        seen[table.name] = table


def migrate_to_postgres(
    *,
    dsn: str,
    schema: str,
    tables: Sequence[SQLiteTable],
    replace: bool,
    chunk_size: int,
) -> None:
    if chunk_size <= 0:
        raise SystemExit("--chunk-size precisa ser maior que zero.")

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(schema)
                )
            )
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema)
                )
            )
            if replace:
                drop_existing_tables(cursor, schema, tables)
            create_tables(cursor, tables)
            create_indexes(cursor, schema, tables)
            copy_data(cursor, schema, tables, chunk_size)
            reset_sequences(cursor, schema, tables)
        connection.commit()


def drop_existing_tables(
    cursor: Any,
    schema: str,
    tables: Sequence[SQLiteTable],
) -> None:
    for table in reversed(tables):
        cursor.execute(
            sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(schema, table.name)
            )
        )


def create_tables(cursor: Any, tables: Sequence[SQLiteTable]) -> None:
    for table in tables:
        cursor.execute(convert_create_table(table.create_sql))


def create_indexes(cursor: Any, schema: str, tables: Sequence[SQLiteTable]) -> None:
    for table in tables:
        with sqlite3.connect(table.source.path) as connection:
            rows = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index'
                    AND tbl_name = ?
                    AND sql IS NOT NULL
                ORDER BY rowid
                """,
                (table.name,),
            ).fetchall()
        for (index_sql,) in rows:
            cursor.execute(convert_create_index(str(index_sql), schema))


def copy_data(
    cursor: Any,
    schema: str,
    tables: Sequence[SQLiteTable],
    chunk_size: int,
) -> None:
    for table in tables:
        rows_copied = 0
        insert_statement = build_insert_statement(schema, table)
        with sqlite3.connect(table.source.path) as connection:
            connection.row_factory = sqlite3.Row
            sqlite_cursor = connection.execute(f'SELECT * FROM "{table.name}"')
            while True:
                rows = sqlite_cursor.fetchmany(chunk_size)
                if not rows:
                    break
                values = [
                    tuple(row[column] for column in table.columns) for row in rows
                ]
                cursor.executemany(insert_statement, values)
                rows_copied += len(rows)
        print(f"{table.name}: {rows_copied} linha(s)")


def build_insert_statement(schema: str, table: SQLiteTable) -> Any:
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in table.columns)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in table.columns)
    return sql.SQL(
        "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
    ).format(sql.Identifier(schema, table.name), columns, placeholders)


def reset_sequences(cursor: Any, schema: str, tables: Sequence[SQLiteTable]) -> None:
    for table in tables:
        if table.serial_column is None:
            continue
        relation = f"{schema}.{table.name}"
        cursor.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            (relation, table.serial_column),
        )
        sequence_name = cursor.fetchone()[0]
        if sequence_name is None:
            continue
        cursor.execute(
            sql.SQL("SELECT COALESCE(MAX({}), 0) FROM {}").format(
                sql.Identifier(table.serial_column),
                sql.Identifier(schema, table.name),
            )
        )
        max_id = int(cursor.fetchone()[0] or 0)
        if max_id <= 0:
            cursor.execute("SELECT setval(%s, 1, false)", (sequence_name,))
        else:
            cursor.execute("SELECT setval(%s, %s, true)", (sequence_name, max_id))


def convert_create_table(create_sql: str) -> str:
    converted = create_sql.strip().rstrip(";")
    converted = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(r"\bINTEGER\b", "BIGINT", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bREAL\b", "DOUBLE PRECISION", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bBLOB\b", "BYTEA", converted, flags=re.IGNORECASE)
    return converted


def convert_create_index(index_sql: str, schema: str) -> str:
    converted = index_sql.strip().rstrip(";")
    converted = re.sub(
        r"\bON\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        lambda match: f'ON "{schema}"."{match.group(1)}" (',
        converted,
        count=1,
        flags=re.IGNORECASE,
    )
    return converted


if __name__ == "__main__":
    raise SystemExit(main())
