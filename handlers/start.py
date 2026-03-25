import json
import base64
import logging
from datetime import datetime
from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, LabeledPrice
)
from config import WEBAPP_URL, WEEK_PRICE_STARS, MONTH_PRICE_STARS, WEEK_DAYS, MONTH_DAYS
from database import upsert_user, get_user

router = Router()
logger = logging.getLogger(__name__)


async def build_webapp_url(user: dict | None, bot: Bot, user_id: int, first_name: str = "", username: str = "") -> str:
    sub_active = False
    sub_type = None
    sub_end = None
    vpn_key = None
    trial_used = False

    if user:
        trial_used = bool(user.get("trial_used"))
        if user.get("sub_end"):
            try:
                end_dt = datetime.fromisoformat(user["sub_end"])
                if end_dt > datetime.now():
                    sub_active = True
                    sub_type = user["sub_type"]
                    sub_end = end_dt.strftime("%d.%m.%Y")
                    vpn_key = user.get("vpn_key")
            except Exception:
                pass

    # Pre-generate invoice links so Mini App can use tg.openInvoice()
    try:
        week_link = await bot.create_invoice_link(
            title="Подписка на неделю",
            description="VPN доступ на 7 дней через приложение Happ",
            payload=f"week_{user_id}",
            currency="XTR",
            prices=[LabeledPrice(label="Неделя", amount=WEEK_PRICE_STARS)]
        )
        logger.info(f"week_link created: {week_link}")
    except Exception as e:
        logger.error(f"create_invoice_link week FAILED: {e}")
        week_link = None

    try:
        month_link = await bot.create_invoice_link(
            title="Подписка на месяц",
            description="VPN доступ на 30 дней через приложение Happ",
            payload=f"month_{user_id}",
            currency="XTR",
            prices=[LabeledPrice(label="Месяц", amount=MONTH_PRICE_STARS)]
        )
        logger.info(f"month_link created: {month_link}")
    except Exception as e:
        logger.error(f"create_invoice_link month FAILED: {e}")
        month_link = None

    try:
        test_link = await bot.create_invoice_link(
            title="Тестовая оплата",
            description="Тест системы оплаты — 1 звезда",
            payload=f"test_{user_id}",
            currency="XTR",
            prices=[LabeledPrice(label="Тест", amount=1)]
        )
        logger.info(f"test_link created: {test_link}")
    except Exception as e:
        logger.error(f"create_invoice_link test FAILED: {e}")
        test_link = None

    logger.info(f"Invoice links result — week: {'OK' if week_link else 'NONE'}, month: {'OK' if month_link else 'NONE'}, test: {'OK' if test_link else 'NONE'}")

    data = {
        "s": 1 if sub_active else 0,
        "t": sub_type,
        "e": sub_end,
        "k": vpn_key,
        "tr": 1 if trial_used else 0,
        "wl": week_link,
        "ml": month_link,
        "tl": test_link,
        "id": user_id,
        "n": first_name,
        "u": username,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(data, ensure_ascii=False).encode()
    ).decode()
    separator = "&" if "?" in WEBAPP_URL else "?"
    full_url = f"{WEBAPP_URL}{separator}d={encoded}"
    logger.info(f"WebApp URL length: {len(full_url)} chars")
    return full_url


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    await upsert_user(user_id, message.from_user.username or "")

    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

    if args in ("buy_week", "buy_month"):
        sub = "week" if args == "buy_week" else "month"
        days = WEEK_DAYS if sub == "week" else MONTH_DAYS
        price = WEEK_PRICE_STARS if sub == "week" else MONTH_PRICE_STARS
        label = "неделю" if sub == "week" else "месяц"
        await bot.send_invoice(
            chat_id=user_id,
            title=f"Подписка на {label}",
            description=f"VPN доступ на {days} дней через приложение Happ",
            payload=f"{sub}_{user_id}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Подписка на {label}", amount=price)]
        )
        return

    if args == "trial":
        from handlers.webapp_data import process_trial
        await process_trial(message, bot)
        return

    user = await get_user(user_id)
    url = await build_webapp_url(
        user, bot, user_id,
        first_name=message.from_user.first_name or "",
        username=message.from_user.username or "",
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Открыть БАБКА VPN", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="💬 Связаться с поддержкой", url="https://t.me/Pardonsky")],
    ])

    await message.answer(
        "👋 Добро пожаловать в <b>БАБКА VPN</b>!\n\n"
        "Нажми кнопку ниже чтобы открыть приложение 👇",
        parse_mode="HTML",
        reply_markup=kb
    )
