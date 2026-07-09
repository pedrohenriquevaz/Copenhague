from __future__ import annotations

from pathlib import Path

import pytest

from app.models.economy import EconomyTransactionType
from app.models.match_bet import MatchBetTicketStatus
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.match_bet_repository import SQLiteMatchBetRepository
from app.services.match_bet_service import MatchBetService, MatchBetValidationError


async def test_match_bet_locks_odds_and_pays_multiple_tickets(
    tmp_path: Path,
) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, balance=1000)

    match = await service.create_match(
        guild_id=1,
        title="Final do Campeonato",
        team_1="Time Azul",
        team_2="Time Rosa",
        odd_team_1=1.50,
        odd_team_2=2.00,
        created_by=99,
    )

    first = await service.place_bet(
        guild_id=1,
        user_id=10,
        match_id=match.id,
        team="team_1",
        stake=100,
    )
    updated = await service.update_odds(
        guild_id=1,
        match_id=match.id,
        odd_team_1=2.50,
        odd_team_2=1.40,
    )
    second = await service.place_bet(
        guild_id=1,
        user_id=10,
        match_id=updated.id,
        team="team_1",
        stake=100,
    )

    result = await service.settle_match(
        guild_id=1,
        match_id=match.id,
        winner="team_1",
    )
    wallet = await economy.get_wallet(1, 10)

    assert first.ticket.odd_bps == 150
    assert first.ticket.potential_payout == 150
    assert second.ticket.odd_bps == 250
    assert second.ticket.potential_payout == 250
    assert result.winning_tickets == 2
    assert result.total_paid == 400
    assert wallet.balance == 1200


async def test_match_bet_insufficient_balance_does_not_create_ticket(
    tmp_path: Path,
) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, balance=50)
    match = await service.create_match(
        guild_id=1,
        title="Semi",
        team_1="A",
        team_2="B",
        odd_team_1=1.80,
        odd_team_2=1.90,
        created_by=99,
    )

    with pytest.raises(MatchBetValidationError, match="Saldo insuficiente"):
        await service.place_bet(
            guild_id=1,
            user_id=10,
            match_id=match.id,
            team="team_2",
            stake=100,
        )

    result = await service.settle_match(
        guild_id=1,
        match_id=match.id,
        winner="team_2",
    )

    assert result.tickets == []


async def test_match_bet_uses_configured_min_stake(tmp_path: Path) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_min_bet_match_bet": 150})
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, balance=1000)
    match = await service.create_match(
        guild_id=1,
        title="Semi",
        team_1="A",
        team_2="B",
        odd_team_1=1.80,
        odd_team_2=1.90,
        created_by=99,
    )

    with pytest.raises(MatchBetValidationError, match="aposta minima"):
        await service.place_bet(
            guild_id=1,
            user_id=10,
            match_id=match.id,
            team="team_1",
            stake=100,
        )


async def test_match_bet_cancel_refunds_open_tickets(tmp_path: Path) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, balance=1000)
    match = await service.create_match(
        guild_id=1,
        title="Cancelada",
        team_1="A",
        team_2="B",
        odd_team_1="1.80",
        odd_team_2="1,90",
        created_by=99,
    )

    await service.place_bet(
        guild_id=1,
        user_id=10,
        match_id=match.id,
        team="team_2",
        stake=250,
    )
    result = await service.settle_match(
        guild_id=1,
        match_id=match.id,
        winner="cancelar",
    )
    wallet = await economy.get_wallet(1, 10)

    assert result.refunded_tickets == 1
    assert result.total_refunded == 250
    assert result.tickets[0].status is MatchBetTicketStatus.REFUNDED
    assert wallet.balance == 1000


async def test_match_bet_admin_summary(tmp_path: Path) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, balance=1000)
    match = await service.create_match(
        guild_id=1,
        title="Final",
        team_1="A",
        team_2="B",
        odd_team_1=1.80,
        odd_team_2=2.10,
        created_by=99,
    )

    await service.place_bet(
        guild_id=1,
        user_id=10,
        match_id=match.id,
        team="team_1",
        stake=100,
    )

    summary = await repository.get_admin_summary(1)

    assert summary["total_matches"] == 1
    assert summary["active_matches"] == 1
    assert summary["total_tickets"] == 1
    assert summary["open_tickets"] == 1
    assert summary["total_stake"] == 100
    assert summary["potential_payout"] == 180


async def test_match_bet_reset_user_profile_clears_only_user_tickets(
    tmp_path: Path,
) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    repository = SQLiteMatchBetRepository(tmp_path / "bets.db")
    service = MatchBetService(repository, economy)
    await _seed_wallet(economy, user_id=10, balance=1000)
    await _seed_wallet(economy, user_id=20, balance=1000)
    match = await service.create_match(
        guild_id=1,
        title="Final",
        team_1="A",
        team_2="B",
        odd_team_1=1.80,
        odd_team_2=2.10,
        created_by=99,
    )

    await service.place_bet(
        guild_id=1,
        user_id=10,
        match_id=match.id,
        team="team_1",
        stake=100,
    )
    await service.place_bet(
        guild_id=1,
        user_id=20,
        match_id=match.id,
        team="team_2",
        stake=200,
    )

    counts = await repository.reset_user_profile(1, 10)
    summary = await repository.get_admin_summary(1)

    assert counts["match_bet_tickets"] == 1
    assert summary["total_matches"] == 1
    assert summary["total_tickets"] == 1
    assert summary["open_tickets"] == 1
    assert summary["total_stake"] == 200


async def _seed_wallet(
    repository: SQLiteEconomyRepository,
    *,
    user_id: int = 10,
    balance: int,
) -> None:
    await repository.mutate_balance(
        guild_id=1,
        user_id=user_id,
        amount=balance,
        transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
        actor_id=None,
        reason="test_seed",
        metadata={"source": "test"},
    )
