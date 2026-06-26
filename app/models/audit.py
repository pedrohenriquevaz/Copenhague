from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AdminAuditLog:
    """Registro de auditoria administrativa."""

    id: int
    guild_id: int
    actor_id: int
    action: str
    target_user_id: int | None
    target_resource_id: str | None
    before_data: dict[str, Any]
    after_data: dict[str, Any]
    reason: str | None
    created_at: datetime
