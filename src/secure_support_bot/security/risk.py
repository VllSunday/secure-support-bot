from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from secure_support_bot.domain.models import ActorContext, Decision


@dataclass(frozen=True, slots=True)
class RiskContext:
    actor: ActorContext
    request_id: UUID
    order_id: str
    amount: int
    currency: str
    original_request: str


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    decision: Decision
    reason: str


class RiskChecker(Protocol):
    async def assess(self, context: RiskContext) -> RiskAssessment: ...


class AllowRiskChecker:
    async def assess(self, context: RiskContext) -> RiskAssessment:
        del context
        return RiskAssessment(Decision.ALLOW, "risk_policy_allow")


async def assess_with_deadline(
    checker: RiskChecker,
    context: RiskContext,
    *,
    timeout_seconds: float,
) -> RiskAssessment:
    try:
        return await asyncio.wait_for(checker.assess(context), timeout=timeout_seconds)
    except TimeoutError:
        return RiskAssessment(Decision.REVIEW, "risk_timeout")
    except Exception:
        return RiskAssessment(Decision.REVIEW, "risk_unavailable")
