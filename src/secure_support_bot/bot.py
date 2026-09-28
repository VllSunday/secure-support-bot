from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from secure_support_bot.application.service import SupportService
from secure_support_bot.domain.models import ActorContext, Decision

MAX_MESSAGE_LENGTH: Final = 4_000
ORDER_PATTERN: Final = re.compile(r"\bORD-[A-Z0-9-]{8,64}\b")
AMOUNT_PATTERN: Final = re.compile(r"(?<!\d)(\d{1,7})(?!\d)")


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    kind: str
    order_id: str | None = None
    amount: int | None = None


def parse_message(text: str) -> ParsedMessage:
    normalized = " ".join(text.strip().split())
    lowered = normalized.casefold()
    order_match = ORDER_PATTERN.search(normalized.upper())
    order_id = order_match.group(0) if order_match else None

    amount: int | None = None
    amount_source = normalized[: order_match.start()] if order_match else normalized
    amount_match = AMOUNT_PATTERN.search(amount_source)
    if amount_match:
        amount = int(amount_match.group(1))

    if "возврат" in lowered or "верни" in lowered or "вернуть" in lowered:
        return ParsedMessage("refund", order_id=order_id, amount=amount)
    if "заказ" in lowered or "order" in lowered:
        return ParsedMessage("order", order_id=order_id)
    return ParsedMessage("documents")


def build_router(service: SupportService, *, mode: str) -> Router:
    router = Router(name="support-bot")

    def is_private(message: Message) -> bool:
        return message.chat.type == "private"

    async def actor_for_message(message: Message) -> ActorContext | None:
        if message.from_user is None:
            return None
        return await service.start(message.from_user.id)

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if not is_private(message):
            await message.answer("Учебные заказы и возвраты доступны только в личном чате с ботом.")
            return
        actor = await actor_for_message(message)
        if actor is None:
            return
        orders = await service.list_orders(actor)
        order_lines = "\n".join(result.message for result in orders)
        await message.answer(
            "Профиль создан.\n"
            f"Режим ответов: {mode}.\n"
            f"Компания: {actor.company.value}.\n"
            "Команды: /order — мой заказ, /help — справка.\n\n"
            f"Ваш учебный заказ:\n{order_lines}"
        )

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        await message.answer(
            "Я отвечаю по доступным документам, показываю только ваши заказы "
            "и оформляю учебный возврат после точного подтверждения.\n\n"
            "Пример: `покажи заказ ORD-ALPHA-...` или `верни 1000 по заказу ORD-...`."
        )

    @router.message(Command("order"))
    async def handle_order_command(message: Message) -> None:
        if not is_private(message):
            await message.answer("Эта команда доступна только в личном чате.")
            return
        actor = await actor_for_message(message)
        if actor is None:
            return
        results = await service.list_orders(actor)
        await message.answer("\n".join(result.message for result in results))

    @router.callback_query(F.data.startswith("refund:"))
    async def handle_refund_confirmation(callback: CallbackQuery) -> None:
        if (
            callback.from_user is None
            or callback.message is None
            or callback.message.chat.type != "private"
            or not isinstance(callback.data, str)
        ):
            await callback.answer("Подтверждение недоступно.", show_alert=True)
            return
        token = callback.data.removeprefix("refund:")
        actor = await service.start(callback.from_user.id)
        result = await service.confirm_refund(actor, token)
        await callback.answer(
            "Готово" if result.decision is Decision.ALLOW else "Операция остановлена",
            show_alert=True,
        )
        await callback.message.answer(result.message)

    @router.message()
    async def handle_text(message: Message) -> None:
        if not is_private(message):
            await message.answer("Пожалуйста, продолжите в личном чате с ботом.")
            return
        if not message.text:
            await message.answer("Поддерживаются только текстовые сообщения.")
            return
        if len(message.text) > MAX_MESSAGE_LENGTH:
            await message.answer("Сообщение слишком длинное. Уменьшите его до 4000 символов.")
            return

        actor = await actor_for_message(message)
        if actor is None:
            return
        parsed = parse_message(message.text)
        if parsed.kind == "order":
            if parsed.order_id is None:
                results = await service.list_orders(actor)
                await message.answer("\n".join(result.message for result in results))
                return
            result = await service.get_order(actor, parsed.order_id)
            await message.answer(result.message)
            return

        if parsed.kind == "refund":
            if parsed.order_id is None or parsed.amount is None:
                await message.answer(
                    "Для возврата укажите конкретный заказ и сумму, например: "
                    "«верни 1000 по заказу ORD-ALPHA-...»."
                )
                return
            result = await service.propose_refund(
                actor=actor,
                order_id=parsed.order_id,
                amount=parsed.amount,
                original_request=message.text,
            )
            if result.confirmation_token:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Подтвердить возврат",
                                callback_data=f"refund:{result.confirmation_token}",
                            )
                        ]
                    ]
                )
                await message.answer(result.message, reply_markup=keyboard)
            else:
                await message.answer(result.message)
            return

        result = await service.answer_from_documents(actor, message.text)
        await message.answer(result.message)

    return router


async def run_polling(bot: Bot, router: Router) -> None:
    from aiogram import Dispatcher

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
