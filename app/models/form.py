from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FormQuestionType(StrEnum):
    """Tipos de pergunta aceitos em formularios dinamicos."""

    SHORT = "short"
    SELECT = "select"
    MULTI_SELECT = "multi_select"


@dataclass(slots=True)
class FormQuestion:
    """Pergunta configurada para um formulario."""

    id: str
    label: str
    type: FormQuestionType
    options: list[str]
    required: bool = True


@dataclass(slots=True)
class FormDefinitionCreate:
    """Dados necessarios para criar um formulario."""

    title: str
    description: str
    response_channel_id: int
    created_by: int
    created_at: datetime
    questions: list[FormQuestion]


@dataclass(slots=True)
class FormDefinition:
    """Formulario publicado ou pronto para publicacao."""

    id: int
    title: str
    description: str
    response_channel_id: int
    channel_id: int | None
    message_id: int | None
    created_by: int
    created_at: datetime
    is_active: bool
    questions: list[FormQuestion]


@dataclass(slots=True)
class FormResponse:
    """Resposta enviada por um usuario."""

    id: int
    form_id: int
    user_id: int
    answers: dict[str, str]
    created_at: datetime


class FormSubmitStatus(StrEnum):
    """Estados possiveis ao tentar enviar uma resposta."""

    SUCCESS = "success"
    ALREADY_SUBMITTED = "already_submitted"
    FORM_NOT_FOUND = "form_not_found"
    FORM_CLOSED = "form_closed"


@dataclass(slots=True)
class FormSubmitResult:
    """Resultado completo do envio de resposta."""

    status: FormSubmitStatus
    form: FormDefinition | None = None
    response: FormResponse | None = None
