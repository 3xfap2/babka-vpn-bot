import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from config import BOT_TOKEN
from database import init_db, get_expired_unsent_users, mark_expiry_notified
from handlers import start, payment, admin, webapp_data
from middleware import SubscriptionMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def expiry_checker(bot: Bot):
    """Runs every hour, sends expiry notification to users whose sub just ended."""
    while True:
        try:
            expired = await get_expired_unsent_users()
            for user in expired:
                try:
                    await bot.send_message(
                        user["user_id"],
                        "⚠️ <b>Подписка истекла</b>\n\n"
                        "Ваша подписка закончилась. Для продолжения использования "
                        "сервиса, пожалуйста, продлите подписку.",
                        parse_mode="HTML"
                    )
                    await mark_expiry_notified(user["user_id"])
                    logger.info(f"Expiry notice sent to {user['user_id']}")
                except Exception as e:
                    logger.warning(f"Failed to notify {user['user_id']}: {e}")
        except Exception as e:
            logger.error(f"Expiry checker error: {e}")
        await asyncio.sleep(3600)  # check every hour


async def main():
    await init_db()
    logger.info("Database initialized")

    proxy = os.getenv("PROXY")
    session = AiohttpSession(proxy=proxy) if proxy else AiohttpSession()
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    dp.update.outer_middleware(SubscriptionMiddleware())

    dp.include_router(admin.router)
    dp.include_router(payment.router)
    dp.include_router(webapp_data.router)
    dp.include_router(start.router)

    try:
        logger.info("Bot started!")
        asyncio.create_task(expiry_checker(bot))
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
