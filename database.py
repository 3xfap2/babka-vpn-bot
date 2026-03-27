import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          INTEGER PRIMARY KEY,
                username         TEXT,
                first_name       TEXT,
                sub_type         TEXT DEFAULT NULL,
                sub_end          TEXT DEFAULT NULL,
                trial_used       INTEGER DEFAULT 0,
                vpn_key          TEXT DEFAULT NULL,
                expiry_notified  INTEGER DEFAULT 0,
                referrer_id      INTEGER DEFAULT NULL,
                pending_ref_days INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migrations for existing DB
        for col, definition in [
            ("expiry_notified",  "INTEGER DEFAULT 0"),
            ("first_name",       "TEXT"),
            ("referrer_id",      "INTEGER DEFAULT NULL"),
            ("pending_ref_days", "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                await db.commit()
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT UNIQUE NOT NULL,
                key_type    TEXT DEFAULT 'any',
                used        INTEGER DEFAULT 0,
                expired     INTEGER DEFAULT 0,
                assigned_to INTEGER DEFAULT NULL,
                assigned_at TEXT DEFAULT NULL
            )
        """)
        try:
            await db.execute("ALTER TABLE keys ADD COLUMN expired INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

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


async def upsert_user(user_id: int, username: str, first_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await db.commit()


async def set_referrer(user_id: int, referrer_id: int):
    """Set referrer only if user has no referrer yet and isn't referring themselves."""
    if user_id == referrer_id:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET referrer_id = ?
            WHERE user_id = ? AND referrer_id IS NULL
        """, (referrer_id, user_id))
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
    """Assign a key, extending existing subscription if active."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM keys WHERE used = 0 AND expired = 0 AND (key_type = ? OR key_type = 'any') LIMIT 1",
            (key_type,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        key_row = dict(row)
        now = datetime.now()

        # Extend existing subscription or start new one
        async with db.execute("SELECT sub_end, pending_ref_days FROM users WHERE user_id = ?", (user_id,)) as cur:
            user_row = await cur.fetchone()

        base = now
        if user_row and user_row["sub_end"]:
            try:
                existing_end = datetime.fromisoformat(user_row["sub_end"])
                if existing_end > now:
                    base = existing_end  # extend from current end
            except Exception:
                pass

        # Add pending referral days
        pending_days = int(user_row["pending_ref_days"]) if user_row and user_row["pending_ref_days"] else 0
        end = base + timedelta(days=days + pending_days)

        await db.execute(
            "UPDATE keys SET used = 1, assigned_to = ?, assigned_at = ? WHERE id = ?",
            (user_id, now.isoformat(), key_row["id"])
        )
        await db.execute("""
            UPDATE users SET sub_type = ?, sub_end = ?, vpn_key = ?,
                expiry_notified = 0, pending_ref_days = 0
            WHERE user_id = ?
        """, (key_type, end.isoformat(), key_row["key"], user_id))
        await db.commit()
        return key_row["key"]


async def manual_set_key(user_id: int, key: str, sub_type: str, days: int):
    """Manually assign key, extending existing subscription."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT sub_end FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()

        now = datetime.now()
        base = now
        if row and row["sub_end"]:
            try:
                existing = datetime.fromisoformat(row["sub_end"])
                if existing > now:
                    base = existing
            except Exception:
                pass

        end = (base + timedelta(days=days)).isoformat()
        await db.execute("""
            UPDATE users SET sub_type = ?, sub_end = ?, vpn_key = ?, expiry_notified = 0
            WHERE user_id = ?
        """, (sub_type, end, key, user_id))
        await db.commit()


async def add_ref_days(referrer_id: int, days: int):
    """Add referral reward days to referrer's subscription or pending balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT sub_end, pending_ref_days FROM users WHERE user_id = ?", (referrer_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return

        now = datetime.now()
        sub_end = row["sub_end"]
        has_active = sub_end and datetime.fromisoformat(sub_end) > now if sub_end else False

        if has_active:
            # Extend existing subscription
            end_dt = datetime.fromisoformat(sub_end) + timedelta(days=days)
            await db.execute(
                "UPDATE users SET sub_end = ?, expiry_notified = 0 WHERE user_id = ?",
                (end_dt.isoformat(), referrer_id)
            )
        else:
            # Save as pending — will be added on next purchase
            pending = (row["pending_ref_days"] or 0) + days
            await db.execute(
                "UPDATE users SET pending_ref_days = ? WHERE user_id = ?",
                (pending, referrer_id)
            )
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


async def delete_keys(key_type: str | None = None, specific_key: str | None = None) -> int:
    """Delete keys. Returns count deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        if specific_key:
            cur = await db.execute("DELETE FROM keys WHERE key = ?", (specific_key,))
        elif key_type == "all":
            cur = await db.execute("DELETE FROM keys")
        else:
            cur = await db.execute("DELETE FROM keys WHERE key_type = ?", (key_type,))
        count = cur.rowcount
        await db.commit()
    return count


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
        async with db.execute("SELECT COUNT(*) FROM keys WHERE used = 0 AND expired = 0") as c:
            free_keys = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM keys WHERE used = 1") as c:
            used_keys = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM keys WHERE expired = 1") as c:
            expired_keys = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM payments") as c:
            total_payments = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(stars) FROM payments") as c:
            total_stars = (await c.fetchone())[0] or 0
    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "free_keys": free_keys,
        "used_keys": used_keys,
        "expired_keys": expired_keys,
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
    """Returns all keys grouped by type with expiry status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Mark expired keys: key is used but user's sub_end has passed
        await db.execute("""
            UPDATE keys SET expired = 1
            WHERE used = 1 AND expired = 0
              AND assigned_to IN (
                SELECT user_id FROM users
                WHERE sub_end IS NOT NULL AND sub_end < datetime('now')
              )
        """)
        await db.commit()
        async with db.execute("SELECT * FROM keys ORDER BY key_type, used, expired") as cur:
            rows = await cur.fetchall()
    result = {}
    for row in rows:
        r = dict(row)
        kt = r["key_type"]
        result.setdefault(kt, []).append(r)
    return result


async def get_expired_unsent_users() -> list[dict]:
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
            "UPDATE users SET expiry_notified = 1, sub_type = NULL, sub_end = NULL, vpn_key = NULL WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()
