import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          INTEGER PRIMARY KEY,
                username         TEXT,
                sub_type         TEXT DEFAULT NULL,
                sub_end          TEXT DEFAULT NULL,
                trial_used       INTEGER DEFAULT 0,
                vpn_key          TEXT DEFAULT NULL,
                expiry_notified  INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migration: add expiry_notified if missing (existing DB)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN expiry_notified INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT UNIQUE NOT NULL,
                key_type    TEXT DEFAULT 'any',
                used        INTEGER DEFAULT 0,
                assigned_to INTEGER DEFAULT NULL,
                assigned_at TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                pay_type    TEXT,
                stars       INTEGER,
                tg_pay_id   TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        await db.commit()


def _is_active(sub_end: str | None) -> bool:
    if not sub_end:
        return False
    try:
        return datetime.fromisoformat(sub_end) > datetime.now()
    except Exception:
        return False


async def subscription_active(user_id: int) -> bool:
    user = await get_user(user_id)
    if not user:
        return False
    return _is_active(user.get("sub_end"))


async def assign_key(user_id: int, key_type: str, days: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM keys WHERE used = 0 AND (key_type = ? OR key_type = 'any') LIMIT 1",
            (key_type,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        key_row = dict(row)
        now = datetime.now()
        end = now + timedelta(days=days)
        await db.execute(
            "UPDATE keys SET used = 1, assigned_to = ?, assigned_at = ? WHERE id = ?",
            (user_id, now.isoformat(), key_row["id"])
        )
        await db.execute("""
            UPDATE users SET sub_type = ?, sub_end = ?, vpn_key = ?, expiry_notified = 0
            WHERE user_id = ?
        """, (key_type, end.isoformat(), key_row["key"], user_id))
        await db.commit()
        return key_row["key"]


async def manual_set_key(user_id: int, key: str, sub_type: str, days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        end = (datetime.now() + timedelta(days=days)).isoformat()
        await db.execute("""
            UPDATE users SET sub_type = ?, sub_end = ?, vpn_key = ? WHERE user_id = ?
        """, (sub_type, end, key, user_id))
        await db.commit()


async def add_keys(keys: list[str], key_type: str = "any") -> tuple[int, int]:
    added, skipped = 0, 0
    async with aiosqlite.connect(DB_PATH) as db:
        for k in keys:
            k = k.strip()
            if not k:
                continue
            try:
                await db.execute(
                    "INSERT INTO keys (key, key_type) VALUES (?, ?)", (k, key_type)
                )
                added += 1
            except Exception:
                skipped += 1
        await db.commit()
    return added, skipped


async def mark_trial_used(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET trial_used = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def save_payment(user_id: int, pay_type: str, stars: int, tg_pay_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, pay_type, stars, tg_pay_id) VALUES (?,?,?,?)",
            (user_id, pay_type, stars, tg_pay_id)
        )
        await db.commit()


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE sub_end > datetime('now')"
        ) as c:
            active_subs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM keys WHERE used = 0") as c:
            free_keys = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM keys WHERE used = 1") as c:
            used_keys = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM payments") as c:
            total_payments = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(stars) FROM payments") as c:
            total_stars = (await c.fetchone())[0] or 0
    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "free_keys": free_keys,
        "used_keys": used_keys,
        "total_payments": total_payments,
        "total_stars": total_stars,
    }


async def get_recent_users(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_keys_info() -> dict:
    """Returns all keys grouped by type for admin /keys command."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM keys ORDER BY key_type, used") as cur:
            rows = await cur.fetchall()
    result = {}
    for row in rows:
        r = dict(row)
        kt = r["key_type"]
        result.setdefault(kt, []).append(r)
    return result


async def get_expired_unsent_users() -> list[dict]:
    """Returns users whose subscription just expired and haven't been notified."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT user_id, username, sub_type, sub_end
            FROM users
            WHERE sub_end IS NOT NULL
              AND sub_end < datetime('now')
              AND sub_type IS NOT NULL
              AND expiry_notified = 0
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def mark_expiry_notified(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET expiry_notified = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()
