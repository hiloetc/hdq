import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

DEFAULT_SETTINGS = {
    "greeting_text": (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Выберите нужный раздел в меню ниже:"
    ),
    "private_block_price": "100",
    "private_block_description": (
        "🔒 <b>PRIVATE BLOCK</b>\n\n"
        "Доступ на закрытый Discord-сервер.\n"
        "После оплаты бот моментально выдаст вам ссылку для входа."
    ),
    "private_channel_id": "",
    "private_channel_link": "",
}


@contextmanager
def get_conn():
    """Yield a SQLite connection with row_factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create database tables and populate default settings if missing."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS builds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                delivery_text TEXT DEFAULT '',
                delivery_file_id TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                item_type TEXT NOT NULL,
                item_id INTEGER,
                item_title TEXT NOT NULL,
                amount INTEGER NOT NULL,
                charge_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS required_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                title TEXT NOT NULL,
                invite_link TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS private_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT DEFAULT '',
                source TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        # Seed 2 starter builds if the catalog is completely empty
        build_cnt = conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
        if build_cnt == 0:
            conn.executemany(
                """
                INSERT INTO builds (title, description, price, delivery_text, delivery_file_id)
                VALUES (?, ?, ?, ?, '')
                """,
                [
                    (
                        "Сборка 1",
                        "Описание для Сборки 1 (можно изменить в Админ-панели).",
                        50,
                        "Спасибо за покупку Сборки 1! Замените этот текст/файл в Админ-панели.",
                    ),
                    (
                        "Сборка 2",
                        "Описание для Сборки 2 (можно изменить в Админ-панели).",
                        100,
                        "Спасибо за покупку Сборки 2! Замените этот текст/файл в Админ-панели.",
                    ),
                ],
            )

        # If PRIVATE_CHANNEL_ID is provided via env and DB value is still empty, prefill it.
        env_channel_id = os.getenv("PRIVATE_CHANNEL_ID", "").strip()
        if env_channel_id:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'private_channel_id'"
            ).fetchone()
            if row and not row["value"]:
                conn.execute(
                    "UPDATE settings SET value = ? WHERE key = 'private_channel_id'",
                    (env_channel_id,),
                )


def get_setting(key: str, default: str = "") -> str:
    """Fetch a setting value by key."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """Insert or update a setting value."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def list_builds(active_only: bool = True) -> list[dict[str, Any]]:
    """Return catalog builds ordered by id."""
    query = "SELECT * FROM builds"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id ASC"
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def get_build(build_id: int) -> Optional[dict[str, Any]]:
    """Return a single build by id."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM builds WHERE id = ? AND is_active = 1", (build_id,)
        ).fetchone()
        return dict(row) if row else None


def add_build(
    title: str,
    description: str,
    price: int,
    delivery_text: str = "",
    delivery_file_id: str = "",
) -> int:
    """Insert a new build into the catalog and return its ID."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO builds (title, description, price, delivery_text, delivery_file_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, description, price, delivery_text, delivery_file_id),
        )
        return cur.lastrowid


def update_build_field(build_id: int, field: str, value: Any) -> None:
    """Update an allowed field of a build."""
    allowed = {"title", "description", "price", "delivery_text", "delivery_file_id"}
    if field not in allowed:
        raise ValueError(f"Unsupported field: {field}")
    with get_conn() as conn:
        conn.execute(f"UPDATE builds SET {field} = ? WHERE id = ?", (value, build_id))


def delete_build(build_id: int) -> None:
    """Soft-delete a build from the catalog."""
    with get_conn() as conn:
        conn.execute("UPDATE builds SET is_active = 0 WHERE id = ?", (build_id,))


def record_purchase(
    user_id: int,
    username: str,
    item_type: str,
    item_id: Optional[int],
    item_title: str,
    amount: int,
    charge_id: str,
) -> None:
    """Log a completed Telegram Stars purchase."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO purchases (user_id, username, item_type, item_id, item_title, amount, charge_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, item_type, item_id, item_title, amount, charge_id),
        )


def get_stats() -> dict[str, int]:
    """Return total purchase count and total Stars revenue."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM purchases"
        ).fetchone()
        return {"count": row["cnt"], "total_stars": row["total"]}


def list_required_channels() -> list[dict[str, Any]]:
    """Return all mandatory subscription channels."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM required_channels ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_required_channel(chat_id: str, title: str, invite_link: str) -> int:
    """Add a mandatory subscription channel and return its row ID."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO required_channels (chat_id, title, invite_link) VALUES (?, ?, ?)",
            (chat_id, title, invite_link),
        )
        return cur.lastrowid


def delete_required_channel(channel_row_id: int) -> None:
    """Remove a mandatory subscription channel by row ID."""
    with get_conn() as conn:
        conn.execute("DELETE FROM required_channels WHERE id = ?", (channel_row_id,))


def upsert_user(user_id: int, username: str = "", first_name: str = "") -> None:
    """Save or update a Telegram user's username and ID."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, username.lstrip("@"), first_name),
        )


def find_user_by_username_or_id(identifier: str) -> Optional[dict[str, Any]]:
    """Find a stored user by @username (case-insensitive) or numeric user_id."""
    clean = identifier.strip().lstrip("@")
    if not clean:
        return None
    with get_conn() as conn:
        if clean.isdigit():
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (int(clean),)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (clean,)
            ).fetchone()
        return dict(row) if row else None


def list_purchases(limit: int = 30) -> list[dict[str, Any]]:
    """Return recent purchases ordered newest-first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM purchases ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_private_member(
    user_id: Optional[int], username: str, source: str = "stars"
) -> int:
    """Record a user who received Private Block access."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO private_members (user_id, username, source) VALUES (?, ?, ?)",
            (user_id, username.lstrip("@"), source),
        )
        return cur.lastrowid


def list_private_members(limit: int = 50) -> list[dict[str, Any]]:
    """Return users who have Private Block access, newest-first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM private_members ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def is_private_member(user_id: int, username: str = "") -> bool:
    """Return True if the user already has Private Block access by user_id or username."""
    clean_username = username.strip().lstrip("@")
    with get_conn() as conn:
        if clean_username:
            row = conn.execute(
                """
                SELECT 1 FROM private_members
                WHERE user_id = ? OR LOWER(username) = LOWER(?)
                LIMIT 1
                """,
                (user_id, clean_username),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM private_members WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
        return row is not None
