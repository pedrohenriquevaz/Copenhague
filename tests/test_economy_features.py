from __future__ import annotations

import gc
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from PIL import Image

from app.cogs.economy.activity import ActivityCog
from app.models.casino import CoinSide
from app.models.economy import (
    CreditProtectionState,
    EconomyTransactionType,
    UserWallet,
)
from app.models.giveaway import serialize_datetime, utc_now
from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    LevelConfig,
    LevelUpgradeStatus,
    RewardItem,
    RewardType,
    ShopPurchaseStatus,
    StockMode,
)
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.services.activity_service import ActivityService
from app.services.casino_service import CasinoService
from app.services.economy_service import EconomyService, EconomyValidationError
from app.services.shop_service import ShopService
from app.ui.economy_panel import EconomyPanelView
from app.ui.ranking_image import RANKING_IMAGE_FILENAME, render_ranking_podium_image
from app.utils.embeds import (
    build_economy_panel_embed,
    build_profile_badges,
    build_profile_embed,
    build_shop_embed,
)


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


async def test_economy_bulk_give_points_grants_unique_users() -> None:
    db_path = Path("tests") / "tmp_economy_bulk.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)

        results = await economy.give_points_bulk(
            guild_id=1,
            user_ids=[10, 20, 10],
            actor_id=99,
            amount=75,
            reason="premiacao por cargo",
            metadata={"role_id": 123},
        )
        wallet_10 = await economy.get_wallet(1, 10)
        wallet_20 = await economy.get_wallet(1, 20)
        history_10 = await economy.list_history(1, 10)

        assert len(results) == 2
        assert wallet_10.balance == 75
        assert wallet_20.balance == 75
        assert history_10[0].type is EconomyTransactionType.ADMIN_GIVE
        assert history_10[0].metadata["role_id"] == 123
    finally:
        repository = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_user_transfer_debits_sender_and_credits_receiver() -> None:
    db_path = Path("tests") / "tmp_economy_transfer.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)
        await economy.give_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=500,
            reason="seed",
        )

        result = await economy.transfer_points(
            guild_id=1,
            sender_id=10,
            receiver_id=20,
            amount=125,
        )
        sender_history = await economy.list_history(1, 10)
        receiver_history = await economy.list_history(1, 20)

        assert result.sender_wallet.balance == 375
        assert result.receiver_wallet.balance == 125
        assert result.sender_transaction.amount == -125
        assert result.receiver_transaction.amount == 125
        assert sender_history[0].type is EconomyTransactionType.USER_TRANSFER
        assert receiver_history[0].type is EconomyTransactionType.USER_TRANSFER
        assert sender_history[0].metadata["receiver_id"] == 20
        assert receiver_history[0].metadata["sender_id"] == 10

        try:
            await economy.transfer_points(
                guild_id=1,
                sender_id=10,
                receiver_id=20,
                amount=1000,
            )
        except EconomyValidationError as exc:
            assert "Saldo insuficiente" in str(exc)
        else:
            raise AssertionError("Transferencia sem saldo foi aceita.")

        sender_wallet = await economy.get_wallet(1, 10)
        receiver_wallet = await economy.get_wallet(1, 20)
        assert sender_wallet.balance == 375
        assert receiver_wallet.balance == 125
    finally:
        repository = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_reset_user_profile_clears_economy_activity_and_shop(
    tmp_path: Path,
) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "reset_economy.sqlite3")
    economy = EconomyService(repository)
    activity = ActivityService(repository)
    shop = ShopService(repository)

    reward = await shop.create_reward(
        guild_id=1,
        name="VIP",
        description="Acesso VIP",
        reward_type=RewardType.MANUAL_REWARD,
        price=100,
        stock_quantity=5,
        stock_mode=StockMode.LIMITED,
        max_per_user=1,
        role_id=None,
        delivery_message=None,
        created_by=99,
    )
    await economy.claim_starter_pack(guild_id=1, user_id=10)
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=500,
        reason="seed",
    )
    await activity.record_message(
        guild_id=1,
        channel_id=100,
        user_id=10,
        is_bot=False,
    )
    await activity.convert_activity(guild_id=1, user_id=10)
    await activity.start_voice_session(
        guild_id=1,
        user_id=10,
        channel_id=200,
        is_bot=False,
    )
    await activity.close_voice_sessions(guild_id=1, user_id=10, is_bot=False)
    await economy.add_credit_saves(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=2,
        reason="teste",
    )
    await economy.deposit_savings(guild_id=1, user_id=10, amount=100)
    purchase = await shop.purchase_reward(
        guild_id=1,
        user_id=10,
        reward_id=reward.id,
    )
    await shop.configure_level(
        guild_id=1,
        level=1,
        role_id=777,
        price=100,
        is_active=True,
        actor_id=99,
    )
    level_purchase = await shop.purchase_level_upgrade(
        guild_id=1,
        user_id=10,
        level=1,
    )

    result = await economy.reset_user_profile(
        guild_id=1,
        user_id=10,
        actor_id=99,
        reason="reset solicitado",
    )
    wallet = await economy.get_wallet(1, 10)
    history = await economy.list_history(1, 10)
    purchases = await shop.list_purchases(1, 10)
    level_upgrades = await shop.list_user_level_upgrades(1, 10)
    stats = await activity.get_stats(1, 10)

    assert purchase.status is ShopPurchaseStatus.SUCCESS
    assert level_purchase.status is LevelUpgradeStatus.SUCCESS
    assert result.wallet_before is not None
    assert result.deleted_wallets == 1
    assert result.deleted_transactions == 6
    assert result.deleted_reward_claims == 1
    assert result.deleted_activity_cursors == 1
    assert result.deleted_message_stats == 1
    assert result.deleted_voice_sessions == 1
    assert result.deleted_purchases == 1
    assert result.deleted_level_upgrades == 1
    assert result.deleted_credit_protection == 1
    assert result.deleted_savings_accounts == 1
    assert wallet.balance == 0
    assert wallet.total_earned == 0
    assert wallet.total_spent == 0
    assert history == []
    assert purchases == []
    assert level_upgrades == []
    assert stats.total_messages == 0
    assert stats.total_voice_seconds == 0

    starter = await economy.claim_starter_pack(guild_id=1, user_id=10)
    assert starter.amount == EconomyService.STARTER_PACK_AMOUNT


