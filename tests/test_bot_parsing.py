from __future__ import annotations

from secure_support_bot.bot import parse_message


def test_order_id_digits_are_not_treated_as_refund_amount() -> None:
    parsed = parse_message("верни по заказу ORD-ALPHA-B610FE09067D")

    assert parsed.kind == "refund"
    assert parsed.order_id == "ORD-ALPHA-B610FE09067D"
    assert parsed.amount is None


def test_refund_parser_extracts_amount_before_order_id() -> None:
    parsed = parse_message("верни 1000 по заказу ORD-ALPHA-B610FE09067D")

    assert parsed.kind == "refund"
    assert parsed.amount == 1_000
    assert parsed.order_id == "ORD-ALPHA-B610FE09067D"
