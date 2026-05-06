"""Парсер объявлений Авито."""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.2 Safari/605.1.15"
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


def _get_headers() -> dict[str, str]:
    """Заголовки для запроса, имитирующие обычный браузер."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,*/*;q=0.8"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


def fetch_ads(
    model: str,
    region: str,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    max_ads: int = 20,
) -> list[Ad]:
    """
    Получить список объявлений с Авито по заданным фильтрам.

    Возвращает список объектов Ad. При ошибке возвращает пустой список.
    """
    url = _build_search_url(model, region, price_min, price_max)
    logger.info("Запрос: %s", url)

    try:
        time.sleep(random.uniform(1.0, 3.0))

        session = requests.Session()
        response = session.get(url, headers=_get_headers(), timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Ошибка запроса к Авито: %s", e)
        return []

    return _parse_html(response.text, max_ads)


def _parse_html(html: str, max_ads: int) -> list[Ad]:
    """Парсинг HTML-страницы выдачи Авито."""
    soup = BeautifulSoup(html, "html.parser")
    ads: list[Ad] = []

    # Авито использует data-marker="item" для карточек объявлений
    items = soup.find_all("div", {"data-marker": "item"})
    if not items:
        # Альтернативный селектор — класс iva-item
        items = soup.find_all("div", class_=lambda c: c and "iva-item" in c)

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
