from __future__ import annotations

import json
import random
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.models.giveaway import (
    GiveawayClaim,
    GiveawayCode,
    GiveawayCodeSeed,
    GiveawayCreationResult,
    GiveawayDrawResult,
    GiveawayEvent,
    GiveawayEventCreate,
    GiveawayEventStats,
    GiveawayFinalizationResult,
    GiveawayRewardTier,
    serialize_datetime,
    utc_now,
)
from app.repositories.giveaway_repository import GiveawayRepositoryProtocol


class GiveawayServiceError(Exception):
    """Erro base da camada de giveaway."""


class GiveawayValidationError(GiveawayServiceError):
    """Erro de validacao de entrada do usuario."""


@dataclass(slots=True)
class GiveawayParsedRewardPlan:
    """Resultado intermediario do parser de configuracao de premios."""

    tiers: list[GiveawayRewardTier]
    rewarded_codes: int


class GiveawayService:
    """Regra de negocio do sistema de distribuicao de codigos."""

    def __init__(self, repository: GiveawayRepositoryProtocol) -> None:
        self._repository = repository

    async def create_event(
        self,
        *,
        title: str,
        description: str,
        created_by: int,
        total_codes: int,
        reward_plan: str | None = None,
        max_redemptions: int | None = None,
        code_length: int = 6,
        notify_user_id: int | None = None,
        embed_color: int | None = None,
        expires_in_minutes: int | None = None,
    ) -> GiveawayCreationResult:
        if not title.strip():
            raise GiveawayValidationError("O titulo do evento nao pode ficar vazio.")

        if not description.strip():
            raise GiveawayValidationError("A descricao do evento nao pode ficar vazia.")

        if total_codes <= 0:
            raise GiveawayValidationError(
                "A quantidade total de codigos precisa ser maior que zero."
            )

        if code_length < 4:
            raise GiveawayValidationError(
                "O tamanho do codigo precisa ter pelo menos 4 caracteres."
            )

        if total_codes > 16**code_length:
            raise GiveawayValidationError(
                "A quantidade de codigos solicitada excede o espaco possivel "
                "para o tamanho atual do codigo."
            )

        if expires_in_minutes is not None and expires_in_minutes <= 0:
            raise GiveawayValidationError(
                "O tempo de publicacao precisa ser maior que zero."
            )

        parsed_plan = self.parse_reward_plan(reward_plan)
        if parsed_plan.rewarded_codes > total_codes:
            raise GiveawayValidationError(
                "A soma das quantidades de premio nao pode ser maior que o total de "
                "codigos do evento."
            )

        generated_codes = self._generate_unique_hex_codes(total_codes, code_length)
        reward_slots: list[GiveawayRewardTier] = [
            tier for tier in parsed_plan.tiers for _ in range(tier.quantity)
        ]

        rng = random.SystemRandom()
        rng.shuffle(generated_codes)
        rng.shuffle(reward_slots)

        code_seeds: list[GiveawayCodeSeed] = []
        reward_cursor = 0
        for code in generated_codes:
            if reward_cursor < len(reward_slots):
                reward = reward_slots[reward_cursor]
                reward_cursor += 1
                code_seeds.append(
                    GiveawayCodeSeed(
                        code=code,
                        reward_name=reward.reward_name,
                        reward_amount=reward.reward_amount,
                    )
                )
                continue

            code_seeds.append(
                GiveawayCodeSeed(
                    code=code,
                    reward_name=None,
                    reward_amount=None,
                )
            )

        expires_at = (
            utc_now() + timedelta(minutes=expires_in_minutes)
            if expires_in_minutes is not None
            else None
        )

        event = await self._repository.create_event(
            GiveawayEventCreate(
                title=title.strip(),
                description=description.strip(),
                created_by=created_by,
                created_at=utc_now(),
                total_codes=total_codes,
                max_redemptions=max_redemptions or total_codes,
                notify_user_id=notify_user_id,
                embed_color=embed_color,
                expires_at=expires_at,
            ),
            code_seeds,
        )

        return GiveawayCreationResult(
            event=event,
            rewarded_codes=parsed_plan.rewarded_codes,
            reward_tiers=parsed_plan.tiers,
        )

    async def publish_event(
        self,
        event_id: int,
        *,
        channel_id: int,
        message_id: int,
        embed_color: int | None = None,
        expires_in_minutes: int | None = None,
    ) -> GiveawayEvent:
        expires_at = (
            serialize_datetime(utc_now() + timedelta(minutes=expires_in_minutes))
            if expires_in_minutes is not None
            else None
        )
        return await self._repository.update_event_publication(
            event_id,
            channel_id=channel_id,
            message_id=message_id,
            embed_color=embed_color,
            expires_at=expires_at,
        )

    async def get_event(self, event_id: int) -> GiveawayEvent | None:
        return await self._repository.get_event(event_id)

    async def get_event_stats(self, event_id: int) -> GiveawayEventStats | None:
        return await self._repository.get_event_stats(event_id)

    async def get_user_claim(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayClaim | None:
        return await self._repository.get_user_claim(event_id, user_id)

    async def draw_code_for_user(
        self,
        event_id: int,
        user_id: int,
    ) -> GiveawayDrawResult:
        return await self._repository.claim_next_available_code(event_id, user_id)

    async def list_active_published_events(self) -> list[GiveawayEvent]:
        return await self._repository.list_active_published_events()

    async def list_remaining_codes(self, event_id: int) -> list[GiveawayCode]:
        return await self._repository.list_remaining_codes(event_id)

    async def finalize_event(self, event_id: int) -> GiveawayFinalizationResult:
        return await self._repository.finalize_event(event_id)

    async def get_expiring_events(self) -> list[GiveawayEvent]:
        now = serialize_datetime(utc_now())
        return await self._repository.get_events_expiring_at_or_before(now)

    @staticmethod
    def parse_reward_plan(
        reward_plan: str | None,
    ) -> GiveawayParsedRewardPlan:
        if reward_plan is None or not reward_plan.strip():
            return GiveawayParsedRewardPlan(tiers=[], rewarded_codes=0)

        raw = reward_plan.strip()
        tiers: list[GiveawayRewardTier] = []

        if raw.startswith("["):
            tiers = GiveawayService._parse_reward_plan_json(raw)
        else:
            tiers = GiveawayService._parse_reward_plan_compact(raw)

        rewarded_codes = sum(tier.quantity for tier in tiers)
        return GiveawayParsedRewardPlan(tiers=tiers, rewarded_codes=rewarded_codes)

    @staticmethod
    def _parse_reward_plan_json(raw: str) -> list[GiveawayRewardTier]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GiveawayValidationError(
                "Nao foi possivel ler o plano de premios em JSON."
            ) from exc

        if not isinstance(data, list):
            raise GiveawayValidationError(
                "O plano de premios em JSON precisa ser uma lista."
            )

        tiers: list[GiveawayRewardTier] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise GiveawayValidationError(
                    f"O item {index} do plano de premios precisa ser um objeto."
                )

            try:
                name = str(
                    item.get("name")
                    or item.get("reward_name")
                    or item.get("reward_type")
                    or "Premio"
                ).strip()
                amount = int(
                    item.get("amount")
                    if item.get("amount") is not None
                    else (
                        item.get("reward_amount")
                        if item.get("reward_amount") is not None
                        else item.get("value")
                    )
                )
                quantity = int(
                    item.get("quantity")
                    if item.get("quantity") is not None
                    else (
                        item.get("reward_quantity")
                        if item.get("reward_quantity") is not None
                        else item.get("qty")
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GiveawayValidationError(
                    f"O item {index} do plano de premios possui campos invalidos."
                ) from exc

            GiveawayService._validate_reward_tier(name, amount, quantity)
            tiers.append(
                GiveawayRewardTier(
                    reward_name=name,
                    reward_amount=amount,
                    quantity=quantity,
                )
            )

        return tiers

    @staticmethod
    def _parse_reward_plan_compact(raw: str) -> list[GiveawayRewardTier]:
        tiers: list[GiveawayRewardTier] = []
        chunks = [chunk.strip() for chunk in raw.split(";") if chunk.strip()]

        for index, chunk in enumerate(chunks, start=1):
            name = "Premio"
            amount_raw: str
            quantity_raw: str

            if "|" in chunk:
                parts = [part.strip() for part in chunk.split("|")]
                if len(parts) == 3:
                    name, amount_raw, quantity_raw = parts
                elif len(parts) == 2:
                    amount_raw, quantity_raw = parts
                else:
                    raise GiveawayValidationError(
                        "Use o formato nome|valor|quantidade ou valor|quantidade."
                    )
            elif "x" in chunk.lower():
                amount_raw, quantity_raw = re.split(r"[xX]", chunk, maxsplit=1)
            else:
                raise GiveawayValidationError(
                    "Use o formato nome|valor|quantidade ou valorxquantidade."
                )

            name = name.strip() or "Premio"
            try:
                amount = int(amount_raw.strip())
                quantity = int(quantity_raw.strip())
            except ValueError as exc:
                raise GiveawayValidationError(
                    f"O item {index} do plano de premios possui valores invalidos."
                ) from exc

            GiveawayService._validate_reward_tier(name, amount, quantity)
            tiers.append(
                GiveawayRewardTier(
                    reward_name=name,
                    reward_amount=amount,
                    quantity=quantity,
                )
            )

        return tiers

    @staticmethod
    def _validate_reward_tier(name: str, amount: int, quantity: int) -> None:
        if not name.strip():
            raise GiveawayValidationError("O nome do premio nao pode ficar vazio.")

        if amount <= 0:
            raise GiveawayValidationError("O valor do premio precisa ser maior que 0.")

        if quantity <= 0:
            raise GiveawayValidationError(
                "A quantidade de codigos premiados precisa ser maior que 0."
            )

    @staticmethod
    def _generate_unique_hex_codes(total_codes: int, length: int) -> list[str]:
        alphabet = "0123456789ABCDEF"
        codes: set[str] = set()

        while len(codes) < total_codes:
            code = "".join(secrets.choice(alphabet) for _ in range(length))
            codes.add(code)

        return list(codes)
