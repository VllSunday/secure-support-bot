from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from secure_support_bot.domain.models import Decision


@dataclass(frozen=True, slots=True)
class ServiceResult:
    decision: Decision
    reason: str
    message: str
    request_id: UUID | None = None
    confirmation_token: str | None = None
    payload: Any = None
    idempotent_replay: bool = False
