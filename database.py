"""Модуль работы с базой данных SQLite."""

import sqlite3
from typing import Optional

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Создание таблиц при первом запуске."""
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            model TEXT NOT NULL,
            region TEXT NOT NULL,
            price_min INTEGER,
            price_max INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS seen_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            ad_url TEXT NOT NULL,
            UNIQUE(subscription_id, ad_url),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_subs_user
            ON subscriptions(user_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_seen_sub
            ON seen_ads(subscription_id);
        """
    )
    conn.commit()
    conn.close()


def add_subscription(
    user_id: int,
    model: str,
    region: str,
    price_min: Optional[int],
    price_max: Optional[int],
) -> int:
    """Добавить подписку пользователя. Возвращает ID подписки."""
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO subscriptions (user_id, model, region, price_min, price_max)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, model, region, price_min, price_max),
    )
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sub_id


def get_active_subscriptions(user_id: Optional[int] = None) -> list[dict]:
    """Получить активные подписки. Если user_id=None, вернуть все."""
    conn = get_connection()
    if user_id is not None:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE is_active = 1"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deactivate_subscription(sub_id: int) -> None:
    """Деактивировать подписку."""
    conn = get_connection()
    conn.execute(
        "UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sub_id,)
    )
    conn.commit()
    conn.close()


def is_ad_seen(subscription_id: int, ad_url: str) -> bool:
    """Проверить, было ли объявление уже отправлено."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM seen_ads WHERE subscription_id = ? AND ad_url = ?",
        (subscription_id, ad_url),
    ).fetchone()
    conn.close()
    return row is not None


def mark_ad_seen(subscription_id: int, ad_url: str) -> None:
    """Отметить объявление как отправленное."""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO seen_ads (subscription_id, ad_url) VALUES (?, ?)",
        (subscription_id, ad_url),
    )
    conn.commit()
    conn.close()


def count_user_subscriptions(user_id: int) -> int:
    """Количество активных подписок пользователя."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM subscriptions WHERE user_id = ? AND is_active = 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["cnt"]