async def test_bot_panel_rewards_are_limited() -> None:
    db_path = Path("tests") / "tmp_bot_panel_rewards.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)

        starter = await economy.claim_starter_pack(guild_id=1, user_id=10)
        daily = await economy.claim_daily_gift(guild_id=1, user_id=10)
        wallet = await economy.get_wallet(1, 10)

        assert starter.amount == 500
        assert 25 <= daily.amount <= 75
        assert wallet.balance == starter.amount + daily.amount

        try:
            await economy.claim_starter_pack(guild_id=1, user_id=10)
        except Exception as exc:
            assert "pacote inicial" in str(exc)
        else:
            raise AssertionError("Pacote inicial foi resgatado duas vezes.")

        try:
            await economy.claim_daily_gift(guild_id=1, user_id=10)
        except Exception as exc:
            assert "presente diario" in str(exc)
        else:
            raise AssertionError("Presente diario foi resgatado duas vezes no dia.")
    finally:
        repository = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_economy_config_and_admin_summary() -> None:
    db_path = Path("tests") / "tmp_economy_admin_summary.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
        economy = EconomyService(repository)

        settings = await economy.configure_settings(
            guild_id=1,
            actor_id=99,
            currency_name="estrelas",
            voice_points_per_minute=4,
            message_points=2,
            min_voice_seconds_to_claim=120,
            min_messages_to_claim=3,
            count_voice_when_alone=True,
            max_admin_grant_per_use=5000,
            casino_max_bet=750,
            casino_daily_profit_limit=2500,
            casino_min_bet_coin_flip=10,
            casino_min_bet_dice=20,
            casino_min_bet_slot=30,
            casino_min_bet_roulette=40,
            casino_min_bet_mascot_race=50,
            casino_min_bet_duel=60,
            casino_min_bet_blackjack=70,
            casino_min_bet_scratch_card=80,
            casino_min_bet_collective_race=90,
            casino_min_bet_match_bet=100,
            casino_limiters_enabled=False,
            savings_daily_interest_percent=1.5,
            economy_manager_role_id=123,
            economy_channel_id=111,
            shop_channel_id=222,
            staff_log_channel_id=333,
        )
        await economy.give_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=100,
            reason="seed",
        )
        await economy.remove_points(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=25,
            reason="ajuste",
        )
        summary = await repository.get_admin_summary(1)

        assert settings.currency_name == "estrelas"
        assert settings.voice_points_per_minute == 4
        assert settings.message_points == 2
        assert settings.min_voice_seconds_to_claim == 120
        assert settings.count_voice_when_alone is True
        assert settings.casino_max_bet == 750
        assert settings.casino_daily_profit_limit == 2500
        assert settings.casino_min_bet_coin_flip == 10
        assert settings.casino_min_bet_dice == 20
        assert settings.casino_min_bet_slot == 30
        assert settings.casino_min_bet_roulette == 40
        assert settings.casino_min_bet_mascot_race == 50
        assert settings.casino_min_bet_duel == 60
        assert settings.casino_min_bet_blackjack == 70
        assert settings.casino_min_bet_scratch_card == 80
        assert settings.casino_min_bet_collective_race == 90
        assert settings.casino_min_bet_match_bet == 100
        assert settings.casino_limiters_enabled is False
        assert settings.savings_daily_interest_bps == 150
        assert settings.economy_manager_role_id == 123
        assert settings.staff_log_channel_id == 333
        assert summary["wallets"]["count"] == 1
        assert summary["wallets"]["balance"] == 75
        assert summary["savings"]["balance"] == 0
        assert summary["transactions"]["ADMIN_GIVE"]["in"] == 100
        assert summary["transactions"]["ADMIN_REMOVE"]["out"] == 25
        assert summary["audit"]["count"] == 3
    finally:
        repository = None
        economy = None
        gc.collect()
        _cleanup_sqlite(db_path)


