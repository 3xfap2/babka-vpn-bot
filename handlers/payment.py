from aiogram import Router, F, Bot
from aiogram.types import (
    Message, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from config import WEEK_DAYS, MONTH_DAYS
from database import assign_key, save_payment, get_user, manual_set_key

router = Router()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    user_id = message.from_user.id
    sp = message.successful_payment
    payload = sp.invoice_payload  # format: "week_123456" or "month_123456"

    parts = payload.split("_", 1)
    sub_type = parts[0]  # "week", "month" or "test"

    if sub_type == "test":
        TEST_KEY = "тест-ключ-vpn-12345"
        await manual_set_key(user_id, TEST_KEY, "test", 1)  # 1 day test subscription
        await save_payment(user_id, payload, sp.total_amount, sp.telegram_payment_charge_id)
        from handlers.start import build_webapp_url
        user_data = await get_user(user_id)
        url = await build_webapp_url(
            user_data, bot, user_id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username or "",
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await message.answer(
            "✅ <b>Тест прошёл успешно!</b>\n\n"
            "🔑 Тестовый VPN ключ:\n<code>тест-ключ-vpn-12345</code>\n\n"
            "Откройте приложение — в профиле обновится статус подписки.",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    if sub_type == "week":
        key = await assign_key(user_id, "week", WEEK_DAYS)
        label = "7 дней"
    elif sub_type == "month":
        key = await assign_key(user_id, "month", MONTH_DAYS)
        label = "30 дней"
    else:
        return

    await save_payment(user_id, payload, sp.total_amount, sp.telegram_payment_charge_id)

    if key:
        from handlers.start import build_webapp_url
        user_data = await get_user(user_id)
        url = await build_webapp_url(
            user_data, bot, user_id,
            first_name=message.from_user.first_name or "",
            username=message.from_user.username or "",
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await message.answer(
            f"✅ <b>Оплата прошла!</b> Подписка активна на {label}\n\n"
            f"🔑 Ваш VPN ключ:\n<code>{key}</code>\n\n"
            "Нажмите на ключ чтобы скопировать, затем вставьте в <b>Happ</b>",
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        await message.answer(
            "✅ Оплата прошла, но свободных ключей нет.\n"
            "Администратор свяжется с вами в ближайшее время."
        )
        from config import ADMIN_IDS
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Нет ключей!\n"
                    f"Пользователь: <code>{user_id}</code> @{message.from_user.username}\n"
                    f"Тариф: {sub_type}\n"
                    f"Используй: /givekey {user_id} <ключ> {sub_type}"
                )
            except Exception:
                pass
