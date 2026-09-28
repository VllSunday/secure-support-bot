from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from secure_support_bot.domain.models import CompanySlug


def refund_fingerprint(
    *,
    secret: str,
    actor_id: UUID,
    company: CompanySlug,
    order_id: str,
    amount: int,
    currency: str,
    request_id: UUID,
    order_version: int,
) -> str:
    message = "\x1f".join(
        (
            str(actor_id),
            company.value,
            order_id,
            str(amount),
            currency,
            str(request_id),
            str(order_version),
        )
    ).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def fingerprints_match(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected, actual)
