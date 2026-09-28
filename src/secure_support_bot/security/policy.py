from __future__ import annotations

from datetime import UTC, datetime

from secure_support_bot.domain.models import (
    ActorContext,
    CheckResult,
    Decision,
    Order,
    OrderStatus,
    PendingRefund,
    PendingRefundStatus,
)
from secure_support_bot.security.fingerprint import fingerprints_match, refund_fingerprint


class RefundPolicy:
    def __init__(self, fingerprint_secret: str) -> None:
        self._fingerprint_secret = fingerprint_secret

    def evaluate(
        self,
        *,
        actor: ActorContext,
        order: Order | None,
        pending: PendingRefund,
        now: datetime | None = None,
    ) -> tuple[CheckResult, ...]:
        current_time = now or datetime.now(UTC)
        checks: list[CheckResult] = []

        checks.append(
            self._check(
                "pending_status",
                pending.status is PendingRefundStatus.AWAITING_CONFIRMATION,
                "pending_action_ready",
                "pending_action_not_ready",
            )
        )
        checks.append(
            self._check(
                "confirmation_expiry",
                current_time < pending.expires_at,
                "confirmation_valid",
                "confirmation_expired",
            )
        )
        checks.append(
            self._check(
                "actor",
                pending.actor_id == actor.user_id,
                "actor_match",
                "actor_mismatch",
            )
        )
        checks.append(
            self._check(
                "company",
                pending.company == actor.company
                and order is not None
                and order.company == actor.company,
                "company_match",
                "company_mismatch",
            )
        )
        checks.append(
            self._check(
                "ownership",
                order is not None and order.owner_id == actor.user_id,
                "owner_match",
                "owner_mismatch",
            )
        )
        checks.append(
            self._check(
                "order_status",
                order is not None
                and order.status in {OrderStatus.PAID, OrderStatus.PARTIALLY_REFUNDED},
                "order_refundable",
                "order_not_refundable",
            )
        )
        checks.append(
            self._check(
                "amount",
                isinstance(pending.amount, int)
                and not isinstance(pending.amount, bool)
                and pending.amount > 0,
                "amount_positive",
                "amount_invalid",
            )
        )
        checks.append(
            self._check(
                "balance",
                order is not None and 0 < pending.amount <= order.remaining_amount,
                "balance_available",
                "amount_exceeds_balance",
            )
        )
        checks.append(
            self._check(
                "order_version",
                order is not None and pending.order_version == order.version,
                "order_version_match",
                "order_changed_after_confirmation_request",
            )
        )

        expected = refund_fingerprint(
            secret=self._fingerprint_secret,
            actor_id=pending.actor_id,
            company=pending.company,
            order_id=pending.order_id,
            amount=pending.amount,
            currency=pending.currency,
            request_id=pending.request_id,
            order_version=pending.order_version,
        )
        checks.append(
            self._check(
                "fingerprint",
                fingerprints_match(expected, pending.fingerprint),
                "confirmation_fingerprint_match",
                "confirmation_fingerprint_mismatch",
            )
        )
        return tuple(checks)

    @staticmethod
    def _check(name: str, condition: bool, allow_reason: str, deny_reason: str) -> CheckResult:
        if condition:
            return CheckResult(name, Decision.ALLOW, allow_reason)
        return CheckResult(name, Decision.DENY, deny_reason)


def aggregate_policy(checks: tuple[CheckResult, ...]) -> Decision:
    if any(check.decision is Decision.DENY for check in checks):
        return Decision.DENY
    if any(check.decision is Decision.REVIEW for check in checks):
        return Decision.REVIEW
    return Decision.ALLOW
