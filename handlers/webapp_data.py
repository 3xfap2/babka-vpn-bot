import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config import TRIAL_CHANNEL, TRIAL_DAYS, ADMIN_IDS, BOT_USERNAME
from database import get_user, assign_key, mark_trial_used

router = Router()
logger = logging.getLogger(__name__)


async def _check_and_grant_trial(user_id: int, first_name: str, username: str,
                                  bot: Bot, reply_func):
    """Shared logic: check channel membership and grant trial if subscribed."""
    user = await get_user(user_id)
    if user and user.get("trial_used"):
        await reply_func("❌ Вы уже использовали пробную подписку")
        return

    try:
        member = await bot.get_chat_member(TRIAL_CHANNEL, user_id)
        is_member = member.status not in ("left", "kicked", "banned")
        logger.info(f"Trial check user {user_id}: status={member.status}, is_member={is_member}")
    except Exception as e:
        logger.error(f"get_chat_member failed for user {user_id}: {e}")
        is_member = False

    if not is_member:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 Подписаться на канал",
                url=f"https://t.me/{TRIAL_CHANNEL.lstrip('@')}"
            )],
            [InlineKeyboardButton(
                text="✅ Проверить подписку",
                callback_data="check_trial"          # ← callback, not URL
            )]
        ])
        await reply_func(
            f"📢 Для пробной подписки подпишитесь на канал:\n"
            f"<b>{TRIAL_CHANNEL}</b>\n\n"
            "После подписки нажмите «Проверить подписку»",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    key = await assign_key(user_id, "trial", TRIAL_DAYS)
    await mark_trial_used(user_id)

    if key:
        from handlers.start import build_webapp_url
        user_data = await get_user(user_id)
        app_url = await build_webapp_url(
            user_data, bot, user_id,
            first_name=first_name,
            username=username,
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=app_url))],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await reply_func(
            f"🎉 <b>Пробная подписка активирована на {TRIAL_DAYS} дня!</b>\n\n"
            f"🔑 Ваш VPN ключ:\n<code>{key}</code>\n\n"
            "Нажмите на ключ чтобы скопировать, затем вставьте в приложение <b>Happ</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await reply_func("😔 Пробных ключей временно нет. Администратор свяжется с вами!")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Нет пробных ключей!\n"
                    f"Пользователь: <code>{user_id}</code> @{username}",
                    parse_mode="HTML"
                )
            except Exception:
                pass


async def process_trial(message: Message, bot: Bot):
    """Called from /start trial deep link."""
    await _check_and_grant_trial(
        user_id=message.from_user.id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or "",
        bot=bot,
        reply_func=message.answer,
    )


@router.callback_query(F.data == "check_trial")
async def check_trial_callback(callback: CallbackQuery, bot: Bot):
    """Called when user taps 'Проверить подписку' inline button."""
    await callback.answer("Проверяем подписку...")

    user = callback.from_user
    await _check_and_grant_trial(
        user_id=user.id,
        first_name=user.first_name or "",
        username=user.username or "",
        bot=bot,
        reply_func=callback.message.answer,
    )


@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, bot: Bot):
    """Called when user taps 'Я подписался — проверить' from the subscription gate."""
    from config import TRIAL_CHANNEL
    try:
        member = await bot.get_chat_member(TRIAL_CHANNEL, callback.from_user.id)
        is_subscribed = member.status not in ("left", "kicked", "banned")
    except Exception:
        is_subscribed = False

    if is_subscribed:
        await callback.answer("✅ Подписка подтверждена!")
        # Trigger the start flow
        from handlers.start import build_webapp_url
        from database import upsert_user, get_user
        user = callback.from_user
        await upsert_user(user.id, user.username or "")
        user_data = await get_user(user.id)
        url = await build_webapp_url(
            user_data, bot, user.id,
            first_name=user.first_name or "",
            username=user.username or "",
        )
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(text="👥 Пригласить друга (+7 дней)", url=f"https://t.me/share/url?url={ref_link}&text=Крутой%20VPN%20бот!")],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await callback.message.answer(
            "👋 Добро пожаловать в <b>БАБКА VPN</b>!\n\n"
            "Нажми кнопку ниже чтобы открыть приложение 👇",
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        await callback.answer("❌ Вы ещё не подписаны на канал", show_alert=True)