async def test_economy_config_rejects_min_bet_above_max(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    economy = EconomyService(repository)

    with pytest.raises(EconomyValidationError, match="maior que o limite maximo"):
        await economy.configure_settings(
            guild_id=1,
            actor_id=99,
            casino_max_bet=100,
            casino_min_bet_duel=101,
        )


async def test_savings_deposit_lock_interest_and_withdraw(tmp_path: Path) -> None:
    db_path = tmp_path / "savings.sqlite3"
    repository = SQLiteEconomyRepository(db_path)
    economy = EconomyService(repository)
    await economy.configure_settings(
        guild_id=1,
        actor_id=99,
        savings_daily_interest_percent=10,
    )
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )

    with pytest.raises(EconomyValidationError, match="70%"):
        await economy.deposit_savings(guild_id=1, user_id=10, amount=701)

    deposit = await economy.deposit_savings(guild_id=1, user_id=10, amount=700)
    assert deposit.overview.wallet.balance == 300
    assert deposit.overview.account.balance == 700
    assert deposit.overview.account.locked_until is not None
    assert deposit.transaction.type is EconomyTransactionType.SAVINGS_DEPOSIT

    with pytest.raises(EconomyValidationError, match="bloqueada"):
        await economy.withdraw_savings(guild_id=1, user_id=10, amount=1)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE user_savings_accounts
            SET last_interest_at = ?,
                locked_until = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (
                serialize_datetime(utc_now() - timedelta(days=1, minutes=1)),
                serialize_datetime(utc_now() - timedelta(minutes=1)),
                1,
                10,
            ),
        )

    overview = await economy.get_savings_overview(1, 10)
    assert overview.interest_applied == 70
    assert overview.account.balance == 770
    assert overview.account.total_interest_earned == 70

    withdrawal = await economy.withdraw_savings(guild_id=1, user_id=10, amount=770)
    assert withdrawal.overview.wallet.balance == 1070
    assert withdrawal.overview.account.balance == 0
    assert withdrawal.transaction.type is EconomyTransactionType.SAVINGS_WITHDRAW
    summary = await repository.get_admin_summary(1)
    assert summary["savings"]["balance"] == 0
    assert summary["savings"]["interest_earned"] == 70


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


