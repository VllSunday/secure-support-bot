from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from secure_support_bot.application.service import SupportService
from secure_support_bot.domain.models import ActorContext, CompanySlug
from secure_support_bot.infrastructure.memory import InMemoryStore
from secure_support_bot.security.risk import AllowRiskChecker


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def service(store: InMemoryStore) -> SupportService:
    return SupportService(
        store=store,
        risk_checker=AllowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
        risk_timeout_seconds=0.05,
    )


@pytest.fixture
async def alpha_actor(service: SupportService) -> AsyncIterator[ActorContext]:
    for telegram_user_id in range(1000, 1100):
        actor = await service.start(telegram_user_id)
        if actor.company is CompanySlug.ALPHA:
            yield actor
            return
    raise AssertionError("test setup could not create an alpha actor")
