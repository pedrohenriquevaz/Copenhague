from __future__ import annotations

import gc
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from app.models.guild_settings import GuildEconomySettings
from app.models.shop import RewardItem, RewardType, ShopPurchaseStatus, StockMode
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.services.activity_service import ActivityService
from app.services.economy_service import EconomyService
from app.services.shop_service import ShopService
from app.utils.embeds import build_shop_embed


async def test_economy_admin_points_and_history() -> None:
    db_path = Path("tests") / "tmp_economy.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)

        given = await economy.give_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=250,
            reason="evento",
        )
        assert given.wallet.balance == 250
        assert given.transaction.balance_before == 0
        assert given.transaction.balance_after == 250

        removed = await economy.remove_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=50,
            reason="ajuste",
        )
        assert removed.wallet.balance == 200

        history = await economy.list_history(1, 10)
        assert [transaction.amount for transaction in history] == [-50, 250]
    finally:
        repository = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_activity_conversion_uses_delta_only() -> None:
    db_path = Path("tests") / "tmp_activity.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        activity = ActivityService(repository)
        economy = EconomyService(repository)

        for _ in range(3):
            await activity.record_message(
                guild_id=1,
                channel_id=100,
                user_id=10,
                is_bot=False,
            )

        await activity.start_voice_session(
            guild_id=1,
            user_id=10,
            channel_id=200,
            is_bot=False,
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute("""
                UPDATE native_voice_sessions
                SET started_at = datetime('now', '-2 minutes')
                WHERE guild_id = 1 AND user_id = 10
                """)
        await activity.close_voice_sessions(guild_id=1, user_id=10, is_bot=False)

        first = await activity.convert_activity(guild_id=1, user_id=10)
        assert first.total_points >= 7
        assert first.messages_delta == 3
        assert first.voice_seconds_delta >= 120

        second = await activity.convert_activity(guild_id=1, user_id=10)
        assert second.total_points == 0
        assert second.transaction is None

        wallet = await economy.get_wallet(1, 10)
        assert wallet.balance == first.total_points
    finally:
        repository = None
        activity = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_activity_conversion_counts_open_voice_session() -> None:
    db_path = Path("tests") / "tmp_activity_open.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        activity = ActivityService(repository)

        await activity.start_voice_session(
            guild_id=1,
            user_id=10,
            channel_id=200,
            is_bot=False,
        )
        await activity.start_voice_session(
            guild_id=1,
            user_id=10,
            channel_id=200,
            is_bot=False,
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute("""
                UPDATE native_voice_sessions
                SET started_at = datetime('now', '-2 minutes')
                WHERE guild_id = 1 AND user_id = 10
                """)
            sessions = connection.execute("""
                SELECT COUNT(*) AS total
                FROM native_voice_sessions
                WHERE guild_id = 1 AND user_id = 10
                """).fetchone()

        result = await activity.convert_activity(guild_id=1, user_id=10)

        assert sessions is not None
        assert int(sessions[0]) == 1
        assert result.voice_seconds_delta >= 120
        assert result.voice_points >= 4
        assert result.total_points >= result.voice_points
    finally:
        repository = None
        activity = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_shop_purchase_debits_wallet_and_stock() -> None:
    db_path = Path("tests") / "tmp_shop.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)
        shop = ShopService(repository)

        reward = await shop.create_reward(
            guild_id=1,
            name="VIP",
            description="Acesso VIP",
            reward_type=RewardType.MANUAL_REWARD,
            price=100,
            stock_quantity=1,
            stock_mode=StockMode.LIMITED,
            max_per_user=1,
            role_id=None,
            delivery_message=None,
            created_by=99,
        )

        insufficient = await shop.purchase_reward(
            guild_id=1,
            user_id=10,
            reward_id=reward.id,
        )
        assert insufficient.status is ShopPurchaseStatus.INSUFFICIENT_BALANCE

        await economy.give_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=150,
            reason="seed",
        )
        purchase = await shop.purchase_reward(
            guild_id=1,
            user_id=10,
            reward_id=reward.id,
        )
        assert purchase.status is ShopPurchaseStatus.SUCCESS
        assert purchase.balance_after == 50

        out_of_stock = await shop.purchase_reward(
            guild_id=1,
            user_id=11,
            reward_id=reward.id,
        )
        assert out_of_stock.status is ShopPurchaseStatus.OUT_OF_STOCK
    finally:
        repository = None
        economy = None
        shop = None
        gc.collect()
        _cleanup_sqlite(db_path)


def test_shop_embed_layout_hides_type_and_formats_stock() -> None:
    now = datetime.now(UTC)
    settings = GuildEconomySettings(
        guild_id=1,
        currency_name="pontos",
        voice_points_per_minute=2,
        message_points=1,
        activity_provider="native",
        economy_channel_id=None,
        shop_channel_id=None,
        staff_log_channel_id=None,
        min_voice_seconds_to_claim=60,
        min_messages_to_claim=1,
        ignore_afk_channel=True,
        ignore_bots=True,
        count_voice_when_alone=False,
        max_admin_grant_per_use=100000,
        economy_manager_role_id=None,
        created_at=now,
        updated_at=now,
    )
    rewards = [
        RewardItem(
            id=3,
            guild_id=1,
            name="VIP Plus",
            description="VIP",
            type=RewardType.ROLE,
            price=17000,
            stock_quantity=0,
            stock_mode=StockMode.LIMITED,
            max_per_user=1,
            role_id=123,
            delivery_message=None,
            is_active=True,
            created_by=99,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ),
        RewardItem(
            id=1,
            guild_id=1,
            name="Passe Semanal",
            description="Passe",
            type=RewardType.MANUAL_REWARD,
            price=8000,
            stock_quantity=10,
            stock_mode=StockMode.LIMITED,
            max_per_user=1,
            role_id=None,
            delivery_message=None,
            is_active=True,
            created_by=99,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        ),
    ]

    embed = build_shop_embed(
        rewards,
        settings,
        image_url="https://cdn.example.com/loja.png",
    )

    assert embed.description is not None
    assert embed.image.url == "https://cdn.example.com/loja.png"
    assert "Escolha uma recompensa no menu abaixo" in embed.description
    assert "**VIP Plus**" in embed.description
    assert "#3" not in embed.description
    assert "Tipo" not in embed.description
    assert "Preço: 17.000 pontos | Esgotado" in embed.description
    assert "Preço: 8.000 pontos | Estoque: 10" in embed.description
    assert "\n\n**Passe Semanal**" in embed.description


def _cleanup_sqlite(db_path: Path) -> None:
    if db_path.exists():
        for _ in range(5):
            try:
                db_path.unlink()
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.1)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            try:
                sidecar.unlink()
            except PermissionError:
                pass
