from __future__ import annotations

from pathlib import Path

from scripts.db_manage import EXPECTED_INDEXES, TABLE_MANIFEST


def test_mlbb_migration_has_required_constraints_without_secret_fields() -> None:
    migration = Path("sql/postgres/migrations/0013_mlbb_account_linking.sql").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(migration.split()).upper()

    assert "MLBB_AUTH_ATTEMPTS" in normalized
    assert "MLBB_ACCOUNT_LINKS" in normalized
    assert "PRIMARY KEY (GUILD_ID, DISCORD_USER_ID)" in normalized
    assert "UNIQUE (GUILD_ID, ROLE_ID, ZONE_ID)" in normalized
    assert "ENCRYPTED_JWT" in normalized
    assert "VERIFICATION_CODE" not in normalized
    assert "MLBB_AUDIT_LOGS" not in normalized


def test_mlbb_repository_uses_postgres_row_locks_without_sqlite_transactions() -> None:
    source = Path("app/repositories/mlbb_repository.py").read_text(encoding="utf-8")

    assert "FOR UPDATE" in source
    assert "pg_advisory_xact_lock" in source
    assert "BEGIN IMMEDIATE" not in source


def test_database_validator_knows_mlbb_tables_and_indexes() -> None:
    table_names = {spec.name for spec in TABLE_MANIFEST}

    assert {"mlbb_auth_attempts", "mlbb_account_links"} <= table_names
    assert {
        "uq_mlbb_open_attempt_user_guild",
        "idx_mlbb_auth_attempts_expiry",
        "idx_mlbb_links_game_account",
        "idx_mlbb_links_status",
    } <= set(EXPECTED_INDEXES)