async def test_voice_activity_does_not_count_muted_microphones() -> None:
    settings = _activity_settings(count_voice_when_alone=False)
    service = _RecordingActivityService()
    bot = SimpleNamespace(
        activity_service=service,
        economy_repository=_StaticSettingsRepository(settings),
        user=SimpleNamespace(id=999),
    )
    cog = ActivityCog(bot)  # type: ignore[arg-type]
    guild = SimpleNamespace(id=1, afk_channel=None)

    channel_with_two_active_users = SimpleNamespace(
        id=200,
        guild=guild,
        members=[
            _voice_member(10),
            _voice_member(20),
            _voice_member(30, self_mute=True),
        ],
        voice_states={},
    )
    await cog._sync_voice_channel(channel_with_two_active_users)  # type: ignore[arg-type]

    assert service.started == [10, 20]
    assert service.closed == [30]

    service.started.clear()
    service.closed.clear()
    channel_with_one_active_user = SimpleNamespace(
        id=201,
        guild=guild,
        members=[
            _voice_member(10),
            _voice_member(20, mute=True),
        ],
        voice_states={},
    )
    await cog._sync_voice_channel(channel_with_one_active_user)  # type: ignore[arg-type]

    assert service.started == []
    assert service.closed == [10, 20]


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


async def test_credit_protection_cashback_consumes_saves_and_resets_on_win(
    tmp_path: Path,
) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "credit_protection.sqlite3")
    economy = EconomyService(repository)
    casino = CasinoService(
        repository,
        rng=_FixedCoinRng(
            [
                CoinSide.COROA,
                CoinSide.COROA,
                CoinSide.COROA,
                CoinSide.COROA,
                CoinSide.COROA,
                CoinSide.COROA,
                CoinSide.CARA,
            ]
        ),
        cooldown_seconds=0,
    )

    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )
    added = await economy.add_credit_saves(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=2,
        reason="teste",
    )

    assert added.after.saves == 2

    first_losses = [
        await casino.play_coin_flip(
            guild_id=1,
            user_id=10,
            bet=100,
            choice="cara",
        )
        for _ in range(3)
    ]
    fourth = await casino.play_coin_flip(
        guild_id=1,
        user_id=10,
        bet=100,
        choice="cara",
    )
    fifth = await casino.play_coin_flip(
        guild_id=1,
        user_id=10,
        bet=100,
        choice="cara",
    )
    sixth = await casino.play_coin_flip(
        guild_id=1,
        user_id=10,
        bet=100,
        choice="cara",
    )
    win = await casino.play_coin_flip(
        guild_id=1,
        user_id=10,
        bet=100,
        choice="cara",
    )

    state = await economy.get_credit_protection_state(1, 10)
    wallet = await economy.get_wallet(1, 10)
    history = await economy.list_history(1, 10, limit=20)
    cashback_transactions = [
        transaction
        for transaction in history
        if transaction.type is EconomyTransactionType.CREDIT_CASHBACK
    ]

    assert [result.cashback for result in first_losses] == [0, 0, 0]
    assert fourth.cashback == 50
    assert fourth.profit == -50
    assert fifth.cashback == 80
    assert fifth.profit == -20
    assert sixth.cashback == 0
    assert win.payout == 140
    assert win.profit == 40
    assert state.saves == 0
    assert state.lose_streak == 0
    assert wallet.balance == 570
    assert [transaction.amount for transaction in cashback_transactions] == [80, 50]


