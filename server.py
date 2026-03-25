import hmac
import hashlib
import json
import os
from urllib.parse import parse_qsl
from aiohttp import web
from config import BOT_TOKEN, WEB_PORT, WEEK_PRICE_STARS, MONTH_PRICE_STARS
from database import get_user, upsert_user

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")


def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData and return user dict or None."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=False))
        check_hash = parsed.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, check_hash):
            return None
        user_str = parsed.get("user", "{}")
        return json.loads(user_str)
    except Exception:
        return None


async def api_user(request: web.Request) -> web.Response:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    tg_user = validate_init_data(init_data)
    if not tg_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    user_id = tg_user.get("id")
    username = tg_user.get("username", "")
    await upsert_user(user_id, username)
    user = await get_user(user_id)

    from datetime import datetime
    sub_active = False
    sub_end_str = None
    if user and user.get("sub_end"):
        try:
            end_dt = datetime.fromisoformat(user["sub_end"])
            if end_dt > datetime.now():
                sub_active = True
                sub_end_str = end_dt.strftime("%d.%m.%Y")
        except Exception:
            pass

    return web.json_response({
        "user_id": user_id,
        "username": username,
        "sub_active": sub_active,
        "sub_type": user.get("sub_type") if user else None,
        "sub_end": sub_end_str,
        "vpn_key": user.get("vpn_key") if (user and sub_active) else None,
        "trial_used": bool(user.get("trial_used")) if user else False,
        "week_price": WEEK_PRICE_STARS,
        "month_price": MONTH_PRICE_STARS,
    })


async def serve_index(request: web.Request) -> web.Response:
    index_path = os.path.join(WEBAPP_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    return web.Response(text=content, content_type="text/html")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/api/user", api_user)
    app.router.add_get("/", serve_index)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEB_PORT)
    await site.start()
    print(f"Web server running on port {WEB_PORT}")
    return runner
