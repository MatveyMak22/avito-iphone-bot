"""Конфигурация бота и парсера Авито."""

import os

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Интервал проверки новых объявлений (в секундах)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))

# Путь к базе данных
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Модели iPhone (от 7 до 16 Pro Max)
IPHONE_MODELS = [
    "iPhone 7",
    "iPhone 7 Plus",
    "iPhone 8",
    "iPhone 8 Plus",
    "iPhone X",
    "iPhone XR",
    "iPhone XS",
    "iPhone XS Max",
    "iPhone 11",
    "iPhone 11 Pro",
    "iPhone 11 Pro Max",
    "iPhone 12",
    "iPhone 12 Mini",
    "iPhone 12 Pro",
    "iPhone 12 Pro Max",
    "iPhone 13",
    "iPhone 13 Mini",
    "iPhone 13 Pro",
    "iPhone 13 Pro Max",
    "iPhone 14",
    "iPhone 14 Plus",
    "iPhone 14 Pro",
    "iPhone 14 Pro Max",
    "iPhone 15",
    "iPhone 15 Plus",
    "iPhone 15 Pro",
    "iPhone 15 Pro Max",
    "iPhone 16",
    "iPhone 16 Plus",
    "iPhone 16 Pro",
    "iPhone 16 Pro Max",
]

# Регионы (slug для URL Авито -> отображаемое название)
REGIONS = {
    "moskva": "Москва",
    "sankt-peterburg": "Санкт-Петербург",
    "novosibirsk": "Новосибирск",
    "ekaterinburg": "Екатеринбург",
    "kazan": "Казань",
    "nizhniy_novgorod": "Нижний Новгород",
    "chelyabinsk": "Челябинск",
    "samara": "Самара",
    "krasnodar": "Краснодар",
    "rostov-na-donu": "Ростов-на-Дону",
    "ufa": "Уфа",
    "voronezh": "Воронеж",
    "perm": "Пермь",
    "volgograd": "Волгоград",
    "tyumen": "Тюмень",
}

# Специальный ключ для "Все регионы"
ALL_REGIONS_KEY = "rossiya"
ALL_REGIONS_NAME = "Вся Россия"