async def test_credit_saves_remove_rejects_negative_balance(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "credit_saves.sqlite3")
    economy = EconomyService(repository)

    added = await economy.add_credit_saves(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=4,
        reason="bonus",
    )
    removed = await economy.remove_credit_saves(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1,
        reason="ajuste",
    )

    assert added.after.saves == 4
    assert removed.before.saves == 4
    assert removed.after.saves == 3
    with pytest.raises(EconomyValidationError, match="saves suficientes"):
        await economy.remove_credit_saves(
            guild_id=1,
            user_id=10,
            actor_id=99,
            amount=4,
            reason="ajuste",
        )


async def test_shop_level_upgrade_debits_wallet_once(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "level_upgrades.sqlite3")
    economy = EconomyService(repository)
    shop = ShopService(repository)

    level_one = await shop.configure_level(
        guild_id=1,
        level=1,
        role_id=101,
        price=200,
        is_active=True,
        actor_id=99,
        saves_reward=2,
    )
    await shop.configure_level(
        guild_id=1,
        level=2,
        role_id=102,
        price=500,
        is_active=True,
        actor_id=99,
        saves_reward=3,
    )
    current_level, next_level, levels = await shop.get_next_level(
        guild_id=1,
        user_id=10,
    )

    assert current_level == 0
    assert next_level == level_one
    assert [level.level for level in levels] == [1, 2]

    insufficient = await shop.purchase_level_upgrade(
        guild_id=1,
        user_id=10,
        level=1,
    )
    assert insufficient.status is LevelUpgradeStatus.INSUFFICIENT_BALANCE
    assert insufficient.missing_points == 200

    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=300,
        reason="seed",
    )
    purchase = await shop.purchase_level_upgrade(
        guild_id=1,
        user_id=10,
        level=1,
    )
    wallet = await economy.get_wallet(1, 10)
    upgrades = await shop.list_user_level_upgrades(1, 10)
    history = await economy.list_history(1, 10)

    assert purchase.status is LevelUpgradeStatus.SUCCESS
    assert purchase.balance_before == 300
    assert purchase.balance_after == 100
    assert wallet.balance == 100
    assert wallet.total_spent == 200
    assert [upgrade.level for upgrade in upgrades] == [1]
    assert history[0].type is EconomyTransactionType.LEVEL_UPGRADE
    assert history[0].metadata["role_id"] == 101
    assert history[0].metadata["saves_reward"] == 2
    protection = await economy.get_credit_protection_state(1, 10)
    assert protection.saves == 2

    repeated = await shop.purchase_level_upgrade(
        guild_id=1,
        user_id=10,
        level=1,
    )
    wallet_after_repeat = await economy.get_wallet(1, 10)
    protection_after_repeat = await economy.get_credit_protection_state(1, 10)
    assert repeated.status is LevelUpgradeStatus.ALREADY_OWNED
    assert wallet_after_repeat.balance == 100
    assert protection_after_repeat.saves == 2

    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=500,
        reason="seed nivel 2",
    )
    second_purchase = await shop.purchase_level_upgrade(
        guild_id=1,
        user_id=10,
        level=2,
    )
    protection_after_second = await economy.get_credit_protection_state(1, 10)
    assert second_purchase.status is LevelUpgradeStatus.SUCCESS
    assert protection_after_second.saves == 5


