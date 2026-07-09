from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from app.models.economy import EconomyTransactionType
from app.models.giveaway import (
    GiveawayCodeSeed,
    GiveawayDrawStatus,
    GiveawayEventCreate,
    utc_now,
)
from app.models.shop import (
    RewardItemCreate,
    RewardType,
    ShopPurchaseStatus,
    StockMode,
)
from app.repositories.postgres_database import PostgresDatabase
from app.repositories.postgres_repositories import (
    PostgresEconomyRepository,
    PostgresGiveawayRepository,
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
        )
    )

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
