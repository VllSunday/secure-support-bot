from __future__ import annotations

import re

from secure_support_bot.domain.models import Decision

_LEAK_RE = re.compile(
    r"(?:system prompt|developer message|api[_ -]?key|bot token|secret[_ -]?key)",
    re.IGNORECASE,
)


def validate_output(text: str, *, max_length: int = 4_000) -> tuple[Decision, str, str]:
    if len(text) > max_length:
        return Decision.DENY, "output_too_long", "Ответ ограничен по длине."
    if _LEAK_RE.search(text):
        return Decision.DENY, "output_sensitive_pattern", "Не удалось безопасно сформировать ответ."
    return Decision.ALLOW, "output_allowed", text
