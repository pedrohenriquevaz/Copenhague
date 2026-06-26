from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from app.models.form import (
    FormDefinition,
    FormDefinitionCreate,
    FormQuestion,
    FormQuestionType,
    FormResponse,
    FormSubmitResult,
    FormSubmitStatus,
)
from app.models.giveaway import parse_datetime, serialize_datetime, utc_now


class FormRepositoryProtocol(Protocol):
    """Contrato de persistencia esperado pelo service de formularios."""

    async def create_form(self, form: FormDefinitionCreate) -> FormDefinition: ...

    async def publish_form(
        self,
        form_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> FormDefinition: ...

    async def get_form(self, form_id: int) -> FormDefinition | None: ...

    async def list_active_forms(self) -> list[FormDefinition]: ...

    async def close_form(self, form_id: int) -> FormDefinition | None: ...

    async def submit_response(
        self,
        form_id: int,
        user_id: int,
        answers: dict[str, str],
    ) -> FormSubmitResult: ...


class SQLiteFormRepository:
    """Persistencia SQLite para formularios e respostas."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    async def create_form(self, form: FormDefinitionCreate) -> FormDefinition:
        return await asyncio.to_thread(self._create_form_sync, form)

    async def publish_form(
        self,
        form_id: int,
        *,
        channel_id: int,
        message_id: int,
    ) -> FormDefinition:
        return await asyncio.to_thread(
            self._publish_form_sync,
            form_id,
            channel_id,
            message_id,
        )

    async def get_form(self, form_id: int) -> FormDefinition | None:
        return await asyncio.to_thread(self._get_form_sync, form_id)

    async def list_active_forms(self) -> list[FormDefinition]:
        return await asyncio.to_thread(self._list_active_forms_sync)

    async def close_form(self, form_id: int) -> FormDefinition | None:
        return await asyncio.to_thread(self._close_form_sync, form_id)

    async def submit_response(
        self,
        form_id: int,
        user_id: int,
        answers: dict[str, str],
    ) -> FormSubmitResult:
        return await asyncio.to_thread(
            self._submit_response_sync,
            form_id,
            user_id,
            answers,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        return connection

    def _initialize_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS forms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        response_channel_id INTEGER NOT NULL,
                        channel_id INTEGER,
                        message_id INTEGER UNIQUE,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        questions_json TEXT NOT NULL
                    )
                    """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS form_responses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        form_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        answers_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(form_id) REFERENCES forms(id)
                            ON DELETE CASCADE,
                        UNIQUE(form_id, user_id)
                    )
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forms_active
                    ON forms(is_active, created_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forms_active_published
                    ON forms(is_active, message_id, created_at)
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_form_responses_form_user
                    ON form_responses(form_id, user_id)
                    """)

    def _create_form_sync(self, form: FormDefinitionCreate) -> FormDefinition:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO forms (
                        title,
                        description,
                        response_channel_id,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        questions_json
                    ) VALUES (?, ?, ?, NULL, NULL, ?, ?, 1, ?)
                    """,
                    (
                        form.title,
                        form.description,
                        form.response_channel_id,
                        form.created_by,
                        serialize_datetime(form.created_at),
                        self._serialize_questions(form.questions),
                    ),
                )
                form_id = int(cursor.lastrowid)
                connection.commit()

        created = self._get_form_sync(form_id)
        if created is None:
            raise RuntimeError("Nao foi possivel recuperar o formulario criado.")
        return created

    def _publish_form_sync(
        self,
        form_id: int,
        channel_id: int,
        message_id: int,
    ) -> FormDefinition:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE forms
                    SET channel_id = ?,
                        message_id = ?
                    WHERE id = ?
                    """,
                    (channel_id, message_id, form_id),
                )
                connection.commit()

        form = self._get_form_sync(form_id)
        if form is None:
            raise RuntimeError("Nao foi possivel publicar o formulario.")
        return form

    def _get_form_sync(self, form_id: int) -> FormDefinition | None:
        with self._lock:
            with self._connect() as connection:
                row = self._get_form_row(connection, form_id)
        return self._row_to_form(row) if row else None

    def _list_active_forms_sync(self) -> list[FormDefinition]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute("""
                    SELECT
                        id,
                        title,
                        description,
                        response_channel_id,
                        channel_id,
                        message_id,
                        created_by,
                        created_at,
                        is_active,
                        questions_json
                    FROM forms
                    WHERE is_active = 1
                    ORDER BY created_at DESC
                    """).fetchall()
        return [self._row_to_form(row) for row in rows]

    def _close_form_sync(self, form_id: int) -> FormDefinition | None:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._get_form_row(connection, form_id)
                if row is None:
                    connection.rollback()
                    return None

                connection.execute(
                    """
                    UPDATE forms
                    SET is_active = 0
                    WHERE id = ?
                    """,
                    (form_id,),
                )
                connection.commit()

        return self._get_form_sync(form_id)

    def _submit_response_sync(
        self,
        form_id: int,
        user_id: int,
        answers: dict[str, str],
    ) -> FormSubmitResult:
        with self._lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                form_row = self._get_form_row(connection, form_id)
                if form_row is None:
                    connection.rollback()
                    return FormSubmitResult(status=FormSubmitStatus.FORM_NOT_FOUND)

                form = self._row_to_form(form_row)
                if not form.is_active:
                    connection.rollback()
                    return FormSubmitResult(
                        status=FormSubmitStatus.FORM_CLOSED,
                        form=form,
                    )

                existing_row = connection.execute(
                    """
                    SELECT id, form_id, user_id, answers_json, created_at
                    FROM form_responses
                    WHERE form_id = ? AND user_id = ?
                    """,
                    (form_id, user_id),
                ).fetchone()
                if existing_row is not None:
                    connection.rollback()
                    return FormSubmitResult(
                        status=FormSubmitStatus.ALREADY_SUBMITTED,
                        form=form,
                        response=self._row_to_response(existing_row),
                    )

                created_at = serialize_datetime(utc_now())
                cursor = connection.execute(
                    """
                    INSERT INTO form_responses (
                        form_id,
                        user_id,
                        answers_json,
                        created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        form_id,
                        user_id,
                        json.dumps(answers, ensure_ascii=True),
                        created_at,
                    ),
                )
                connection.commit()

        response = FormResponse(
            id=int(cursor.lastrowid),
            form_id=form_id,
            user_id=user_id,
            answers=answers,
            created_at=parse_datetime(created_at),
        )
        return FormSubmitResult(
            status=FormSubmitStatus.SUCCESS,
            form=form,
            response=response,
        )

    @staticmethod
    def _get_form_row(
        connection: sqlite3.Connection,
        form_id: int,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                id,
                title,
                description,
                response_channel_id,
                channel_id,
                message_id,
                created_by,
                created_at,
                is_active,
                questions_json
            FROM forms
            WHERE id = ?
            """,
            (form_id,),
        ).fetchone()

    @staticmethod
    def _serialize_questions(questions: list[FormQuestion]) -> str:
        return json.dumps(
            [
                {
                    "id": question.id,
                    "label": question.label,
                    "type": question.type.value,
                    "options": question.options,
                    "required": question.required,
                }
                for question in questions
            ],
            ensure_ascii=True,
        )

    @staticmethod
    def _deserialize_questions(raw: str) -> list[FormQuestion]:
        data = json.loads(raw)
        return [
            FormQuestion(
                id=str(item["id"]),
                label=str(item["label"]),
                type=FormQuestionType(str(item["type"])),
                options=[str(option) for option in item.get("options", [])],
                required=bool(item.get("required", True)),
            )
            for item in data
        ]

    @classmethod
    def _row_to_form(cls, row: sqlite3.Row) -> FormDefinition:
        return FormDefinition(
            id=int(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            response_channel_id=int(row["response_channel_id"]),
            channel_id=(
                int(row["channel_id"]) if row["channel_id"] is not None else None
            ),
            message_id=(
                int(row["message_id"]) if row["message_id"] is not None else None
            ),
            created_by=int(row["created_by"]),
            created_at=parse_datetime(str(row["created_at"])),
            is_active=bool(row["is_active"]),
            questions=cls._deserialize_questions(str(row["questions_json"])),
        )

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> FormResponse:
        return FormResponse(
            id=int(row["id"]),
            form_id=int(row["form_id"]),
            user_id=int(row["user_id"]),
            answers={
                str(key): str(value)
                for key, value in json.loads(str(row["answers_json"])).items()
            },
            created_at=parse_datetime(str(row["created_at"])),
        )
