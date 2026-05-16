"""Обработчики команд и callback-запросов Telegram-бота."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
from config import ALL_REGIONS_KEY, ALL_REGIONS_NAME, REGIONS
from monitor import fetch_initial_ads
from keyboards import (
    confirm_keyboard,
    main_menu_keyboard,
    models_keyboard,
    regions_keyboard,
    skip_price_keyboard,
    subscriptions_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()

MAX_SUBSCRIPTIONS = 10


class SearchForm(StatesGroup):
    """Состояния FSM для создания подписки."""

    choosing_model = State()
    choosing_region = State()
    entering_price_min = State()
    entering_price_max = State()
    confirming = State()


# ── /start ──────────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я бот для мониторинга объявлений iPhone на Авито.\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1. Нажмите <b>«Новый поиск»</b>\n"
        "2. Выберите модель iPhone\n"
        "3. Выберите регион\n"
        "4. Укажите диапазон цен (можно пропустить)\n"
        "5. Подтвердите подписку\n\n"
        "После этого бот будет автоматически присылать "
        "вам новые объявления каждые 2 минуты.\n\n"
        "Максимум подписок: <b>10</b>\n\n"
        "/start — главное меню\n"
        "/mysubs — мои подписки",
        parse_mode="HTML",
    )


@router.message(Command("mysubs"))
async def cmd_mysubs(message: Message) -> None:
    subs = db.get_active_subscriptions(message.from_user.id)
    if not subs:
        await message.answer(
            "У вас нет активных подписок.\n"
            "Нажмите /start чтобы создать новую.",
        )
        return
    await _show_subscriptions(message, subs)


# ── Главное меню (callback) ────────────────────────────────────────────────


@router.callback_query(F.data == "new_search")
async def cb_new_search(callback: CallbackQuery, state: FSMContext) -> None:
    count = db.count_user_subscriptions(callback.from_user.id)
    if count >= MAX_SUBSCRIPTIONS:
        await callback.answer(
            f"Достигнут лимит подписок ({MAX_SUBSCRIPTIONS}).", show_alert=True
        )
        return
    await state.set_state(SearchForm.choosing_model)
    await callback.message.edit_text(
        "📱 <b>Выберите модель iPhone:</b>",
        reply_markup=models_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "my_subs")
async def cb_my_subs(callback: CallbackQuery) -> None:
    subs = db.get_active_subscriptions(callback.from_user.id)
    if not subs:
        await callback.message.edit_text(
            "У вас нет активных подписок.",
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()
        return
    text = "📋 <b>Ваши подписки</b>\nНажмите на подписку, чтобы удалить:"
    await callback.message.edit_text(
        text,
        reply_markup=subscriptions_keyboard(subs),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1. Нажмите <b>«Новый поиск»</b>\n"
        "2. Выберите модель iPhone\n"
        "3. Выберите регион\n"
        "4. Укажите диапазон цен (можно пропустить)\n"
        "5. Подтвердите подписку\n\n"
        "Бот будет присылать новые объявления каждые 2 минуты.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ── Выбор модели ────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("models_page:"))
async def cb_models_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(
        reply_markup=models_keyboard(page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("model:"), SearchForm.choosing_model)
async def cb_model_chosen(
    callback: CallbackQuery, state: FSMContext
) -> None:
    model = callback.data.split(":", 1)[1]
    await state.update_data(model=model)
    await state.set_state(SearchForm.choosing_region)
    await callback.message.edit_text(
        f"📱 Модель: <b>{model}</b>\n\n🌍 <b>Выберите регион:</b>",
        reply_markup=regions_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Выбор региона ───────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("regions_page:"))
async def cb_regions_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(
        reply_markup=regions_keyboard(page)
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("region:"), SearchForm.choosing_region
)
async def cb_region_chosen(
    callback: CallbackQuery, state: FSMContext
) -> None:
    region = callback.data.split(":", 1)[1]
    region_name = REGIONS.get(region, ALL_REGIONS_NAME)
    await state.update_data(region=region, region_name=region_name)
    await state.set_state(SearchForm.entering_price_min)
    data = await state.get_data()
    await callback.message.edit_text(
        f"📱 Модель: <b>{data['model']}</b>\n"
        f"🌍 Регион: <b>{region_name}</b>\n\n"
        "💰 Введите <b>минимальную</b> цену (в рублях).\n"
        "Или нажмите «Пропустить».",
        reply_markup=skip_price_keyboard("price_min"),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Ввод цены ───────────────────────────────────────────────────────────────


@router.callback_query(F.data == "skip_price_min", SearchForm.entering_price_min)
async def cb_skip_price_min(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(price_min=None)
    await state.set_state(SearchForm.entering_price_max)
    data = await state.get_data()
    await callback.message.edit_text(
        f"📱 Модель: <b>{data['model']}</b>\n"
        f"🌍 Регион: <b>{data['region_name']}</b>\n"
        f"💰 Мин. цена: <b>не указана</b>\n\n"
        "💰 Введите <b>максимальную</b> цену (в рублях).\n"
        "Или нажмите «Пропустить».",
        reply_markup=skip_price_keyboard("price_max"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SearchForm.entering_price_min)
async def msg_price_min(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("❌ Введите число (например: 30000)")
        return
    price_min = int(text)
    await state.update_data(price_min=price_min)
    await state.set_state(SearchForm.entering_price_max)
    data = await state.get_data()
    await message.answer(
        f"📱 Модель: <b>{data['model']}</b>\n"
        f"🌍 Регион: <b>{data['region_name']}</b>\n"
        f"💰 Мин. цена: <b>{price_min:,} ₽</b>\n\n"
        "💰 Введите <b>максимальную</b> цену (в рублях).\n"
        "Или нажмите «Пропустить».",
        reply_markup=skip_price_keyboard("price_max"),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "skip_price_max", SearchForm.entering_price_max)
async def cb_skip_price_max(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(price_max=None)
    await _show_confirmation(callback.message, state)
    await callback.answer()


@router.message(SearchForm.entering_price_max)
async def msg_price_max(message: Message, state: FSMContext) -> None:
    text = message.text.strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("❌ Введите число (например: 80000)")
        return
    price_max = int(text)
    data = await state.get_data()
    if data.get("price_min") and price_max < data["price_min"]:
        await message.answer(
            "❌ Максимальная цена не может быть меньше минимальной."
        )
        return
    await state.update_data(price_max=price_max)
    await _show_confirmation(message, state)


async def _show_confirmation(
    message: Message, state: FSMContext
) -> None:
    """Показать итоговое подтверждение подписки."""
    await state.set_state(SearchForm.confirming)
    data = await state.get_data()
    price_min_str = (
        f"{data['price_min']:,} ₽" if data.get("price_min") else "не указана"
    )
    price_max_str = (
        f"{data['price_max']:,} ₽" if data.get("price_max") else "не указана"
    )
    text = (
        "📝 <b>Подтвердите подписку:</b>\n\n"
        f"📱 Модель: <b>{data['model']}</b>\n"
        f"🌍 Регион: <b>{data['region_name']}</b>\n"
        f"💰 Мин. цена: <b>{price_min_str}</b>\n"
        f"💰 Макс. цена: <b>{price_max_str}</b>"
    )
    try:
        await message.edit_text(
            text, reply_markup=confirm_keyboard(), parse_mode="HTML"
        )
    except Exception:
        await message.answer(
            text, reply_markup=confirm_keyboard(), parse_mode="HTML"
        )


# ── Подтверждение / Отмена ──────────────────────────────────────────────────


@router.callback_query(F.data == "confirm", SearchForm.confirming)
async def cb_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    sub_id = db.add_subscription(
        user_id=callback.from_user.id,
        model=data["model"],
        region=data["region"],
        price_min=data.get("price_min"),
        price_max=data.get("price_max"),
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Подписка #{sub_id} создана!</b>\n\n"
        f"📱 {data['model']} | 🌍 {data['region_name']}\n\n"
        "⏳ Загружаю последние объявления...",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Подписка создана!")

    # Сразу отправить 5-10 последних объявлений
    bot = callback.bot
    sub = {
        "id": sub_id,
        "user_id": callback.from_user.id,
        "model": data["model"],
        "region": data["region"],
        "region_name": data["region_name"],
        "price_min": data.get("price_min"),
        "price_max": data.get("price_max"),
    }
    asyncio.create_task(fetch_initial_ads(bot, sub))


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ Подписка отменена.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ── Удаление подписки ───────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("unsub:"))
async def cb_unsubscribe(callback: CallbackQuery) -> None:
    sub_id = int(callback.data.split(":")[1])
    db.deactivate_subscription(sub_id)
    await callback.answer("Подписка удалена!", show_alert=True)
    subs = db.get_active_subscriptions(callback.from_user.id)
    if subs:
        await callback.message.edit_reply_markup(
            reply_markup=subscriptions_keyboard(subs)
        )
    else:
        await callback.message.edit_text(
            "У вас больше нет активных подписок.",
            reply_markup=main_menu_keyboard(),
        )


# ── Вспомогательные ─────────────────────────────────────────────────────────


async def _show_subscriptions(message: Message, subs: list[dict]) -> None:
    """Показать список подписок пользователя."""
    lines = ["📋 <b>Ваши подписки:</b>\n"]
    for s in subs:
        region_name = REGIONS.get(s["region"], s["region"])
        if s["region"] == ALL_REGIONS_KEY:
            region_name = ALL_REGIONS_NAME
        price_info = ""
        if s["price_min"] or s["price_max"]:
            pmin = f"{s['price_min']:,} ₽" if s["price_min"] else "—"
            pmax = f"{s['price_max']:,} ₽" if s["price_max"] else "—"
            price_info = f" | {pmin} – {pmax}"
        lines.append(f"• #{s['id']} {s['model']} | {region_name}{price_info}")
    lines.append("\nНажмите на подписку, чтобы удалить:")
    await message.answer(
        "\n".join(lines),
        reply_markup=subscriptions_keyboard(subs),
        parse_mode="HTML",
    )
