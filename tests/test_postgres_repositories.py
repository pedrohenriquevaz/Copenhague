from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from psycopg import sql

from app.models.economy import EconomyTransactionType
from app.models.giveaway import (
    GiveawayCodeSeed,
    GiveawayDrawStatus,
    GiveawayEventCreate,
    utc_now,
)
from app.models.moderation import ModerationActionType, ModerationCaseCreate
from app.models.shop import (
    RewardItemCreate,
    RewardType,
    ShopPurchaseStatus,
    StockMode,
)
from app.repositories.postgres_database import PostgresDatabase
from app.repositories.postgres_moderation_repository import PostgresModerationRepository
from app.repositories.postgres_repositories import (
    PostgresEconomyRepository,
    PostgresGiveawayRepository,
)
from scripts.db_manage import (
    apply_migrations,
    ensure_migrations_table,
    load_migrations,
    validate_schema,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Defina RUN_POSTGRES_TESTS=1 para executar testes PostgreSQL.",
)


@pytest.fixture
async def postgres_database():
    psycopg = pytest.importorskip("psycopg")
    dsn = os.getenv(
        "POSTGRES_TEST_DSN",
        os.getenv(
            "POSTGRES_MIGRATION_DSN",
            "postgresql://copenhague:copenhague@127.0.0.1:5432/copenhague",
        ),
    )
    schema = f"copenhague_test_{uuid.uuid4().hex}"
    database = PostgresDatabase(dsn, schema=schema, min_size=1, max_size=4)
    try:
        yield database
    finally:
        await database.close()
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()


async def test_postgres_economy_concurrent_transfers(postgres_database) -> None:
    repository = PostgresEconomyRepository(postgres_database)
    await repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=1000,
        transaction_type=EconomyTransactionType.ADMIN_GIVE,
        actor_id=99,
        reason="seed",
    )

    await asyncio.gather(
        *(
            repository.transfer_balance(
                guild_id=1,
                sender_id=10,
                receiver_id=20 + index,
                amount=50,
                reason="test",
            )
            for index in range(8)
        )
    )

    sender = await repository.get_wallet(1, 10)
    assert sender.balance == 600


async def test_postgres_casino_cap_is_atomic_across_repository_instances(
    postgres_database,
) -> None:
    first_repository = PostgresEconomyRepository(postgres_database)
    second_repository = PostgresEconomyRepository(postgres_database)
    await first_repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=30_000,
        transaction_type=EconomyTransactionType.ADMIN_GIVE,
        actor_id=99,
        reason="seed",
    )
    for index in range(2):
        await first_repository.mutate_balance(
            guild_id=1,
            user_id=10,
            amount=-100,
            transaction_type=EconomyTransactionType.CASINO_BET,
            actor_id=None,
            reason=f"concurrent_bet_{index}",
        )

    results = await asyncio.gather(
        first_repository.settle_casino_payout(
            guild_id=1,
            user_id=10,
            requested_payout=1_000,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            reason="concurrent_payout_1",
            metadata={"game": "test"},
            daily_profit_limit=100,
            profit_timezone_offset_minutes=-180,
            idempotency_key="atomic-cap:1",
        ),
        second_repository.settle_casino_payout(
            guild_id=1,
            user_id=10,
            requested_payout=1_000,
            transaction_type=EconomyTransactionType.CASINO_PAYOUT,
            reason="concurrent_payout_2",
            metadata={"game": "test"},
            daily_profit_limit=100,
            profit_timezone_offset_minutes=-180,
            idempotency_key="atomic-cap:2",
        ),
    )

    assert sorted(result.paid_payout for result in results) == [0, 300]
    assert (await first_repository.get_wallet(1, 10)).balance == 30_100
    assert all(result.transaction is not None for result in results)


async def test_postgres_casino_payout_idempotency_prevents_double_credit(
    postgres_database,
) -> None:
    first_repository = PostgresEconomyRepository(postgres_database)
    second_repository = PostgresEconomyRepository(postgres_database)
    await first_repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=30_000,
        transaction_type=EconomyTransactionType.ADMIN_GIVE,
        actor_id=99,
        reason="seed",
    )

    results = await asyncio.gather(
        *(
            repository.settle_casino_payout(
                guild_id=1,
                user_id=10,
                requested_payout=500,
                transaction_type=EconomyTransactionType.CASINO_PAYOUT,
                reason="idempotent_payout",
                metadata={"game": "test"},
                daily_profit_limit=None,
                profit_timezone_offset_minutes=-180,
                idempotency_key="same-round",
            )
            for repository in (first_repository, second_repository)
        )
    )

    assert {result.transaction.id for result in results} == {
        results[0].transaction.id
    }
    assert sorted(result.idempotent_replay for result in results) == [False, True]
    assert (await first_repository.get_wallet(1, 10)).balance == 30_500


