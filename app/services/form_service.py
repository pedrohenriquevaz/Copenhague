from __future__ import annotations

from app.models.form import (
    FormDefinition,
    FormDefinitionCreate,
    FormQuestion,
    FormQuestionType,
    FormSubmitResult,
)
from app.models.giveaway import utc_now
from app.repositories.form_repository import FormRepositoryProtocol


class FormServiceError(Exception):
    """Erro base da camada de formularios."""


class FormValidationError(FormServiceError):
    """Erro de validacao de entrada do formulario."""


class FormService:
    """Regras de negocio para formularios dinamicos."""

    MAX_QUESTIONS = 9
    MAX_SHORT_QUESTIONS = 5
    MAX_SELECT_QUESTIONS = 4
    MAX_OPTIONS_PER_SELECT = 25

    def __init__(self, repository: FormRepositoryProtocol) -> None:
        self._repository = repository

    async def create_form(
        self,
        *,
        title: str,
        description: str,
        response_channel_id: int,
        created_by: int,
        questions_raw: str,
    ) -> FormDefinition:
        title = self._require_text(
            title,
            "O título do formulário nao pode ficar vazio.",
        )
        description = self._require_text(
            description,
            "A descrição do formulário nao pode ficar vazia.",
        )
        questions = self.parse_questions(questions_raw)

        return await self._repository.create_form(
            FormDefinitionCreate(
                title=title,
                description=description,
                response_channel_id=response_channel_id,
                created_by=created_by,
                created_at=utc_now(),
                questions=questions,
            )
        )

    async def publish_form(
        self,
        form_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> FormDefinition:
        return await self._repository.publish_form(
            form_id,
            channel_id=channel_id,
            message_id=message_id,
        )

    async def get_form(self, form_id: int) -> FormDefinition | None:
        return await self._repository.get_form(form_id)

    async def list_active_forms(self) -> list[FormDefinition]:
        return await self._repository.list_active_forms()

    async def close_form(self, form_id: int) -> FormDefinition:
        form = await self._repository.close_form(form_id)
        if form is None:
            raise FormValidationError("Nao encontrei um formulario com esse ID.")
        return form

    async def submit_response(
        self,
        form_id: int,
        user_id: int,
        answers: dict[str, str],
    ) -> FormSubmitResult:
        form = await self.get_form(form_id)
        if form is None:
            return await self._repository.submit_response(form_id, user_id, answers)

        normalized_answers = self.validate_answers(form, answers)
        return await self._repository.submit_response(
            form_id,
            user_id,
            normalized_answers,
        )

    @classmethod
    def parse_questions(cls, raw: str) -> list[FormQuestion]:
        text = cls._require_text(raw, "Informe pelo menos uma pergunta.")
        questions: list[FormQuestion] = []

        for index, item in enumerate(text.split(";"), start=1):
            item = item.strip()
            if not item:
                continue

            parts = [part.strip() for part in item.split("|")]
            if len(parts) < 2:
                raise FormValidationError(
                    "Cada pergunta deve usar o formato tipo|pergunta|opcoes."
                )

            question_type = cls._parse_question_type(parts[0])
            label = cls._require_text(parts[1], "A pergunta nao pode ficar vazia.")
            options = cls._parse_options(parts[2] if len(parts) >= 3 else "")

            if question_type is FormQuestionType.SHORT and options:
                raise FormValidationError(
                    "Perguntas curtas nao devem receber opcoes."
                )

            if question_type is not FormQuestionType.SHORT and len(options) < 2:
                raise FormValidationError(
                    "Perguntas de selecao precisam ter pelo menos duas opcoes."
                )

            questions.append(
                FormQuestion(
                    id=f"q{index}",
                    label=label[:100],
                    type=question_type,
                    options=options,
                )
            )

        cls._validate_question_limits(questions)
        return questions

    @classmethod
    def validate_answers(
        cls,
        form: FormDefinition,
        answers: dict[str, str],
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for question in form.questions:
            answer = answers.get(question.id, "").strip()
            if question.required and not answer:
                raise FormValidationError(
                    f"A pergunta '{question.label}' precisa ser respondida."
                )

            if question.type is FormQuestionType.SHORT:
                normalized[question.id] = answer[:1000]
                continue

            selected = [item.strip() for item in answer.split(",") if item.strip()]
            invalid = [item for item in selected if item not in question.options]
            if invalid:
                raise FormValidationError(
                    f"A pergunta '{question.label}' recebeu uma opção invalida."
                )

            if question.type is FormQuestionType.SELECT and len(selected) != 1:
                raise FormValidationError(
                    f"A pergunta '{question.label}' aceita apenas uma opção."
                )

            normalized[question.id] = ", ".join(selected)

        return normalized

    @classmethod
    def _validate_question_limits(cls, questions: list[FormQuestion]) -> None:
        if not questions:
            raise FormValidationError("Informe pelo menos uma pergunta.")

        if len(questions) > cls.MAX_QUESTIONS:
            raise FormValidationError(
                f"O formulario aceita no maximo {cls.MAX_QUESTIONS} perguntas."
            )

        short_count = sum(
            1 for question in questions if question.type is FormQuestionType.SHORT
        )
        if short_count > cls.MAX_SHORT_QUESTIONS:
            raise FormValidationError(
                "O Discord permite no maximo 5 respostas curtas por modal."
            )

        select_count = len(questions) - short_count
        if select_count > cls.MAX_SELECT_QUESTIONS:
            raise FormValidationError(
                "O formulario aceita no maximo 4 perguntas de seleção."
            )

        for question in questions:
            if len(question.options) > cls.MAX_OPTIONS_PER_SELECT:
                raise FormValidationError(
                    "Cada pergunta de seleção aceita no maximo 25 opcoes."
                )

    @staticmethod
    def _parse_question_type(raw: str) -> FormQuestionType:
        normalized = raw.strip().lower().replace("-", "_")
        aliases = {
            "curta": FormQuestionType.SHORT,
            "short": FormQuestionType.SHORT,
            "texto": FormQuestionType.SHORT,
            "combo": FormQuestionType.SELECT,
            "select": FormQuestionType.SELECT,
            "selecao": FormQuestionType.SELECT,
            "multipla": FormQuestionType.MULTI_SELECT,
            "multiple": FormQuestionType.MULTI_SELECT,
            "multi": FormQuestionType.MULTI_SELECT,
            "multipla_escolha": FormQuestionType.MULTI_SELECT,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise FormValidationError(
                "Tipo de pergunta invalido. Use curta, combo ou multipla."
            ) from exc

    @staticmethod
    def _parse_options(raw: str) -> list[str]:
        options: list[str] = []
        seen: set[str] = set()
        for option in raw.split(","):
            normalized = option.strip()
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            options.append(normalized[:100])
            seen.add(key)
        return options

    @staticmethod
    def _require_text(value: str, message: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise FormValidationError(message)
        return normalized
