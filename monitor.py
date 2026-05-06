"""Фоновый мониторинг новых объявлений."""

import asyncio
import logging

from aiogram import Bot

import database as db
from config import ALL_REGIONS_KEY, ALL_REGIONS_NAME, CHECK_INTERVAL, REGIONS
from parser import Ad, fetch_ads

logger = logging.getLogger(__name__)


def _format_ad(ad: Ad) -> str:
    """Форматировать объявление для отправки в Telegram."""
    lines = [
        f"📦 <b>{ad.title}</b>",
        f"💰 {ad.price}",
    ]
    if ad.location:
        lines.append(f"📍 {ad.location}")
    if ad.date:
        lines.append(f"🕐 {ad.date}")
    lines.append(f"\n🔗 <a href=\"{ad.url}\">Открыть на Авито</a>")
    return "\n".join(lines)


async def check_subscription(bot: Bot, sub: dict) -> int:
    """
    Проверить одну подписку и отправить новые объявления.
    Возвращает количество отправленных объявлений.
    """
    ads = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: fetch_ads(
            model=sub["model"],
            region=sub["region"],
            price_min=sub["price_min"],
            price_max=sub["price_max"],
        ),
    )

    sent_count = 0
    for ad in ads:
        if not ad.url:
            continue
        if db.is_ad_seen(sub["id"], ad.url):
            continue

        db.mark_ad_seen(sub["id"], ad.url)
        try:
            region_name = REGIONS.get(sub["region"], sub["region"])
            if sub["region"] == ALL_REGIONS_KEY:
                region_name = ALL_REGIONS_NAME
            header = f"🔔 <b>{sub['model']}</b> | {region_name}\n\n"
            await bot.send_message(
                chat_id=sub["user_id"],
                text=header + _format_ad(ad),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            sent_count += 1
            await asyncio.sleep(0.5)  # Задержка между сообщениями
        except Exception as e:
            logger.error(
                "Ошибка отправки объявления user=%s sub=%s: %s",
                sub["user_id"],
                sub["id"],
                e,
            )

    return sent_count


async def monitoring_loop(bot: Bot) -> None:
    """Основной цикл мониторинга."""
    logger.info("Мониторинг запущен (интервал: %d сек)", CHECK_INTERVAL)
    while True:
        try:
            subs = db.get_active_subscriptions()
            if subs:
                logger.info("Проверка %d подписок...", len(subs))
                for sub in subs:
                    try:
                        count = await check_subscription(bot, sub)
                        if count:
                            logger.info(
                                "Sub #%d: отправлено %d объявлений",
                                sub["id"],
                                count,
                            )
                    except Exception as e:
                        logger.error("Ошибка проверки sub #%d: %s", sub["id"], e)
                    # Пауза между подписками, чтобы не нагружать Авито
                    await asyncio.sleep(2)
        except Exception as e:
            logger.error("Ошибка в цикле мониторинга: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)
