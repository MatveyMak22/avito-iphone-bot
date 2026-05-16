"""Точка входа — запуск Telegram-бота и мониторинга."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from config import BOT_TOKEN
from handlers import router
from monitor import monitoring_loop
from parser import close_browser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN не задан! Укажите его в .env файле или "
            "переменной окружения BOT_TOKEN."
        )
        sys.exit(1)

    # Инициализация БД
    db.init_db()
    logger.info("База данных инициализирована.")

    # Создание бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Запуск мониторинга в фоне
    asyncio.create_task(monitoring_loop(bot))
    logger.info("Бот запущен!")

    try:
        # Запуск polling
        await dp.start_polling(
            bot, allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        await close_browser()
        logger.info("Браузер закрыт.")


if __name__ == "__main__":
    asyncio.run(main())
