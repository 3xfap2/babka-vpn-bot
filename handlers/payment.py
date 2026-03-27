import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from config import WEEK_DAYS, MONTH_DAYS, ADMIN_IDS
from database import assign_key, save_payment, get_user, manual_set_key, add_ref_days

router = Router()
logger = logging.getLogger(__name__)

NOTIFY_ADMIN_IDS = [6849781575, 7565071317]


async def _notify_admin(bot: Bot, text: str):
    for admin_id in NOTIFY_ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Admin notify failed for {admin_id}: {e}")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or "—"
    first_name = message.from_user.first_name or "—"
    sp = message.successful_payment
    payload = sp.invoice_payload
    stars = sp.total_amount

    parts = payload.split("_", 1)
    sub_type = parts[0]  # "week", "month", "test"

    # ── TEST ──────────────────────────────────────────────
    if sub_type == "test":
        TEST_KEY = "тест-ключ-vpn-12345"
        await manual_set_key(user_id, TEST_KEY, "test", 1)
        await save_payment(user_id, payload, stars, sp.telegram_payment_charge_id)

        from handlers.start import build_webapp_url
        user_data = await get_user(user_id)
        url = await build_webapp_url(
            user_data, bot, user_id,
            first_name=first_name, username=username,
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await message.answer(
            "✅ <b>Тест прошёл успешно!</b>\n\n"
            "🔑 Тестовый VPN ключ:\n<code>тест-ключ-vpn-12345</code>\n\n"
            "Откройте приложение — в профиле обновится статус подписки.",
            parse_mode="HTML", reply_markup=kb
        )
        await _notify_admin(bot,
            f"🧪 <b>Тест оплата</b>\n"
            f"👤 {first_name} (@{username}) <code>{user_id}</code>\n"
            f"📦 Тариф: Тест | ⭐ {stars} звёзд"
        )
        return

    # ── WEEK / MONTH ──────────────────────────────────────
    if sub_type == "week":
        days, label, rub_price = WEEK_DAYS, "Неделя (7 дней)", "35₽"
    elif sub_type == "month":
        days, label, rub_price = MONTH_DAYS, "Месяц (30 дней)", "145₽"
    else:
        return

    key = await assign_key(user_id, sub_type, days)
    await save_payment(user_id, payload, stars, sp.telegram_payment_charge_id)

    from handlers.start import build_webapp_url

    if key:
        user_data = await get_user(user_id)
        url = await build_webapp_url(
            user_data, bot, user_id,
            first_name=first_name, username=username,
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
        ])
        await message.answer(
            f"✅ <b>Оплата прошла!</b> Подписка: <b>{label}</b>\n\n"
            f"🔑 Ваш VPN ключ:\n<code>{key}</code>\n\n"
            "Нажмите на ключ чтобы скопировать, затем вставьте в <b>Happ</b>",
            parse_mode="HTML", reply_markup=kb
        )
        # Уведомление админу
        await _notify_admin(bot,
            f"💰 <b>Новая покупка!</b>\n"
            f"👤 {first_name} (@{username}) <code>{user_id}</code>\n"
            f"📦 Тариф: {label}\n"
            f"⭐ {stars} звёзд (~{rub_price})\n"
            f"🔑 Ключ выдан: <code>{key}</code>"
        )
        # Реферальная награда — если купил месяц
        if sub_type == "month":
            user_data_full = await get_user(user_id)
            referrer_id = user_data_full.get("referrer_id") if user_data_full else None
            if referrer_id:
                await add_ref_days(referrer_id, 7)
                try:
                    await bot.send_message(
                        referrer_id,
                        "🎁 <b>Реферальная награда!</b>\n\n"
                        f"Ваш друг купил подписку на месяц.\n"
                        "Вам начислено <b>+7 дней</b> к подписке!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await _notify_admin(bot,
                    f"🔗 Реферальная награда выдана\n"
                    f"Реферер: <code>{referrer_id}</code> +7 дней\n"
                    f"От: {first_name} <code>{user_id}</code>"
                )
    else:
        # Ключей нет
        await message.answer(
            "✅ Оплата прошла, но свободных ключей временно нет.\n"
            "Администратор свяжется с вами в ближайшее время."
        )
        await _notify_admin(bot,
            f"⚠️ <b>КЛЮЧЕЙ НЕТ!</b>\n"
            f"👤 {first_name} (@{username}) <code>{user_id}</code>\n"
            f"📦 Тариф: {label} | ⭐ {stars} звёзд\n"
            f"👉 Используй: /givekey {user_id} &lt;ключ&gt; {sub_type}"
        )