async def test_shop_reward_update_and_remove() -> None:
    db_path = Path("tests") / "tmp_shop_update.sqlite3"
    _cleanup_sqlite(db_path)

    try:
        repository = SQLiteEconomyRepository(db_path)
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
            duration_days=30,
        )

        assert reward.duration_days == 30

        updated = await shop.update_reward(
            guild_id=1,
            reward_id=reward.id,
            actor_id=99,
            name="VIP Plus",
            price=250,
            stock_quantity=5,
            stock_mode=StockMode.LIMITED,
            max_per_user=0,
            duration_days=7,
            is_active=False,
        )

        assert updated.name == "VIP Plus"
        assert updated.price == 250
        assert updated.stock_quantity == 5
        assert updated.max_per_user is None
        assert updated.duration_days == 7
        assert updated.is_active is False
        assert await shop.list_rewards(1) == []

        reactivated = await shop.update_reward(
            guild_id=1,
            reward_id=reward.id,
            actor_id=99,
            stock_mode=StockMode.UNLIMITED,
            duration_days=0,
            is_active=True,
        )

        assert reactivated.stock_quantity is None
        assert reactivated.stock_mode is StockMode.UNLIMITED
        assert reactivated.duration_days is None
        assert reactivated.is_active is True
        assert [item.id for item in await shop.list_rewards(1)] == [reward.id]

        removed = await shop.remove_reward(
            guild_id=1,
            reward_id=reward.id,
            actor_id=99,
            reason="teste",
        )

        assert removed.is_active is False
        assert removed.deleted_at is not None
        assert await shop.list_rewards(1) == []
        assert await shop.list_rewards(1, include_inactive=True) == []
    finally:
        repository = None
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
        casino_max_bet=1000,
        casino_daily_profit_limit=5000,
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
            duration_days=7,
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

    levels = [
        LevelConfig(
            guild_id=1,
            level=1,
            role_id=321,
            price=12000,
            is_active=True,
            created_by=99,
            created_at=now,
            updated_at=now,
            saves_reward=2,
        ),
    ]

    embed = build_shop_embed(
        rewards,
        settings,
        image_url="https://cdn.example.com/loja.png",
        levels=levels,
    )

    assert embed.description is not None
    assert embed.image.url == "https://cdn.example.com/loja.png"
    assert "Escolha uma recompensa no menu abaixo" in embed.description
    assert "🎭 **VIP Plus** — 17.000 pontos · Esgotado · 7 dias" in embed.description
    assert (
        "🎁 **Passe Semanal** — 8.000 pontos · 10 un. · Permanente"
        in embed.description
    )
    assert "#3" not in embed.description
    assert "#1" not in embed.description
    assert "Tipo" not in embed.description
    assert "**Upgrades de nível**" in embed.description
    assert "🔰 **Nível 1** · <@&321> · 12.000 pontos · 2 save(s)" in embed.description
    assert "ativo" not in embed.description
    assert "inativo" not in embed.description

    admin_embed = build_shop_embed(
        rewards,
        settings,
        levels=levels,
        show_reward_ids=True,
    )
    assert admin_embed.description is not None
    assert "#3 · VIP Plus" in admin_embed.description


def test_economy_panel_embed_accepts_presentation_image() -> None:
    settings = _activity_settings(count_voice_when_alone=False)

    embed = build_economy_panel_embed(
        settings,
        image_url="https://cdn.example.com/economia.png",
    )

    assert embed.title == "Economia da Comunidade"
    assert embed.image.url == "https://cdn.example.com/economia.png"
    assert embed.fields[0].name == "Conversão atual"
    assert "1 minuto em call = 2 pontos" in embed.fields[0].value
    assert "abrir a loja" not in (embed.description or "")


def test_economy_panel_view_removes_open_shop_button() -> None:
    view = EconomyPanelView(bot=object())  # type: ignore[arg-type]
    custom_ids = {
        getattr(item, "custom_id", None)
        for item in view.children
        if isinstance(item, discord.ui.Button)
    }

    assert "economy_panel:shop" not in custom_ids
    assert "economy_panel:transfer" in custom_ids
    assert "economy_panel:savings" in custom_ids


