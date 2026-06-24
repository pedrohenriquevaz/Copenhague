from __future__ import annotations

from app.models.bolao import (
    BolaoEvent,
    BolaoEventCreate,
    BolaoGuess,
    BolaoGuessResult,
)
from app.models.giveaway import utc_now
from app.repositories.bolao_repository import BolaoRepositoryProtocol


class BolaoServiceError(Exception):
    """Erro base da camada de bolao."""


class BolaoValidationError(BolaoServiceError):
    """Erro de validacao de entrada do bolao."""


class BolaoService:
    """Regras de negocio para eventos de bolao."""

    def __init__(self, repository: BolaoRepositoryProtocol) -> None:
        self._repository = repository

    async def create_event(
        self,
        *,
        title: str,
        description: str,
        prize: str,
        team_1: str,
        team_2: str,
        created_by: int,
        receiver_user_id: int,
    ) -> BolaoEvent:
        title = self._require_text(title, "O titulo do bolao nao pode ficar vazio.")
        description = self._require_text(
            description,
            "A descricao do bolao nao pode ficar vazia.",
        )
        prize = self._require_text(prize, "A premiacao do bolao nao pode ficar vazia.")
        team_1 = self._require_text(team_1, "O time 1 nao pode ficar vazio.")
        team_2 = self._require_text(team_2, "O time 2 nao pode ficar vazio.")

        if team_1.casefold() == team_2.casefold():
            raise BolaoValidationError("Os times do bolao precisam ser diferentes.")

        return await self._repository.create_event(
            BolaoEventCreate(
                title=title,
                description=description,
                prize=prize,
                team_1=team_1,
                team_2=team_2,
                created_by=created_by,
                receiver_user_id=receiver_user_id,
                created_at=utc_now(),
            )
        )

    async def publish_event(
        self,
        bolao_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> BolaoEvent:
        return await self._repository.publish_event(
            bolao_id,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_event(self, bolao_id: int) -> BolaoEvent | None:
        return await self._repository.get_event(bolao_id)

    async def get_event_by_message_id(self, message_id: int) -> BolaoEvent | None:
        return await self._repository.get_event_by_message_id(message_id)

    async def list_active_events(self) -> list[BolaoEvent]:
        return await self._repository.list_active_events()

    async def close_event(self, bolao_id: int) -> BolaoEvent:
        event = await self._repository.close_event(bolao_id)
        if event is None:
            raise BolaoValidationError("Nao encontrei um bolao com esse ID.")
        return event

    async def create_guess(
        self,
        bolao_id: int,
        user_id: int,
        score_team_1: int,
        score_team_2: int,
    ) -> BolaoGuessResult:
        self.validate_score(score_team_1)
        self.validate_score(score_team_2)
        return await self._repository.create_guess(
            bolao_id,
            user_id,
            score_team_1,
            score_team_2,
        )

    async def list_winning_guesses(
        self,
        bolao_id: int,
        score_team_1: int,
        score_team_2: int,
    ) -> list[BolaoGuess]:
        self.validate_score(score_team_1)
        self.validate_score(score_team_2)
        event = await self.get_event(bolao_id)
        if event is None:
            raise BolaoValidationError("Nao encontrei um bolao com esse ID.")

        return await self._repository.list_winning_guesses(
            bolao_id,
            score_team_1,
            score_team_2,
        )

    @staticmethod
    def validate_score(score: int) -> None:
        if score < 0:
            raise BolaoValidationError("O placar nao pode ser negativo.")

        if score > 99:
            raise BolaoValidationError("O placar maximo aceito e 99.")

    @staticmethod
    def _require_text(value: str, message: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise BolaoValidationError(message)
        return normalized
