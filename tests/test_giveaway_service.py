from __future__ import annotations

import gc
from pathlib import Path

from app.models.giveaway import GiveawayDrawStatus
from app.repositories.giveaway_repository import SQLiteGiveawayRepository
from app.services.giveaway_service import GiveawayService


def test_parse_reward_plan_supports_compact_and_json() -> None:
    compact = GiveawayService.parse_reward_plan("Diamantes|100|2;200|1")
    assert compact.rewarded_codes == 3
    assert compact.tiers[0].reward_name == "Diamantes"
    assert compact.tiers[0].reward_amount == 100
    assert compact.tiers[0].quantity == 2

    json_plan = GiveawayService.parse_reward_plan(
        '[{"reward_name":"XP","reward_amount":50,"reward_quantity":4}]'
    )
    assert json_plan.rewarded_codes == 4
    assert json_plan.tiers[0].reward_name == "XP"
    assert json_plan.tiers[0].reward_amount == 50
    assert json_plan.tiers[0].quantity == 4


async def test_giveaway_service_creates_and_draws_codes() -> None:
    db_path = Path("tests") / "tmp_giveaways.sqlite3"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = SQLiteGiveawayRepository(db_path)
        service = GiveawayService(repository)

        creation = await service.create_event(
            title="Evento",
            description="Descricao do evento",
            created_by=123,
            total_codes=3,
            reward_plan="Diamantes|100|1;Diamantes|200|1",
        )

        event = creation.event
        stats = await service.get_event_stats(event.id)

        assert creation.rewarded_codes == 2
        assert stats is not None
        assert stats.total_codes == 3
        assert stats.rewarded_codes == 2
        assert stats.available_codes == 3

        first_draw = await service.draw_code_for_user(event.id, 10)
        assert first_draw.status is GiveawayDrawStatus.SUCCESS
        assert first_draw.code is not None
        assert first_draw.claim is not None

        repeat_draw = await service.draw_code_for_user(event.id, 10)
        assert repeat_draw.status is GiveawayDrawStatus.ALREADY_CLAIMED
        assert repeat_draw.claim is not None
        assert repeat_draw.claim.code == first_draw.claim.code

        second_draw = await service.draw_code_for_user(event.id, 11)
        assert second_draw.status is GiveawayDrawStatus.SUCCESS
        assert second_draw.code is not None

        third_draw = await service.draw_code_for_user(event.id, 12)
        assert third_draw.status is GiveawayDrawStatus.SUCCESS

        after_sold_out = await service.draw_code_for_user(event.id, 13)
        assert after_sold_out.status is GiveawayDrawStatus.EVENT_INACTIVE
    finally:
        repository = None
        service = None
        gc.collect()
        if db_path.exists():
            db_path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
