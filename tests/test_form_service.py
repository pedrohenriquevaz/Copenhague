from __future__ import annotations

import gc
from pathlib import Path

import pytest

from app.models.form import FormQuestionType, FormSubmitStatus
from app.services.form_service import FormService, FormValidationError
from tests.postgres_support import PostgresFormRepository


def test_form_service_parses_dynamic_questions() -> None:
    questions = FormService.parse_questions(
        "curta|Qual seu nome?;"
        "combo|Cargo desejado|Moderador,Suporte;"
        "multipla|Horarios|Manha,Tarde,Noite"
    )

    assert [question.type for question in questions] == [
        FormQuestionType.SHORT,
        FormQuestionType.SELECT,
        FormQuestionType.MULTI_SELECT,
    ]
    assert questions[1].options == ["Moderador", "Suporte"]


def test_form_service_validates_dynamic_questions() -> None:
    with pytest.raises(FormValidationError, match="pelo menos duas"):
        FormService.parse_questions("combo|Cargo|Moderador")

    with pytest.raises(FormValidationError, match="Tipo"):
        FormService.parse_questions("numero|Idade")

    too_many_short = ";".join(f"curta|Pergunta {index}" for index in range(6))
    with pytest.raises(FormValidationError, match="5 respostas curtas"):
        FormService.parse_questions(too_many_short)


async def test_form_service_creates_publishes_and_submits_response() -> None:
    db_path = Path("tests") / "tmp_forms.pg"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = PostgresFormRepository(db_path)
        service = FormService(repository)

        form = await service.create_form(
            title="Staff",
            description="Formulario de staff",
            response_channel_id=123,
            created_by=10,
            questions_raw=(
                "curta|Nome;"
                "combo|Cargo|Moderador,Suporte;"
                "multipla|Turnos|Manha,Tarde,Noite"
            ),
        )
        assert form.id > 0
        assert form.is_active is True
        assert len(form.questions) == 3

        published = await service.publish_form(
            form.id,
            channel_id=456,
            message_id=789,
        )
        assert published.channel_id == 456
        assert published.message_id == 789

        result = await service.submit_response(
            form.id,
            20,
            {"q1": "Pedro", "q2": "Moderador", "q3": "Manha, Noite"},
        )
        assert result.status is FormSubmitStatus.SUCCESS
        assert result.response is not None
        assert result.response.answers["q1"] == "Pedro"

        duplicate = await service.submit_response(
            form.id,
            20,
            {"q1": "Outro", "q2": "Suporte", "q3": "Tarde"},
        )
        assert duplicate.status is FormSubmitStatus.ALREADY_SUBMITTED
    finally:
        repository = None
        service = None
        gc.collect()
        _cleanup_database_files(db_path)


async def test_form_service_closes_form() -> None:
    db_path = Path("tests") / "tmp_forms_close.pg"
    if db_path.exists():
        db_path.unlink()

    try:
        repository = PostgresFormRepository(db_path)
        service = FormService(repository)

        form = await service.create_form(
            title="Staff",
            description="Formulario de staff",
            response_channel_id=123,
            created_by=10,
            questions_raw="curta|Nome",
        )
        assert [item.id for item in await service.list_active_forms()] == [form.id]

        closed = await service.close_form(form.id)
        assert closed.is_active is False
        assert await service.list_active_forms() == []

        result = await service.submit_response(form.id, 20, {"q1": "Pedro"})
        assert result.status is FormSubmitStatus.FORM_CLOSED
    finally:
        repository = None
        service = None
        gc.collect()
        _cleanup_database_files(db_path)


def _cleanup_database_files(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
