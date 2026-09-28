from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from secure_support_bot.application.agents import (
    AnswerAgent,
    MockAnswerAgent,
    MockQuarantineAgent,
    QuarantineAgent,
)
from secure_support_bot.application.results import ServiceResult
from secure_support_bot.domain.models import (
    ActorContext,
    AuditEvent,
    CompanySlug,
    Decision,
    PendingRefund,
    PendingRefundStatus,
)
from secure_support_bot.infrastructure.memory import InMemoryStore
from secure_support_bot.security.fingerprint import refund_fingerprint
from secure_support_bot.security.input_guard import assess_input
from secure_support_bot.security.output import validate_output
from secure_support_bot.security.policy import RefundPolicy
from secure_support_bot.security.risk import RiskChecker, RiskContext, assess_with_deadline
from secure_support_bot.security.tools import (
    GetOrderArguments,
    RefundArguments,
    ToolValidationError,
    validate_tool_call,
)

_PROFILE_NAMESPACE = UUID("266eb5ec-f9f7-454b-ad51-683b7fd5e24e")


class SupportService:
    def __init__(
        self,
        *,
        store: InMemoryStore,
        risk_checker: RiskChecker,
        company_assignment_secret: str,
        confirmation_secret: str,
        risk_timeout_seconds: float = 2.0,
        confirmation_ttl: timedelta = timedelta(minutes=10),
        quarantine_agent: QuarantineAgent | None = None,
        answer_agent: AnswerAgent | None = None,
    ) -> None:
        self._store = store
        self._risk_checker = risk_checker
        self._company_assignment_secret = company_assignment_secret
        self._confirmation_secret = confirmation_secret
        self._risk_timeout_seconds = risk_timeout_seconds
        self._confirmation_ttl = confirmation_ttl
        self._refund_policy = RefundPolicy(confirmation_secret)
        self._quarantine_agent = quarantine_agent or MockQuarantineAgent()
        self._answer_agent = answer_agent or MockAnswerAgent()

    async def start(self, telegram_user_id: int) -> ActorContext:
        profile = await self._store.get_or_create_profile(
            telegram_user_id=telegram_user_id,
            company=self._assign_company(telegram_user_id),
            profile_id=uuid5(_PROFILE_NAMESPACE, f"telegram:{telegram_user_id}"),
        )
        return profile.actor()

    async def get_order(self, actor: ActorContext, order_id: str) -> ServiceResult:
        try:
            arguments = validate_tool_call("get_order", {"order_id": order_id})
        except ToolValidationError as exc:
            return await self._reject_tool(actor, "get_order", str(exc), order_id=order_id)
        if not isinstance(arguments, GetOrderArguments):
            return await self._reject_tool(actor, "get_order", "invalid_tool_arguments")

        order = await self._store.get_owned_order(actor, arguments.order_id)
        if order is None:
            return await self._reject_tool(
                actor,
                "get_order",
                "order_not_found_or_not_owned",
                order_id=arguments.order_id,
            )
        await self._store.append_audit(
            AuditEvent(
                event_type="tool_decision",
                decision=Decision.ALLOW,
                reason_codes=("tool_allowed", "owner_match", "company_match"),
                actor_id=actor.user_id,
                order_id=order.id,
                tool_name="get_order",
            )
        )
        return ServiceResult(
            decision=Decision.ALLOW,
            reason="order_visible",
            message=(
                f"Заказ {order.id}: оплачено {order.paid_amount} {order.currency}, "
                f"возвращено {order.refunded_amount} {order.currency}, "
                f"доступно {order.remaining_amount} {order.currency}."
            ),
            payload=order,
        )

    async def list_orders(self, actor: ActorContext) -> tuple[ServiceResult, ...]:
        orders = await self._store.list_owned_orders(actor)
        results: list[ServiceResult] = []
        for order in orders:
            results.append(await self.get_order(actor, order.id))
        return tuple(results)

    async def propose_refund(
        self,
        *,
        actor: ActorContext,
        order_id: str,
        amount: int,
        original_request: str,
        request_id: UUID | None = None,
        now: datetime | None = None,
    ) -> ServiceResult:
        input_assessment = assess_input(original_request)
        if input_assessment.decision is not Decision.ALLOW:
            return await self._reject_tool(
                actor,
                "refund",
                input_assessment.reason,
                order_id=order_id,
                request_id=request_id,
            )
        resolved_request_id = request_id or uuid4()
        try:
            arguments = validate_tool_call(
                "refund",
                {
                    "request_id": resolved_request_id,
                    "order_id": order_id,
                    "amount": amount,
                    "currency": "DEMO",
                },
            )
        except ToolValidationError as exc:
            return await self._reject_tool(
                actor,
                "refund",
                str(exc),
                order_id=order_id,
                request_id=resolved_request_id,
            )
        if not isinstance(arguments, RefundArguments):
            return await self._reject_tool(
                actor,
                "refund",
                "invalid_tool_arguments",
                order_id=order_id,
                request_id=resolved_request_id,
            )

        order = await self._store.get_owned_order(actor, arguments.order_id)
        if order is None:
            return await self._reject_tool(
                actor,
                "refund",
                "order_not_found_or_not_owned",
                order_id=arguments.order_id,
                request_id=resolved_request_id,
            )
        if arguments.amount > order.remaining_amount:
            return await self._reject_tool(
                actor,
                "refund",
                "amount_exceeds_balance",
                order_id=arguments.order_id,
                request_id=resolved_request_id,
            )

        created_at = now or datetime.now(UTC)
        fingerprint = refund_fingerprint(
            secret=self._confirmation_secret,
            actor_id=actor.user_id,
            company=actor.company,
            order_id=arguments.order_id,
            amount=arguments.amount,
            currency=arguments.currency,
            request_id=arguments.request_id,
            order_version=order.version,
        )
        pending = PendingRefund(
            request_id=arguments.request_id,
            confirmation_token=secrets.token_urlsafe(24),
            actor_id=actor.user_id,
            company=actor.company,
            order_id=arguments.order_id,
            amount=arguments.amount,
            currency=arguments.currency,
            order_version=order.version,
            fingerprint=fingerprint,
            original_request=original_request,
            expires_at=created_at + self._confirmation_ttl,
        )
        stored = await self._store.create_pending(pending)
        if (
            stored.actor_id != pending.actor_id
            or stored.company != pending.company
            or stored.order_id != pending.order_id
            or stored.amount != pending.amount
            or stored.currency != pending.currency
            or stored.fingerprint != pending.fingerprint
        ):
            return await self._reject_tool(
                actor,
                "refund",
                "request_id_reuse_mismatch",
                order_id=order_id,
                request_id=resolved_request_id,
            )
        await self._store.append_audit(
            AuditEvent(
                event_type="refund_proposed",
                decision=Decision.REVIEW,
                reason_codes=("explicit_confirmation_required",),
                actor_id=actor.user_id,
                request_id=stored.request_id,
                order_id=stored.order_id,
                tool_name="refund",
            )
        )
        return ServiceResult(
            decision=Decision.REVIEW,
            reason="confirmation_required",
            message=(
                f"Подтвердите учебный возврат {stored.amount} {stored.currency} "
                f"по заказу {stored.order_id}."
            ),
            request_id=stored.request_id,
            confirmation_token=stored.confirmation_token,
            payload=stored,
        )

    async def confirm_refund(self, actor: ActorContext, confirmation_token: str) -> ServiceResult:
        pending = await self._store.get_pending_by_token(confirmation_token)
        if pending is None or pending.actor_id != actor.user_id or pending.company != actor.company:
            return await self._reject_tool(actor, "refund", "confirmation_not_found")

        if pending.status is PendingRefundStatus.EXECUTED:
            return await self._store.execute_refund(
                actor=actor,
                pending=pending,
                policy=self._refund_policy,
            )

        risk = await assess_with_deadline(
            self._risk_checker,
            RiskContext(
                actor=actor,
                request_id=pending.request_id,
                order_id=pending.order_id,
                amount=pending.amount,
                currency=pending.currency,
                original_request=pending.original_request,
            ),
            timeout_seconds=self._risk_timeout_seconds,
        )
        if risk.decision is not Decision.ALLOW:
            status = (
                PendingRefundStatus.REVIEW
                if risk.decision is Decision.REVIEW
                else PendingRefundStatus.DENIED
            )
            await self._store.set_pending_status(pending.request_id, status)
            await self._store.append_audit(
                AuditEvent(
                    event_type="risk_decision",
                    decision=risk.decision,
                    reason_codes=(risk.reason,),
                    actor_id=actor.user_id,
                    request_id=pending.request_id,
                    order_id=pending.order_id,
                    tool_name="refund",
                )
            )
            return ServiceResult(
                decision=risk.decision,
                reason=risk.reason,
                message="Операция остановлена до дополнительной проверки.",
                request_id=pending.request_id,
            )

        try:
            validate_tool_call(
                "refund",
                {
                    "request_id": pending.request_id,
                    "order_id": pending.order_id,
                    "amount": pending.amount,
                    "currency": pending.currency,
                },
            )
        except ToolValidationError as exc:
            return await self._reject_tool(
                actor,
                "refund",
                str(exc),
                order_id=pending.order_id,
                request_id=pending.request_id,
            )

        result = await self._store.execute_refund(
            actor=actor,
            pending=pending,
            policy=self._refund_policy,
        )
        await self._store.append_audit(
            AuditEvent(
                event_type="refund_decision",
                decision=result.decision,
                reason_codes=(risk.reason, result.reason),
                actor_id=actor.user_id,
                request_id=pending.request_id,
                order_id=pending.order_id,
                tool_name="refund",
            )
        )
        return result

    async def answer_from_documents(self, actor: ActorContext, query: str) -> ServiceResult:
        input_assessment = assess_input(query)
        if input_assessment.decision is not Decision.ALLOW:
            await self._store.append_audit(
                AuditEvent(
                    event_type="input_guard",
                    decision=input_assessment.decision,
                    reason_codes=(input_assessment.reason,),
                    actor_id=actor.user_id,
                )
            )
            return ServiceResult(
                decision=input_assessment.decision,
                reason=input_assessment.reason,
                message=(
                    "Запрос отклонён входным security-фильтром."
                    if input_assessment.decision is Decision.DENY
                    else "Запрос остановлен до дополнительной проверки."
                ),
            )

        documents = await self._store.search_documents(actor, input_assessment.normalized_text)
        if not documents:
            return ServiceResult(
                decision=Decision.ALLOW,
                reason="no_documents_found",
                message="В доступных документах нет подходящей информации.",
                payload=documents,
            )

        quarantined = await self._quarantine_agent.inspect(documents)
        try:
            message = await self._answer_agent.answer(query, quarantined)
        except Exception:
            await self._store.append_audit(
                AuditEvent(
                    event_type="answer_agent",
                    decision=Decision.REVIEW,
                    reason_codes=("answer_agent_unavailable",),
                    actor_id=actor.user_id,
                )
            )
            return ServiceResult(
                decision=Decision.REVIEW,
                reason="answer_agent_unavailable",
                message="Не удалось безопасно сформировать ответ. Повторите запрос позже.",
                payload=documents,
            )
        output_decision, output_reason, safe_message = validate_output(message)
        if output_decision is not Decision.ALLOW:
            message = safe_message
        await self._store.append_audit(
            AuditEvent(
                event_type="document_answer",
                decision=output_decision,
                reason_codes=(
                    "tenant_filter_applied",
                    "untrusted_content_quarantined",
                    output_reason,
                ),
                actor_id=actor.user_id,
            )
        )
        return ServiceResult(
            decision=output_decision,
            reason="document_answered" if output_decision is Decision.ALLOW else output_reason,
            message=message,
            payload=documents,
        )

    async def dispatch_untrusted_tool_call(
        self,
        actor: ActorContext,
        name: str,
        arguments: dict[str, object],
    ) -> ServiceResult:
        try:
            parsed = validate_tool_call(name, arguments)
        except ToolValidationError as exc:
            return await self._reject_tool(actor, name, str(exc))
        if isinstance(parsed, GetOrderArguments):
            return await self.get_order(actor, parsed.order_id)
        return await self._reject_tool(actor, name, "refund_requires_confirmed_server_action")

    async def _reject_tool(
        self,
        actor: ActorContext,
        tool_name: str,
        reason: str,
        *,
        order_id: str | None = None,
        request_id: UUID | None = None,
    ) -> ServiceResult:
        await self._store.append_audit(
            AuditEvent(
                event_type="tool_decision",
                decision=Decision.DENY,
                reason_codes=(reason,),
                actor_id=actor.user_id,
                request_id=request_id,
                order_id=order_id,
                tool_name=tool_name,
            )
        )
        return ServiceResult(
            decision=Decision.DENY,
            reason=reason,
            message="Запрос отклонён серверной политикой безопасности.",
            request_id=request_id,
        )

    def _assign_company(self, telegram_user_id: int) -> CompanySlug:
        digest = hmac.new(
            self._company_assignment_secret.encode(),
            str(telegram_user_id).encode(),
            hashlib.sha256,
        ).digest()
        return CompanySlug.ALPHA if digest[0] % 2 == 0 else CompanySlug.BETA
