"""Клавиатуры для Telegram-бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ALL_REGIONS_KEY, ALL_REGIONS_NAME, IPHONE_MODELS, REGIONS


def models_keyboard(page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Клавиатура выбора модели iPhone с пагинацией."""
    total_pages = (len(IPHONE_MODELS) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    models_page = IPHONE_MODELS[start:end]

    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(models_page), 2):
        row = []
        for model in models_page[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=model, callback_data=f"model:{model}"
                )
            )
        buttons.append(row)

    # Навигация
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"models_page:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"models_page:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def regions_keyboard(page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Клавиатура выбора региона с пагинацией."""
    region_items = list(REGIONS.items())
    total_pages = (len(region_items) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    regions_page = region_items[start:end]

    buttons: list[list[InlineKeyboardButton]] = []

    # Кнопка "Вся Россия" на первой странице
    if page == 0:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🇷🇺 {ALL_REGIONS_NAME}",
                    callback_data=f"region:{ALL_REGIONS_KEY}",
                )
            ]
        )

    for i in range(0, len(regions_page), 2):
        row = []
        for slug, name in regions_page[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=name, callback_data=f"region:{slug}"
                )
            )
        buttons.append(row)

    # Навигация
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"regions_page:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"regions_page:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения подписки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            ]
        ]
    )


def subscriptions_keyboard(subs: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком подписок для удаления."""
    buttons: list[list[InlineKeyboardButton]] = []
    for sub in subs:
        region_name = REGIONS.get(sub["region"], sub["region"])
        if sub["region"] == ALL_REGIONS_KEY:
            region_name = ALL_REGIONS_NAME
        label = f"❌ {sub['model']} | {region_name}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label, callback_data=f"unsub:{sub['id']}"
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Новый поиск", callback_data="new_search"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Мои подписки", callback_data="my_subs"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Помощь", callback_data="help"
                )
            ],
        ]
    )


def skip_price_keyboard(step: str) -> InlineKeyboardMarkup:
    """Клавиатура для пропуска ввода цены."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить", callback_data=f"skip_{step}"
                )
            ]
        ]
    )
