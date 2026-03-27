from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from datetime import datetime
from config import ADMIN_IDS, WEEK_DAYS, MONTH_DAYS
from database import (
    add_keys, get_stats, get_recent_users,
    manual_set_key, get_all_user_ids, get_user_ids_by_sub, get_keys_info, get_user, delete_keys,
    clear_user_key
)

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🛠 <b>Админ панель БАБКА VPN</b>\n\n"
        "📊 <b>Статистика:</b>\n"
        "/stats — общая статистика\n"
        "/users — последние 30 пользователей\n"
        "/keys — все ключи со статусом\n\n"
        "🔑 <b>Управление ключами:</b>\n"
        "/addkey week|month|free — добавить ключи\n"
        "/delkey &lt;ключ&gt; — удалить конкретный ключ\n"
        "/delkeys week|month|trial|all — удалить все ключи типа\n\n"
        "👤 <b>Пользователи:</b>\n"
        "/givekey &lt;user_id&gt; &lt;ключ&gt; &lt;week|month|trial&gt;\n"
        "/clearkey &lt;user_id&gt; — удалить ключ у пользователя\n\n"
        "📢 <b>Рассылка:</b>\n"
        "/say &lt;текст&gt; — всем\n"
        "/sayactive &lt;текст&gt; — только с активной подпиской\n"
        "/sayinactive &lt;текст&gt; — только без подписки\n",
        parse_mode="HTML"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = await get_stats()
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{s['total_users']}</b>\n"
        f"✅ Активных подписок: <b>{s['active_subs']}</b>\n"
        f"🔑 Свободных ключей: <b>{s['free_keys']}</b>\n"
        f"🔒 Использовано ключей: <b>{s['used_keys']}</b>\n"
        f"❌ Истёкших ключей: <b>{s['expired_keys']}</b>\n"
        f"💳 Платежей: <b>{s['total_payments']}</b>\n"
        f"⭐ Заработано звёзд: <b>{s['total_stars']}</b>\n",
        parse_mode="HTML"
    )


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    users = await get_recent_users(30)
    if not users:
        await message.answer("Нет пользователей")
        return
    lines = []
    for u in users:
        sub = "❌"
        if u.get("sub_end"):
            try:
                end_dt = datetime.fromisoformat(u["sub_end"])
                if end_dt > datetime.now():
                    sub = f"✅ {u['sub_type']} до {end_dt.strftime('%d.%m.%Y')}"
            except Exception:
                pass
        uname = f"@{u['username']}" if u.get("username") else "—"
        lines.append(f"<code>{u['user_id']}</code> {uname} — {sub}")
    await message.answer(
        "👥 <b>Последние пользователи:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML"
    )


