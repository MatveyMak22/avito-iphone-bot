"""Парсер объявлений Авито с обходом блокировки через curl_cffi."""

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

# Прокси (опционально, задаётся через .env)
PROXY_URL = os.getenv("PROXY_URL", "")

# Браузерные impersonate-профили для curl_cffi
BROWSER_PROFILES = [
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
    "chrome107",
    "chrome104",
    "edge101",
    "safari17_0",
    "safari15_5",
]

# Глобальная сессия
_session: Optional[curl_requests.Session] = None
_session_profile: str = ""


@dataclass
class Ad:
    """Одно объявление с Авито."""

    title: str
    price: str
    url: str
    location: str
    date: str
    image_url: Optional[str] = None


def _get_session() -> tuple[curl_requests.Session, str]:
    """Получить или создать HTTP-сессию с TLS-отпечатком браузера."""
    global _session, _session_profile

    if _session is not None:
        return _session, _session_profile

    _session_profile = random.choice(BROWSER_PROFILES)
    _session = curl_requests.Session(impersonate=_session_profile)

    if PROXY_URL:
        _session.proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }
        logger.info("Используется прокси: %s", PROXY_URL[:30] + "...")

    # Заходим на главную, чтобы получить cookies
    headers = _make_headers(referer=None)
    try:
        resp = _session.get(
            "https://www.avito.ru/", headers=headers, timeout=15
        )
        logger.info(
            "Инициализация сессии (%s): status=%d, cookies=%d",
            _session_profile,
            resp.status_code,
            len(resp.cookies),
        )
    except Exception as e:
        logger.warning("Не удалось инициализировать сессию: %s", e)

    return _session, _session_profile


def reset_session() -> None:
    """Сбросить сессию (при ошибках 429/403)."""
    global _session, _session_profile
    if _session is not None:
        try:
            _session.close()
        except Exception:
            pass
    _session = None
    _session_profile = ""


def _make_headers(referer: Optional[str] = None) -> dict[str, str]:
    """Минимальные заголовки (TLS-отпечаток уже от curl_cffi)."""
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
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

    Использует curl_cffi для имитации TLS-отпечатка браузера.
    Поддерживает retry с экспоненциальной задержкой при ошибках 429/403.
    """
    url = _build_search_url(model, region, price_min, price_max)
    logger.info("Запрос: %s", url)

    for attempt in range(max_retries):
        session, profile = _get_session()

        # Случайная задержка перед запросом
        delay = random.uniform(2.0, 5.0) + (attempt * 5)
        time.sleep(delay)

        try:
            referer = f"https://www.avito.ru/{region}/telefony"
            headers = _make_headers(referer=referer)
            response = session.get(url, headers=headers, timeout=20)

            if response.status_code == 429:
                wait_time = (attempt + 1) * 20 + random.uniform(5, 15)
                logger.warning(
                    "429 Too Many Requests (попытка %d/%d, профиль: %s). "
                    "Ждём %.0f сек...",
                    attempt + 1,
                    max_retries,
                    profile,
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

            if response.status_code != 200:
                logger.error("HTTP %d для %s", response.status_code, url)
                reset_session()
                continue

            # Сначала пробуем извлечь данные из JSON (embedded в HTML)
            ads = _parse_json_data(response.text, max_ads)
            if ads:
                return ads

            # Фоллбэк — парсинг HTML
            return _parse_html(response.text, max_ads)

        except Exception as e:
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


def _parse_json_data(html: str, max_ads: int) -> list[Ad]:
    """Попытка извлечь объявления из JSON-данных, встроенных в HTML."""
    ads: list[Ad] = []

    # Авито встраивает данные в window.__initialData__ или window.__state__
    patterns = [
        r'window\.__initialData__\s*=\s*"(.+?)"\s*;',
        r'window\.__state__\s*=\s*(\{.+?\})\s*;',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            continue

        try:
            raw = match.group(1)
            # __initialData__ закодирован как строка
            if pattern.startswith(r"window\.__initialData__"):
                raw = raw.encode().decode("unicode_escape")
            data = json.loads(raw)

            # Ищем items в разных структурах JSON
            items = _find_items_in_json(data)
            for item_data in items[:max_ads]:
                ad = _json_item_to_ad(item_data)
                if ad:
                    ads.append(ad)

            if ads:
                logger.info("Извлечено %d объявлений из JSON", len(ads))
                return ads
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("Не удалось разобрать JSON: %s", e)
            continue

    return ads


def _find_items_in_json(data: dict) -> list[dict]:
    """Рекурсивно найти список объявлений в JSON-данных."""
    if isinstance(data, dict):
        # Ищем ключи, похожие на списки объявлений
        for key in ("items", "list", "results", "ads", "catalog"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # Рекурсивный поиск
        for value in data.values():
            result = _find_items_in_json(value)
            if result:
                return result
    return []


def _json_item_to_ad(item: dict) -> Optional[Ad]:
    """Конвертировать JSON-элемент в объект Ad."""
    try:
        title = item.get("title") or item.get("name", "")
        if not title:
            return None

        # Цена
        price_val = item.get("price") or item.get("priceDetailed", {})
        if isinstance(price_val, dict):
            price_str = price_val.get("string") or price_val.get("value", "")
        elif isinstance(price_val, (int, float)):
            price_str = f"{int(price_val):,} ₽".replace(",", " ")
        else:
            price_str = str(price_val) if price_val else "Цена не указана"

        # URL
        url_path = item.get("url") or item.get("uri", "")
        if url_path and not url_path.startswith("http"):
            url_path = f"https://www.avito.ru{url_path}"

        # Локация
        location = item.get("location") or item.get("address", "")
        if isinstance(location, dict):
            location = location.get("name", "")

        # Дата
        date = item.get("time") or item.get("date", "")
        if isinstance(date, dict):
            date = date.get("relative", "") or date.get("absolute", "")

        # Изображение
        images = item.get("images") or item.get("photos", [])
        image_url = None
        if images and isinstance(images, list):
            first = images[0]
            if isinstance(first, str):
                image_url = first
            elif isinstance(first, dict):
                image_url = first.get("url") or first.get("src")

        return Ad(
            title=title,
            price=price_str,
            url=url_path,
            location=str(location),
            date=str(date),
            image_url=image_url,
        )
    except Exception as e:
        logger.debug("Ошибка парсинга JSON-элемента: %s", e)
        return None


def _parse_html(html: str, max_ads: int) -> list[Ad]:
    """Парсинг HTML-страницы выдачи Авито."""
    soup = BeautifulSoup(html, "html.parser")
    ads: list[Ad] = []

    # Авито использует data-marker="item" для карточек объявлений
    items = soup.find_all("div", {"data-marker": "item"})
    if not items:
        items = soup.find_all("div", class_=lambda c: c and "iva-item" in c)

    if not items:
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

    logger.info("Найдено %d объявлений (HTML)", len(ads))
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
        price = price_tag.get_text(strip=True) if price_tag else "Цена не указана"

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
