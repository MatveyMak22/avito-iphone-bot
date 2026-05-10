"""Парсер объявлений Авито через Playwright (headless Chrome)."""

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode

from bs4 import BeautifulSoup
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Playwright,
)

logger = logging.getLogger(__name__)

PROXY_URL = os.getenv("PROXY_URL", "")

# Стелс-скрипт для обхода детекта автоматизации
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['ru-RU', 'ru', 'en-US', 'en'],
});

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});

Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});

Object.defineProperty(navigator, 'maxTouchPoints', {
    get: () => 0,
});
"""

# User-Agent-ы реальных браузеров
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
]


@dataclass
class Ad:
    """Одно объявление с Авито."""

    title: str
    price: str
    url: str
    location: str
    date: str
    image_url: Optional[str] = None


# ── Глобальный браузер ──────────────────────────────────────────────────────

_pw: Optional[Playwright] = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None


async def _get_context() -> BrowserContext:
    """Получить или создать контекст браузера."""
    global _pw, _browser, _context

    if _context is not None:
        return _context

    _pw = await async_playwright().start()

    launch_args: dict = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-gpu",
            "--window-size=1920,1080",
        ],
    }

    if PROXY_URL:
        launch_args["proxy"] = {"server": PROXY_URL}
        logger.info("Используется прокси: %s", PROXY_URL[:30] + "...")

    _browser = await _pw.chromium.launch(**launch_args)

    ua = random.choice(_USER_AGENTS)
    _context = await _browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=ua,
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        color_scheme="light",
        java_script_enabled=True,
    )

    await _context.add_init_script(_STEALTH_JS)

    # Инициализация: заходим на главную для получения cookies
    page = await _context.new_page()
    try:
        resp = await page.goto(
            "https://www.avito.ru/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        status = resp.status if resp else "?"
        await page.wait_for_timeout(random.randint(2000, 5000))
        cookies = await _context.cookies()
        logger.info(
            "Браузер инициализирован: status=%s, cookies=%d, ua=%s",
            status,
            len(cookies),
            ua[:50],
        )
    except Exception as e:
        logger.warning("Ошибка инициализации браузера: %s", e)
    finally:
        await page.close()

    return _context


async def reset_browser() -> None:
    """Сбросить браузер (при ошибках 429/403)."""
    global _pw, _browser, _context
    if _context:
        try:
            await _context.close()
        except Exception:
            pass
        _context = None
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
        _pw = None


async def close_browser() -> None:
    """Закрыть браузер при завершении работы."""
    await reset_browser()


# ── URL ─────────────────────────────────────────────────────────────────────


def _build_search_url(
    model: str,
    region: str,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
) -> str:
    """Построить URL поиска на Авито."""
    base = f"https://www.avito.ru/{region}/telefony"
    params: dict[str, str] = {
        "q": model,
        "s": "104",  # сортировка по дате (новые первые)
    }
    if price_min is not None:
        params["pmin"] = str(price_min)
    if price_max is not None:
        params["pmax"] = str(price_max)
    return f"{base}?{urlencode(params, quote_via=quote_plus)}"


# ── Основная функция ────────────────────────────────────────────────────────


async def fetch_ads(
    model: str,
    region: str,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    max_ads: int = 20,
    max_retries: int = 3,
) -> list[Ad]:
    """
    Получить список объявлений с Авито через Playwright (headless Chrome).

    Использует настоящий браузер: выполняет JS, проходит анти-бот-проверки,
    имеет реальный TLS-отпечаток и fingerprint.
    """
    url = _build_search_url(model, region, price_min, price_max)
    logger.info("Запрос: %s", url)

    for attempt in range(max_retries):
        page = None
        try:
            context = await _get_context()
            page = await context.new_page()

            # Случайная задержка (имитация реального пользователя)
            await asyncio.sleep(random.uniform(1.5, 4.0) + attempt * 3)

            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=30000
            )
            status = response.status if response else 0

            if status == 429:
                wait_time = (attempt + 1) * 25 + random.uniform(5, 15)
                logger.warning(
                    "429 Too Many Requests (попытка %d/%d). "
                    "Ждём %.0f сек...",
                    attempt + 1,
                    max_retries,
                    wait_time,
                )
                await page.close()
                page = None
                await reset_browser()
                await asyncio.sleep(wait_time)
                continue

            if status == 403:
                logger.warning(
                    "403 Forbidden (попытка %d/%d). Сбрасываем...",
                    attempt + 1,
                    max_retries,
                )
                await page.close()
                page = None
                await reset_browser()
                await asyncio.sleep(random.uniform(10, 20))
                continue

            # Ждём рендер карточек (Авито подгружает их JS)
            try:
                await page.wait_for_selector(
                    "[data-marker='item']",
                    timeout=10000,
                )
            except Exception:
                # Может не быть карточек — пробуем альтернативные селекторы
                try:
                    await page.wait_for_selector(
                        "[class*='iva-item']",
                        timeout=5000,
                    )
                except Exception:
                    pass

            # Скролл вниз для подгрузки lazy-загруженных элементов
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await page.wait_for_timeout(random.randint(1000, 2000))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(random.randint(1000, 2000))

            html = await page.content()
            await page.close()
            page = None

            ads = _parse_html(html, max_ads)
            if ads:
                logger.info("Найдено %d объявлений", len(ads))
                return ads

            logger.warning(
                "Не найдено объявлений (попытка %d/%d, status=%s)",
                attempt + 1,
                max_retries,
                status,
            )
            if attempt < max_retries - 1:
                await reset_browser()
                await asyncio.sleep(random.uniform(5, 10))

        except Exception as e:
            logger.error(
                "Ошибка запроса (попытка %d/%d): %s",
                attempt + 1,
                max_retries,
                e,
            )
            await reset_browser()
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(5, 10))
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    logger.error("Все %d попыток неудачны для: %s", max_retries, url)
    return []


# ── HTML-парсинг ────────────────────────────────────────────────────────────


def _parse_html(html: str, max_ads: int) -> list[Ad]:
    """Парсинг HTML-страницы выдачи Авито."""
    soup = BeautifulSoup(html, "html.parser")
    ads: list[Ad] = []

    items = soup.find_all("div", {"data-marker": "item"})
    if not items:
        items = soup.find_all("div", class_=lambda c: c and "iva-item" in c)

    if not items:
        page_text = soup.get_text()
        if "captcha" in page_text.lower() or "blocked" in page_text.lower():
            logger.warning("Авито показывает капчу/блокировку")
        else:
            logger.warning(
                "Не найдено карточек объявлений (HTML: %d символов)",
                len(html),
            )

    for item in items[:max_ads]:
        try:
            ad = _parse_item(item)
            if ad:
                ads.append(ad)
        except Exception as e:
            logger.debug("Не удалось распарсить карточку: %s", e)
            continue

    return ads


def _parse_item(item) -> Optional[Ad]:
    """Извлечь данные из одной карточки объявления."""
    title_tag = item.find("a", {"data-marker": "item-title"})
    if not title_tag:
        title_tag = item.find(
            "a", class_=lambda c: c and "title" in c.lower()
        )
    if not title_tag:
        title_tag = item.find("h3")
        if title_tag:
            title_tag = title_tag.find("a") or title_tag

    if not title_tag:
        return None

    title = title_tag.get_text(strip=True)
    href = title_tag.get("href", "")
    if href and not href.startswith("http"):
        href = f"https://www.avito.ru{href}"

    price_tag = item.find("meta", {"itemprop": "price"})
    if price_tag:
        price = price_tag.get("content", "")
        currency = item.find("meta", {"itemprop": "priceCurrency"})
        currency_text = currency.get("content", "RUB") if currency else "RUB"
        price = f"{int(float(price)):,} {currency_text}".replace(",", " ")
    else:
        price_tag = item.find(
            "span", {"data-marker": "item-price"}
        ) or item.find("span", class_=lambda c: c and "price" in c.lower())
        price = (
            price_tag.get_text(strip=True) if price_tag else "Цена не указана"
        )

    location_tag = item.find("div", {"data-marker": "item-address"})
    if not location_tag:
        location_tag = item.find(
            "span", class_=lambda c: c and "geo" in c.lower()
        )
    location = location_tag.get_text(strip=True) if location_tag else ""

    date_tag = item.find("div", {"data-marker": "item-date"})
    if not date_tag:
        date_tag = item.find(
            "span", class_=lambda c: c and "date" in c.lower()
        )
    date = date_tag.get_text(strip=True) if date_tag else ""

    img_tag = item.find("img")
    image_url = img_tag.get("src") if img_tag else None

    return Ad(
        title=title,
        price=price,
        url=href,
        location=location,
        date=date,
        image_url=image_url,
    )
