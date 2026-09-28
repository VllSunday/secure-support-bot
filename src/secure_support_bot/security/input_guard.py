from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass

from secure_support_bot.domain.models import Decision


@dataclass(frozen=True, slots=True)
class InputAssessment:
    decision: Decision
    reason: str
    normalized_text: str


_INJECTION_RE = re.compile(
    r"(?:ignore|игнорируй|обойди|bypass|override|developer mode|режим разработчика|"
    r"reveal.*prompt|раскрой.*промпт|export_all_customers|вызови.*инструмент)",
    re.IGNORECASE,
)
_EDUCATIONAL_RE = re.compile(
    r"(?:для обучения|учебн|объясни|разбор|анализ|что означает|почему это)",
    re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"(?:вызови|выполни|покажи.*данн|выгрузи|экспорт|дай.*ключ|раскрой.*секрет)",
    re.IGNORECASE,
)


def assess_input(text: str, *, max_length: int = 4_000) -> InputAssessment:
    normalized = unicodedata.normalize("NFKC", text).replace("\x00", "")
    if len(normalized) > max_length:
        return InputAssessment(Decision.DENY, "input_too_long", normalized[:max_length])

    if any(unicodedata.category(char) == "Cf" for char in normalized):
        return InputAssessment(Decision.REVIEW, "invisible_unicode_detected", normalized)

    decoded = _try_decode_base64(normalized)
    injection_match = _INJECTION_RE.search(normalized) or (
        decoded is not None and _INJECTION_RE.search(decoded)
    )
    if injection_match and _EDUCATIONAL_RE.search(normalized):
        return InputAssessment(Decision.ALLOW, "educational_analysis", normalized)
    if injection_match and _ACTION_RE.search(normalized):
        return InputAssessment(Decision.DENY, "prompt_injection_action_request", normalized)
    if injection_match:
        return InputAssessment(Decision.REVIEW, "prompt_injection_signal", normalized)
    return InputAssessment(Decision.ALLOW, "input_allowed", normalized)


def _try_decode_base64(value: str) -> str | None:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 16 or len(compact) % 4 != 0 or not re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        return None
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