def test_profile_embed_shows_avatar_balance_badges_and_levels() -> None:
    now = datetime.now(UTC)
    settings = _activity_settings(count_voice_when_alone=False)
    wallet = UserWallet(
        guild_id=1,
        user_id=10,
        balance=30_000,
        total_earned=55_000,
        total_spent=12_000,
        created_at=now,
        updated_at=now,
    )
    level = LevelConfig(
        guild_id=1,
        level=3,
        role_id=333,
        price=15_000,
        is_active=True,
        created_by=99,
        created_at=now,
        updated_at=now,
        saves_reward=2,
    )
    credit_state = CreditProtectionState(
        guild_id=1,
        user_id=10,
        saves=2,
        lose_streak=1,
        updated_at=now,
    )
    badges = build_profile_badges(
        wallet,
        top_wallets=[wallet],
        achievements=[],
        level_upgrades=[],
        credit_state=credit_state,
        owned_levels=[level],
    )

    embed = build_profile_embed(
        wallet,
        settings,
        display_name="Copenhague",
        avatar_url="https://cdn.example.com/avatar.png",
        badges=badges,
        owned_levels=[level],
        ranking_position=1,
        credit_state=credit_state,
    )

    assert embed.title == "Perfil de Copenhague"
    assert embed.thumbnail.url == "https://cdn.example.com/avatar.png"
    assert embed.fields[0].name == "Saldo atual"
    assert embed.fields[0].value == "30.000 pontos"
    assert embed.fields[1].name == "Total ganho"
    assert embed.fields[1].value == "55.000 pontos"
    assert "💰 **Magnata**" in embed.fields[5].value
    assert "🔰 **Nível 3**" in embed.fields[6].value


def test_ranking_image_renders_visual_top_ten() -> None:
    now = datetime.now(UTC)
    settings = _activity_settings(count_voice_when_alone=False)
    wallets = [
        UserWallet(1, 10, 3000, 5000, 2000, now, now),
        UserWallet(1, 20, 2000, 3000, 1000, now, now),
        UserWallet(1, 30, 1000, 2000, 1000, now, now),
        UserWallet(1, 40, 500, 700, 200, now, now),
    ]
    names = {10: "Ana", 20: "Bruno", 30: "Carla", 40: "Diego"}

    image_bytes = render_ranking_podium_image(
        wallets,
        settings,
        display_names=names,
    )

    assert RANKING_IMAGE_FILENAME == "ranking.png"
    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(image_bytes)) as image:
        assert image.size == (900, 1280)


class _RecordingActivityService:
    def __init__(self) -> None:
        self.started: list[int] = []
        self.closed: list[int] = []

    async def start_voice_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        is_bot: bool,
    ) -> None:
        self.started.append(user_id)

    async def close_voice_sessions(
        self,
        *,
        guild_id: int,
        user_id: int,
        is_bot: bool,
        invalid_reason: str | None = None,
    ) -> None:
        self.closed.append(user_id)


class _StaticSettingsRepository:
    def __init__(self, settings: GuildEconomySettings) -> None:
        self._settings = settings

    async def get_guild_settings(self, guild_id: int) -> GuildEconomySettings:
        return self._settings


class _FixedCoinRng:
    def __init__(self, choices: list[CoinSide]) -> None:
        self._choices = choices

    def choice(self, options):
        if not self._choices:
            raise AssertionError("Acabaram os resultados fixos do RNG.")
        return self._choices.pop(0)

    def randint(self, start: int, end: int) -> int:
        return start


def _activity_settings(*, count_voice_when_alone: bool) -> GuildEconomySettings:
    now = datetime.now(UTC)
    return GuildEconomySettings(
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
        count_voice_when_alone=count_voice_when_alone,
        max_admin_grant_per_use=100000,
        casino_max_bet=1000,
        casino_daily_profit_limit=5000,
        economy_manager_role_id=None,
        created_at=now,
        updated_at=now,
    )


def _voice_member(
    user_id: int,
    *,
    bot: bool = False,
    self_mute: bool = False,
    mute: bool = False,
    suppress: bool = False,
):
    return SimpleNamespace(
        id=user_id,
        bot=bot,
        voice=SimpleNamespace(
            self_mute=self_mute,
            mute=mute,
            suppress=suppress,
        ),
    )


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
