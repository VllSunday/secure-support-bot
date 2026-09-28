from __future__ import annotations

import pytest

from secure_support_bot.config import Settings
from secure_support_bot.main import build_service


def test_llm_mode_requires_explicit_provider_credentials() -> None:
    settings = Settings(app_env="test", bot_mode="llm")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY and OPENAI_MODEL"):
        build_service(settings)