async def test_postgres_balance_mutation_idempotency_prevents_double_refund(
    postgres_database,
) -> None:
    first_repository = PostgresEconomyRepository(postgres_database)
    second_repository = PostgresEconomyRepository(postgres_database)

    results = await asyncio.gather(
        *(
            repository.mutate_balance(
                guild_id=1,
                user_id=10,
                amount=100,
                transaction_type=EconomyTransactionType.REFUND,
                actor_id=None,
                reason="retry_refund",
                idempotency_key="refund:1",
            )
            for repository in (first_repository, second_repository)
        )
    )

    assert results[0].transaction.id == results[1].transaction.id
    assert (await first_repository.get_wallet(1, 10)).balance == 100


async def test_postgres_credit_protection_effect_is_idempotent(
    postgres_database,
) -> None:
    first_repository = PostgresEconomyRepository(postgres_database)
    second_repository = PostgresEconomyRepository(postgres_database)
    await first_repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=1_000,
        transaction_type=EconomyTransactionType.ADMIN_GIVE,
        actor_id=99,
        reason="seed",
    )
    await first_repository.adjust_credit_saves(guild_id=1, user_id=10, delta=1)
    for index in range(3):
        await first_repository.apply_credit_protection(
            guild_id=1,
            user_id=10,
            game_key="test",
            stake=100,
            is_loss=True,
            idempotency_key=f"prior-loss:{index}",
        )

    results = await asyncio.gather(
        *(
            repository.apply_credit_protection(
                guild_id=1,
                user_id=10,
                game_key="test",
                stake=100,
                is_loss=True,
                idempotency_key="same-loss",
            )
            for repository in (first_repository, second_repository)
        )
    )
    state = await first_repository.get_credit_protection_state(1, 10)

    assert sorted(result.cashback_amount for result in results) == [0, 50]
    assert sorted(result.idempotent_replay for result in results) == [False, True]
    assert (await first_repository.get_wallet(1, 10)).balance == 1_050
    assert state.saves == 0
    assert state.lose_streak == 4


async def test_postgres_settlement_uses_one_instant_for_day_and_created_at(
    postgres_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PostgresEconomyRepository(postgres_database)
    await repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=30_000,
        transaction_type=EconomyTransactionType.ADMIN_GIVE,
        actor_id=99,
        reason="seed",
    )
    fixed_now = datetime(2026, 7, 15, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "app.repositories.economy_repository.utc_now", lambda: fixed_now
    )

    result = await repository.settle_casino_payout(
        guild_id=1,
        user_id=10,
        requested_payout=100,
        transaction_type=EconomyTransactionType.CASINO_PAYOUT,
        reason="midnight_payout",
        metadata={"game": "test"},
        daily_profit_limit=30,
        profit_timezone_offset_minutes=-180,
        idempotency_key="midnight-round",
    )

    assert result.paid_payout == 30
    assert result.profit_window_start == fixed_now
    assert result.transaction.created_at == fixed_now
    assert result.transaction.metadata["economic_settlement_window_start"] == (
        "2026-07-15T03:00:00+00:00"
    )


async def test_postgres_shop_limited_stock_is_single_claim(
    postgres_database,
) -> None:
    repository = PostgresEconomyRepository(postgres_database)
    for user_id in (10, 11):
        await repository.mutate_balance(
            guild_id=1,
            user_id=user_id,
            amount=100,
            transaction_type=EconomyTransactionType.ADMIN_GIVE,
            actor_id=99,
            reason="seed",
        )

    reward = await repository.create_reward(
        RewardItemCreate(
            guild_id=1,
            name="VIP",
            description="Acesso VIP",
            type=RewardType.VIP_ACCESS,
            price=50,
            stock_quantity=1,
            stock_mode=StockMode.LIMITED,
            max_per_user=None,
            role_id=None,
            delivery_message=None,
            created_by=99,
            duration_days=14,
        )
    )

    assert reward.duration_days == 14

    results = await asyncio.gather(
        repository.purchase_reward(guild_id=1, user_id=10, reward_id=reward.id),
        repository.purchase_reward(guild_id=1, user_id=11, reward_id=reward.id),
    )

    statuses = {result.status for result in results}
    assert statuses == {
        ShopPurchaseStatus.SUCCESS,
        ShopPurchaseStatus.OUT_OF_STOCK,
    }


async def test_postgres_giveaway_single_code_claim(postgres_database) -> None:
    repository = PostgresGiveawayRepository(postgres_database)
    event = await repository.create_event(
        GiveawayEventCreate(
            title="Drop",
            description="Teste",
            created_by=99,
            created_at=utc_now(),
            total_codes=1,
        ),
        [GiveawayCodeSeed(code="ABC", reward_name="Doletas", reward_amount=100)],
    )

    results = await asyncio.gather(
        repository.claim_next_available_code(event.id, 10),
        repository.claim_next_available_code(event.id, 11),
    )

    statuses = {result.status for result in results}
    assert GiveawayDrawStatus.SUCCESS in statuses
    assert statuses <= {
        GiveawayDrawStatus.SUCCESS,
        GiveawayDrawStatus.SOLD_OUT,
        GiveawayDrawStatus.EVENT_INACTIVE,
    }


