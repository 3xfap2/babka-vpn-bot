import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, InlineKeyboardMarkup, InlineKeyboardButton
from config import TRIAL_CHANNEL, ADMIN_IDS

logger = logging.getLogger(__name__)

BYPASS_CALLBACKS = {"check_subscription"}


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        bot = data.get("bot")

        # event here is Update object
        if not isinstance(event, Update):
            return await handler(event, data)

        if event.message:
            user = event.message.from_user

            async def send_gate(text, **kwargs):
                await event.message.answer(text, **kwargs)

        elif event.callback_query:
            # Always let bypass callbacks through (subscription check itself)
            if event.callback_query.data in BYPASS_CALLBACKS:
                return await handler(event, data)

            user = event.callback_query.from_user

            async def send_gate(text, **kwargs):
                await event.callback_query.answer()
                await event.callback_query.message.answer(text, **kwargs)

        else:
            return await handler(event, data)

        if not user:
            return await handler(event, data)

        # Admins always bypass
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        # Check subscription
        try:
            member = await bot.get_chat_member(TRIAL_CHANNEL, user.id)
            is_subscribed = member.status not in ("left", "kicked", "banned")
            logger.info(f"Sub check {user.id} (@{user.username}): {member.status}")
        except Exception as e:
            logger.warning(f"Sub check failed for {user.id}: {e} — letting through")
            is_subscribed = True  # Don't block if API error

        if not is_subscribed:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=f"https://t.me/{TRIAL_CHANNEL.lstrip('@')}"
                )],
                [InlineKeyboardButton(
                    text="✅ Я подписался — проверить",
                    callback_data="check_subscription"
                )],
            ])
            await send_gate(
                f"🔒 <b>Доступ ограничен</b>\n\n"
                f"Для использования бота подпишитесь на канал {TRIAL_CHANNEL}.\n\n"
                "После подписки нажмите кнопку ниже 👇",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return  # Block handler

        return await handler(event, data)
