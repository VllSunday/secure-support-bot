from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from secure_support_bot.application.agents import OpenAIAnswerAgent
from secure_support_bot.application.service import SupportService
from secure_support_bot.bot import build_router, run_polling
from secure_support_bot.config import Settings, get_settings
from secure_support_bot.infrastructure.memory import InMemoryStore
from secure_support_bot.infrastructure.sql import SqlStore
from secure_support_bot.security.risk import AllowRiskChecker


def build_service(settings: Settings) -> tuple[SupportService, object]:
    if settings.app_env == "test":
        store: object = InMemoryStore()
    else:
        store = SqlStore(settings.database_url)
    answer_agent = None
    if settings.bot_mode == "llm":
        if not settings.openai_api_key or not settings.openai_model:
            raise RuntimeError("BOT_MODE=llm requires OPENAI_API_KEY and OPENAI_MODEL")
        answer_agent = OpenAIAnswerAgent(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    service = SupportService(
        store=store,  # type: ignore[arg-type]
        risk_checker=AllowRiskChecker(),
        company_assignment_secret=settings.company_assignment_secret,
        confirmation_secret=settings.confirmation_hmac_secret,
        risk_timeout_seconds=settings.risk_timeout_seconds,
        answer_agent=answer_agent,
    )
    return service, store


async def async_main(settings: Settings) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")

    service, store = build_service(settings)
    if isinstance(store, SqlStore):
        await store.create_schema()
    bot = Bot(token=settings.telegram_bot_token)
    router = build_router(service, mode=settings.bot_mode)
    try:
        await run_polling(bot, router)
    finally:
        await bot.session.close()
        if isinstance(store, SqlStore):
            await store.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(async_main(get_settings()))


if __name__ == "__main__":
    main()