async def test_postgres_moderation_isolates_guilds_and_persists_cases(
    postgres_database,
) -> None:
    import psycopg

    postgres_database.open_sync()
    with psycopg.connect(postgres_database._dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(postgres_database.schema)
                )
            )
        apply_migrations(connection)
        validate_schema(connection)

    repository = PostgresModerationRepository(postgres_database)
    assert await repository.add_authorized_role(1, 100)
    assert not await repository.add_authorized_role(1, 100)
    await repository.set_log_channel(1, 500)

    case = await repository.create_case(
        ModerationCaseCreate(
            guild_id=1,
            action_type=ModerationActionType.MUTE,
            target_user_id=20,
            moderator_user_id=10,
            reason="Teste de integracao",
            duration=timedelta(seconds=60),
            metadata={"source": "pytest", "nested": {"attempt": 1}},
        )
    )
    kick_case = await repository.create_case(
        ModerationCaseCreate(
            guild_id=1,
            action_type=ModerationActionType.KICK,
            target_user_id=21,
            moderator_user_id=10,
            reason="Teste de kick",
        )
    )
    warn_case = await repository.create_case(
        ModerationCaseCreate(
            guild_id=1,
            action_type=ModerationActionType.WARN,
            target_user_id=22,
            moderator_user_id=10,
            reason="Teste de warn",
        )
    )

    assert (await repository.get_settings(1)).authorized_role_ids == (100,)
    assert (await repository.get_settings(1)).log_channel_id == 500
    assert (await repository.get_settings(2)).authorized_role_ids == ()
    assert await repository.get_case(1, case.id) == case
    assert await repository.get_case(1, kick_case.id) == kick_case
    assert await repository.get_case(1, warn_case.id) == warn_case
    assert await repository.get_case(2, case.id) is None
    assert await repository.remove_authorized_role(1, 100)
    assert not await repository.remove_authorized_role(1, 100)
    cleared = await repository.set_log_channel(1, None)
    assert cleared.log_channel_id is None


async def test_postgres_moderation_migrations_upgrade_from_applied_0009(
    postgres_database,
) -> None:
    import psycopg

    migrations = load_migrations()
    original = next(
        migration
        for migration in migrations
        if migration.name == "0009_moderation_foundation"
    )
    assert original.checksum == (
        "8c661708df653184f058b26125ecc92bdb92ac9d907becb8698abfb20b404476"
    )

    with psycopg.connect(postgres_database._dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(postgres_database.schema)
                )
            )
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(postgres_database.schema)
                )
            )
        connection.commit()
        ensure_migrations_table(connection)

        with connection.cursor() as cursor:
            for migration in migrations:
                if migration.name > original.name:
                    break
                cursor.execute(migration.path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (migration.name, migration.checksum),
                )
            cursor.execute(
                """
                INSERT INTO moderation_cases (
                    guild_id, action_type, target_user_id, moderator_user_id,
                    reason, duration_seconds, status, origin, metadata
                ) VALUES (1, 'TIMEOUT', 2, 3, 'legado', 0, 'COMPLETED',
                          'COMMAND', '{}'::jsonb)
                """
            )
        connection.commit()

        apply_migrations(connection)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT action_type, duration_seconds
                FROM moderation_cases
                WHERE guild_id = 1
                """
            )
            migrated_action, migrated_duration = cursor.fetchone()
            assert migrated_action == "MUTE"
            assert migrated_duration is None
            cursor.execute(
                """
                SELECT BOOL_AND(constraint_data.convalidated)
                FROM (
                    SELECT constraint_row.convalidated
                    FROM pg_constraint AS constraint_row
                    JOIN pg_class AS table_row
                      ON table_row.oid = constraint_row.conrelid
                    JOIN pg_namespace AS namespace_row
                      ON namespace_row.oid = table_row.relnamespace
                    WHERE namespace_row.nspname = current_schema()
                      AND constraint_row.conname LIKE 'moderation_%'
                      AND constraint_row.contype = 'c'
                ) AS constraint_data
                """
            )
            assert cursor.fetchone()[0] is True
            with pytest.raises(psycopg.errors.CheckViolation):
                cursor.execute(
                    """
                    INSERT INTO moderation_cases (
                        guild_id, action_type, target_user_id, moderator_user_id,
                        reason, status, origin, metadata
                    ) VALUES (1, 'TIMEOUT', 4, 3, 'tipo antigo', 'COMPLETED',
                              'COMMAND', '{}'::jsonb)
                    """
                )
        connection.rollback()