@router.message(Command("keys"))
async def cmd_keys(message: Message):
    if not is_admin(message.from_user.id):
        return
    info = await get_keys_info()

    lines = ["🔑 <b>Все ключи в базе:</b>\n"]
    for key_type, label in [
        ("week", "📅 Неделя"),
        ("month", "🗓 Месяц"),
        ("trial", "🎁 Бесплатные"),
        ("any", "🔀 Любые"),
    ]:
        keys = info.get(key_type, [])
        if not keys:
            continue
        free = [k for k in keys if not k["used"] and not k["expired"]]
        used = [k for k in keys if k["used"] and not k["expired"]]
        expired = [k for k in keys if k["expired"]]

        lines.append(
            f"{label}: ✅ <b>{len(free)}</b> свободных / "
            f"🔒 {len(used)} работает / ❌ {len(expired)} истекло"
        )
        for k in free[:10]:
            lines.append(f"  ✅ <code>{k['key']}</code>")
        if len(free) > 10:
            lines.append(f"  ...ещё {len(free) - 10}")
        for k in used[:5]:
            uid = k.get("assigned_to", "?")
            lines.append(f"  🔒 <code>{k['key']}</code> → <code>{uid}</code>")
        if len(used) > 5:
            lines.append(f"  ...ещё {len(used) - 5}")
        for k in expired[:3]:
            lines.append(f"  ❌ <code>{k['key']}</code>")
        if len(expired) > 3:
            lines.append(f"  ...ещё {len(expired) - 3}")
        lines.append("")

    if len(lines) == 1:
        await message.answer("Ключей нет. Добавьте через /addkey1w, /addkey1m или /addkeyfree")
        return

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("addkey"))
async def cmd_addkey(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text[len("/addkey"):].strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    TYPE_MAP = {
        "week": ("week", "📅 <b>Ключи на неделю добавлены</b>"),
        "month": ("month", "🗓 <b>Ключи на месяц добавлены</b>"),
        "free": ("trial", "🎁 <b>Бесплатные ключи добавлены</b>"),
    }

    key_type = label = None
    for alias, (kt, lb) in TYPE_MAP.items():
        if lines and lines[0].lower() == alias:
            key_type, label = kt, lb
            lines = lines[1:]
            break
        if lines and lines[-1].lower() == alias:
            key_type, label = kt, lb
            lines = lines[:-1]
            break

    if not key_type:
        await message.answer(
            "Использование:\n\n"
            "<code>/addkey week\nключ1\nключ2</code>\n\n"
            "Типы: <b>week</b> / <b>month</b> / <b>free</b>",
            parse_mode="HTML"
        )
        return

    if not lines:
        await message.answer("❌ Нет ключей для добавления")
        return

    added, skipped = await add_keys(lines, key_type)
    await message.answer(
        f"{label}\n✅ Добавлено: <b>{added}</b>\n⏭ Пропущено (дубли): <b>{skipped}</b>",
        parse_mode="HTML"
    )


@router.message(Command("delkey"))
async def cmd_delkey(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /delkey &lt;ключ&gt;", parse_mode="HTML")
        return
    key = parts[1].strip()
    count = await delete_keys(specific_key=key)
    if count:
        await message.answer(f"✅ Ключ удалён: <code>{key}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Ключ не найден")


@router.message(Command("delkeys"))
async def cmd_delkeys(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip() not in ("week", "month", "trial", "all"):
        await message.answer(
            "Использование: /delkeys &lt;week|month|trial|all&gt;\n\n"
            "⚠️ Удаляет ВСЕ ключи указанного типа",
            parse_mode="HTML"
        )
        return
    key_type = parts[1].strip()
    count = await delete_keys(key_type=key_type)
    label = {"week": "неделю", "month": "месяц", "trial": "бесплатные", "all": "все"}.get(key_type, key_type)
    await message.answer(f"✅ Удалено ключей ({label}): <b>{count}</b>", parse_mode="HTML")


@router.message(Command("givekey"))
async def cmd_givekey(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "Использование: /givekey &lt;user_id&gt; &lt;ключ&gt; &lt;week|month|trial&gt;",
            parse_mode="HTML"
        )
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    key = parts[2]
    sub_type = parts[3]
    days_map = {"week": WEEK_DAYS, "month": MONTH_DAYS, "trial": 7}
    days = days_map.get(sub_type, WEEK_DAYS)
    await manual_set_key(target_id, key, sub_type, days)
    await message.answer(f"✅ Ключ выдан пользователю <code>{target_id}</code>", parse_mode="HTML")
    try:
        from handlers.start import build_webapp_url
        user_data = await get_user(target_id)
        webapp_url = await build_webapp_url(user_data, bot, target_id)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(
                text="🔑 Открыть БАБКА VPN",
                web_app=WebAppInfo(url=webapp_url)
            )]],
            resize_keyboard=True
        )
        await bot.send_message(
            target_id,
            f"🎉 <b>Администратор выдал вам подписку!</b>\n\n"
            f"Тариф: <b>{sub_type}</b>\n"
            f"VPN ключ: <code>{key}</code>\n\n"
            "Откройте приложение — всё уже обновилось 👇",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось отправить уведомление: {e}")


@router.message(Command("clearkey"))
async def cmd_clearkey(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /clearkey &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        target_id = int(parts[1].strip())
    except ValueError:
        await message.answer("❌ Неверный user_id")
        return
    user = await get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    old_key = user.get("vpn_key") or "—"
    found = await clear_user_key(target_id)
    if found:
        await message.answer(
            f"✅ Ключ удалён у пользователя <code>{target_id}</code>\n"
            f"Был ключ: <code>{old_key}</code>",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                target_id,
                "⚠️ <b>Ваша подписка была отозвана администратором.</b>\n\n"
                "Если это ошибка — обратитесь в поддержку.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ Пользователь не найден")


async def _do_broadcast(message: Message, bot: Bot, user_ids: list, text: str, label: str):
    sent, failed = 0, 0
    status_msg = await message.answer(f"📤 {label}: отправляю... (0/{len(user_ids)})")
    for i, uid in enumerate(user_ids):
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(f"📤 {label}: отправляю... ({i + 1}/{len(user_ids)})")
            except Exception:
                pass
    await status_msg.edit_text(
        f"✅ Рассылка завершена ({label})\n✓ Отправлено: {sent}\n✗ Ошибок: {failed}"
    )


@router.message(Command("broadcast", "say"))
async def cmd_broadcast(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    cmd = message.text.split()[0].lstrip("/")
    text = message.text[len(f"/{cmd}"):].strip()
    if not text:
        await message.answer("Использование: /say &lt;текст&gt;", parse_mode="HTML")
        return
    user_ids = await get_all_user_ids()
    await _do_broadcast(message, bot, user_ids, text, "Все пользователи")


@router.message(Command("sayactive"))
async def cmd_sayactive(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    text = message.text[len("/sayactive"):].strip()
    if not text:
        await message.answer("Использование: /sayactive &lt;текст&gt;", parse_mode="HTML")
        return
    user_ids = await get_user_ids_by_sub(active=True)
    if not user_ids:
        await message.answer("Нет пользователей с активной подпиской")
        return
    await _do_broadcast(message, bot, user_ids, text, f"Активные подписчики ({len(user_ids)})")


@router.message(Command("sayinactive"))
async def cmd_sayinactive(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    text = message.text[len("/sayinactive"):].strip()
    if not text:
        await message.answer("Использование: /sayinactive &lt;текст&gt;", parse_mode="HTML")
        return
    user_ids = await get_user_ids_by_sub(active=False)
    if not user_ids:
        await message.answer("Нет пользователей без подписки")
        return
    await _do_broadcast(message, bot, user_ids, text, f"Без подписки ({len(user_ids)})")
