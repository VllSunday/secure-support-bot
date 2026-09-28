from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from secure_support_bot.application.service import SupportService
from secure_support_bot.domain.models import Decision
from secure_support_bot.infrastructure.sql import SqlStore
from secure_support_bot.security.risk import AllowRiskChecker


@pytest.mark.asyncio
async def test_sql_store_persists_profile_and_idempotent_refund(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'secure.db'}"
    store = SqlStore(database_url)
    await store.create_schema()
    service = SupportService(
        store=store,  # type: ignore[arg-type]
        risk_checker=AllowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
        risk_timeout_seconds=0.05,
    )

    actor = await service.start(91001)
    orders = await store.list_owned_orders(actor)
    assert len(orders) == 1
    request_id = uuid4()
    proposal = await service.propose_refund(
        actor=actor,
        order_id=orders[0].id,
        amount=1_000,
        original_request="верни 1000",
        request_id=request_id,
    )
    first = await service.confirm_refund(actor, proposal.confirmation_token or "")
    replay = await service.confirm_refund(actor, proposal.confirmation_token or "")

    assert first.decision is Decision.ALLOW
    assert replay.idempotent_replay is True
    assert await store.count_refund_operations() == 1

    await store.close()

    reopened = SqlStore(database_url)
    await reopened.create_schema()
    service_reopened = SupportService(
        store=reopened,  # type: ignore[arg-type]
        risk_checker=AllowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
    )
    same_actor = await service_reopened.start(91001)
    persisted_orders = await reopened.list_owned_orders(same_actor)
    assert persisted_orders[0].refunded_amount == 1_000
    assert await reopened.count_refund_operations() == 1
    await reopened.close()
