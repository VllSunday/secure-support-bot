from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class CompanySlug(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"


class OrderStatus(StrEnum):
    PAID = "paid"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PendingRefundStatus(StrEnum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REVIEW = "review"
    DENIED = "denied"
    EXECUTED = "executed"
    EXPIRED = "expired"


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: UUID
    telegram_user_id: int
    company: CompanySlug
    role: str = "customer"


@dataclass(slots=True)
class UserProfile:
    id: UUID
    telegram_user_id: int
    company: CompanySlug
    role: str = "customer"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def actor(self) -> ActorContext:
        return ActorContext(
            user_id=self.id,
            telegram_user_id=self.telegram_user_id,
            company=self.company,
            role=self.role,
        )


@dataclass(slots=True)
class Order:
    id: str
    owner_id: UUID
    company: CompanySlug
    paid_amount: int
    refunded_amount: int = 0
    currency: str = "DEMO"
    status: OrderStatus = OrderStatus.PAID
    version: int = 1

    @property
    def remaining_amount(self) -> int:
        return self.paid_amount - self.refunded_amount


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    company: CompanySlug
    title: str
    content: str
    instruction_like: bool = False


@dataclass(slots=True)
class PendingRefund:
    request_id: UUID
    confirmation_token: str
    actor_id: UUID
    company: CompanySlug
    order_id: str
    amount: int
    currency: str
    order_version: int
    fingerprint: str
    original_request: str
    expires_at: datetime
    status: PendingRefundStatus = PendingRefundStatus.AWAITING_CONFIRMATION
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RefundOperation:
    request_id: UUID
    actor_id: UUID
    company: CompanySlug
    order_id: str
    amount: int
    currency: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    decision: Decision
    reason: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    decision: Decision
    reason_codes: tuple[str, ...]
    actor_id: UUID | None = None
    request_id: UUID | None = None
    order_id: str | None = None
    tool_name: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
