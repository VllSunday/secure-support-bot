from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from secure_support_bot.security.tools import (
    RefundArguments,
    ToolValidationError,
    validate_tool_call,
)


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ToolValidationError, match="tool_not_allowed"):
        validate_tool_call("export_all_customers", {})


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "1000", 1_000_001])
def test_refund_amount_is_strict_and_bounded(amount: object) -> None:
    with pytest.raises(ToolValidationError, match="invalid_tool_arguments"):
        validate_tool_call(
            "refund",
            {
                "request_id": uuid4(),
                "order_id": "ORD-ALPHA-12345678",
                "amount": amount,
                "currency": "DEMO",
            },
        )


def test_extra_tool_arguments_are_rejected() -> None:
    with pytest.raises(ToolValidationError, match="invalid_tool_arguments"):
        validate_tool_call(
            "get_order",
            {"order_id": "ORD-ALPHA-12345678", "role": "admin"},
        )


def test_refund_model_does_not_coerce_values() -> None:
    with pytest.raises(ValidationError):
        RefundArguments.model_validate(
            {
                "request_id": str(uuid4()),
                "order_id": "ORD-ALPHA-12345678",
                "amount": 1000,
                "currency": "DEMO",
            }
        )
