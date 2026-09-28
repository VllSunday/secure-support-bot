from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError


class ToolValidationError(ValueError):
    pass


class GetOrderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: StrictStr = Field(min_length=8, max_length=64, pattern=r"^[A-Z0-9-]+$")


class RefundArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: UUID
    order_id: StrictStr = Field(min_length=8, max_length=64, pattern=r"^[A-Z0-9-]+$")
    amount: StrictInt = Field(gt=0, le=1_000_000)
    currency: Literal["DEMO"]


ParsedArguments = GetOrderArguments | RefundArguments


def validate_tool_call(name: str, arguments: dict[str, Any]) -> ParsedArguments:
    schemas: dict[str, type[GetOrderArguments] | type[RefundArguments]] = {
        "get_order": GetOrderArguments,
        "refund": RefundArguments,
    }
    schema = schemas.get(name)
    if schema is None:
        raise ToolValidationError("tool_not_allowed")
    try:
        return schema.model_validate(arguments)
    except ValidationError as exc:
        raise ToolValidationError("invalid_tool_arguments") from exc


def allowed_tool_names() -> frozenset[str]:
    return frozenset({"get_order", "refund"})
