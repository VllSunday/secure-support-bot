from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from secure_support_bot.application.service import SupportService
from secure_support_bot.domain.models import ActorContext, CompanySlug, Decision
from secure_support_bot.infrastructure.sql import SqlStore
from secure_support_bot.security.risk import AllowRiskChecker, RiskAssessment, RiskContext


async def _alpha_actor(service: SupportService, start_id: int = 92000) -> ActorContext:
    for telegram_user_id in range(start_id, start_id + 200):
        actor = await service.start(telegram_user_id)
        if actor.company is CompanySlug.ALPHA:
            return actor
    raise AssertionError("test setup could not create an alpha actor")


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


@pytest.mark.asyncio
async def test_sql_store_keeps_documents_and_orders_tenant_scoped(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    store = SqlStore(database_url)
    await store.create_schema()
    service = SupportService(
        store=store,  # type: ignore[arg-type]
        risk_checker=AllowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
    )

    actor = await _alpha_actor(service)
    documents = await store.search_documents(actor, "BETA-ONLY доставка")
    own_orders = await store.list_owned_orders(actor)
    foreign_refund = await service.propose_refund(
        actor=actor,
        order_id=store.foreign_order_id(actor.company),
        amount=1_000,
        original_request="верни 1000 по чужому заказу",
    )
    too_large = await service.propose_refund(
        actor=actor,
        order_id=own_orders[0].id,
        amount=6_000,
        original_request="верни 6000",
    )

    assert all(document.company is actor.company for document in documents)
    assert all(document.company is not CompanySlug.BETA for document in documents)
    assert foreign_refund.decision is Decision.DENY
    assert too_large.decision is Decision.DENY
    assert await store.count_refund_operations() == 0
    await store.close()


class _SlowRiskChecker:
    async def assess(self, context: RiskContext) -> RiskAssessment:
        del context
        await asyncio.sleep(0.2)
        return RiskAssessment(Decision.ALLOW, "late_allow")


@pytest.mark.asyncio
async def test_sql_store_risk_timeout_never_executes_refund(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'timeout.db'}"
    store = SqlStore(database_url)
    await store.create_schema()
    service = SupportService(
        store=store,  # type: ignore[arg-type]
        risk_checker=_SlowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
        risk_timeout_seconds=0.01,
    )

    actor = await service.start(93001)
    order = (await store.list_owned_orders(actor))[0]
    proposal = await service.propose_refund(
        actor=actor,
        order_id=order.id,
        amount=1_000,
        original_request="верни 1000",
    )
    result = await service.confirm_refund(actor, proposal.confirmation_token or "")

    assert result.decision is Decision.REVIEW
    assert result.reason == "risk_timeout"
    assert await store.count_refund_operations() == 0
    persisted = await store.get_owned_order(actor, order.id)
    assert persisted is not None
    assert persisted.refunded_amount == 0
    await store.close()
