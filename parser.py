"""Парсер объявлений Авито с обходом блокировки."""

import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Прокси (опционально, задаётся через .env)
PROXY_URL = os.getenv("PROXY_URL", "")

# Актуальные User-Agent строки
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
    ),
]

# Глобальная сессия для переиспользования cookies
_session: Optional[requests.Session] = None
_session_ua: str = ""


@dataclass
class Ad:
    """Одно объявление с Авито."""

    title: str
    price: str
    url: str
    location: str
    date: str
    image_url: Optional[str] = None


def _get_session() -> tuple[requests.Session, str]:
    """Получить или создать HTTP-сессию с cookies."""
    global _session, _session_ua

    if _session is not None:
        return _session, _session_ua

    _session = requests.Session()
    _session_ua = random.choice(USER_AGENTS)

    if PROXY_URL:
        _session.proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }
        logger.info("Используется прокси: %s", PROXY_URL[:30] + "...")

    # Сначала заходим на главную, чтобы получить cookies
    headers = _make_headers(_session_ua, referer=None)
    try:
        resp = _session.get(
            "https://www.avito.ru/", headers=headers, timeout=15
        )
        logger.info(
            "Инициализация сессии: status=%d, cookies=%d",
            resp.status_code,
            len(_session.cookies),
        )
    except requests.RequestException as e:
        logger.warning("Не удалось инициализировать сессию: %s", e)

    return _session, _session_ua


def reset_session() -> None:
    """Сбросить сессию (при ошибках 429/403)."""
    global _session, _session_ua
    _session = None
    _session_ua = ""


def _make_headers(user_agent: str, referer: Optional[str] = None) -> dict[str, str]:
    """Заголовки, имитирующие реальный браузер."""
    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if referer else "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
    return headers


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


def fetch_ads(
    model: str,
    region: str,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    max_ads: int = 20,
    max_retries: int = 3,
) -> list[Ad]:
    """
    Получить список объявлений с Авито по заданным фильтрам.

    Поддерживает retry с экспоненциальной задержкой при ошибках 429/403.
    """
    url = _build_search_url(model, region, price_min, price_max)
    logger.info("Запрос: %s", url)

    for attempt in range(max_retries):
        session, ua = _get_session()

        # Случайная задержка перед запросом (3-7 секунд)
        delay = random.uniform(3.0, 7.0) + (attempt * 5)
        time.sleep(delay)

        try:
            referer = f"https://www.avito.ru/{region}/telefony"
            headers = _make_headers(ua, referer=referer)
            response = session.get(url, headers=headers, timeout=20)

            if response.status_code == 429:
                wait_time = (attempt + 1) * 15 + random.uniform(5, 15)
                logger.warning(
                    "429 Too Many Requests (попытка %d/%d). "
                    "Ждём %.0f сек...",
                    attempt + 1,
                    max_retries,
                    wait_time,
                )
                reset_session()
                time.sleep(wait_time)
                continue

            if response.status_code == 403:
                logger.warning(
                    "403 Forbidden (попытка %d/%d). Сбрасываем сессию...",
                    attempt + 1,
                    max_retries,
                )
                reset_session()
                time.sleep(random.uniform(10, 20))
                continue

            response.raise_for_status()
            return _parse_html(response.text, max_ads)

        except requests.RequestException as e:
            logger.error(
                "Ошибка запроса (попытка %d/%d): %s",
                attempt + 1,
                max_retries,
                e,
            )
            reset_session()
            if attempt < max_retries - 1:
                time.sleep(random.uniform(5, 10))

    logger.error("Все %d попыток неудачны для: %s", max_retries, url)
    return []


def _parse_html(html: str, max_ads: int) -> list[Ad]:
    """Парсинг HTML-страницы выдачи Авито."""
    soup = BeautifulSoup(html, "html.parser")
    ads: list[Ad] = []

    # Авито использует data-marker="item" для карточек объявлений
    items = soup.find_all("div", {"data-marker": "item"})
    if not items:
        # Альтернативный селектор — класс iva-item
        items = soup.find_all("div", class_=lambda c: c and "iva-item" in c)

    if not items:
        # Проверим, не получили ли мы страницу с капчей
        page_text = soup.get_text()
        if "captcha" in page_text.lower() or "blocked" in page_text.lower():
            logger.warning("Авито показывает капчу/блокировку")
            reset_session()
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

    logger.info("Найдено %d объявлений", len(ads))
    return ads


def _parse_item(item) -> Optional[Ad]:
    """Извлечь данные из одной карточки объявления."""
    # Заголовок и ссылка
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

    # Цена
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
        price = price_tag.get_text(strip=True) if price_tag else "Цена не указана"

    # Локация
    location_tag = item.find("div", {"data-marker": "item-address"})
    if not location_tag:
        location_tag = item.find(
            "span", class_=lambda c: c and "geo" in c.lower()
        )
    location = location_tag.get_text(strip=True) if location_tag else ""

    # Дата
    date_tag = item.find("div", {"data-marker": "item-date"})
    if not date_tag:
        date_tag = item.find(
            "span", class_=lambda c: c and "date" in c.lower()
        )
    date = date_tag.get_text(strip=True) if date_tag else ""

    # Изображение
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
