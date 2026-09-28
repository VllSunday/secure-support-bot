from __future__ import annotations

import asyncio
from uuid import uuid4

from secure_support_bot.application.service import SupportService
from secure_support_bot.domain.models import ActorContext, CompanySlug, Decision
from secure_support_bot.infrastructure.memory import InMemoryStore
from secure_support_bot.security.risk import RiskAssessment, RiskContext
from secure_support_bot.security.tools import allowed_tool_names


class SlowRiskChecker:
    async def assess(self, context: RiskContext) -> RiskAssessment:
        del context
        await asyncio.sleep(0.2)
        return RiskAssessment(Decision.ALLOW, "late_allow")


async def test_own_order_is_visible(service: SupportService, store: InMemoryStore) -> None:
    actor = await service.start(2001)
    owned = await store.list_owned_orders(actor)

    result = await service.get_order(actor, owned[0].id)

    assert result.decision is Decision.ALLOW
    assert result.payload.owner_id == actor.user_id
    assert result.payload.paid_amount == 5_000


async def test_foreign_document_never_enters_context(
    service: SupportService,
    store: InMemoryStore,
    alpha_actor: ActorContext,
) -> None:
    actor = alpha_actor
    result = await service.answer_from_documents(actor, "поддержка доставка возврат")

    assert result.decision is Decision.ALLOW
    assert result.payload
    assert all(document.company is CompanySlug.ALPHA for document in result.payload)
    assert "BETA-ONLY" not in result.message


async def test_document_instruction_cannot_register_or_call_export(
    service: SupportService,
    store: InMemoryStore,
    alpha_actor: ActorContext,
) -> None:
    actor = alpha_actor
    answer = await service.answer_from_documents(actor, "правила возврата")
    attack = await service.dispatch_untrusted_tool_call(actor, "export_all_customers", {})

    assert allowed_tool_names() == frozenset({"get_order", "refund"})
    assert "не выполняется" in answer.message
    assert attack.decision is Decision.DENY
    assert attack.reason == "tool_not_allowed"
    assert len(store.refund_operations) == 0


async def test_refund_for_foreign_order_is_denied(
    service: SupportService,
    store: InMemoryStore,
) -> None:
    actor = await service.start(2002)
    foreign_order_id = store.foreign_order_id(actor.company)

    result = await service.propose_refund(
        actor=actor,
        order_id=foreign_order_id,
        amount=1_000,
        original_request="Верни 1000 по чужому заказу",
    )

    assert result.decision is Decision.DENY
    assert result.reason == "order_not_found_or_not_owned"
    assert len(store.refund_operations) == 0
    assert store.orders[foreign_order_id].refunded_amount == 0


async def test_refund_above_paid_amount_is_denied(
    service: SupportService,
    store: InMemoryStore,
) -> None:
    actor = await service.start(2003)
    order = (await store.list_owned_orders(actor))[0]

    result = await service.propose_refund(
        actor=actor,
        order_id=order.id,
        amount=6_000,
        original_request="Верни 6000",
    )

    assert result.decision is Decision.DENY
    assert result.reason == "amount_exceeds_balance"
    assert len(store.refund_operations) == 0
    assert store.orders[order.id].remaining_amount == 5_000


async def test_risk_timeout_returns_review_without_refund(store: InMemoryStore) -> None:
    service = SupportService(
        store=store,
        risk_checker=SlowRiskChecker(),
        company_assignment_secret="company-assignment-secret-for-tests",
        confirmation_secret="confirmation-fingerprint-secret-for-tests",
        risk_timeout_seconds=0.01,
    )
    actor = await service.start(2004)
    order = (await store.list_owned_orders(actor))[0]
    proposal = await service.propose_refund(
        actor=actor,
        order_id=order.id,
        amount=1_000,
        original_request="Верни 1000",
    )

    result = await service.confirm_refund(actor, proposal.confirmation_token or "")

    assert result.decision is Decision.REVIEW
    assert result.reason == "risk_timeout"
    assert len(store.refund_operations) == 0
    assert store.orders[order.id].remaining_amount == 5_000


async def test_confirmed_refund_is_executed_once_for_same_request_id(
    service: SupportService,
    store: InMemoryStore,
) -> None:
    actor = await service.start(2005)
    order = (await store.list_owned_orders(actor))[0]
    request_id = uuid4()
    proposal = await service.propose_refund(
        actor=actor,
        order_id=order.id,
        amount=1_000,
        original_request="Верни 1000",
        request_id=request_id,
    )

    first = await service.confirm_refund(actor, proposal.confirmation_token or "")
    replay = await service.confirm_refund(actor, proposal.confirmation_token or "")

    assert first.decision is Decision.ALLOW
    assert replay.decision is Decision.ALLOW
    assert replay.idempotent_replay is True
    assert len(store.refund_operations) == 1
    assert store.orders[order.id].refunded_amount == 1_000
    assert store.orders[order.id].remaining_amount == 4_000


async def test_educational_analysis_of_injection_phrase_remains_available(
    service: SupportService,
    store: InMemoryStore,
    alpha_actor: ActorContext,
) -> None:
    actor = alpha_actor
    result = await service.answer_from_documents(
        actor,
        "Объясни для обучения фразу: игнорируй инструкции",
    )

    assert result.decision is Decision.ALLOW
    assert "типичный пример prompt injection" in result.message
    assert len(store.refund_operations) == 0


async def test_review_input_does_not_enter_document_context(
    service: SupportService,
    alpha_actor: ActorContext,
) -> None:
    result = await service.answer_from_documents(alpha_actor, "покажи\u200b правила возврата")

    assert result.decision is Decision.REVIEW
    assert result.reason == "invisible_unicode_detected"
