import os


def get_admin_ids() -> set[int]:
    """Parse ADMIN_IDS environment variable into a set of integer Telegram user IDs."""
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def is_admin(user_id: int) -> bool:
    """Return True if user_id has ADMIN privileges."""
    return user_id in get_admin_ids()
