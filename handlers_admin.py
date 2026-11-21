import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db
from config import is_admin
from handlers_user import create_private_invite_link

# Conversation states
(
    ADD_TITLE,
    ADD_DESC,
    ADD_PRICE,
    ADD_DELIVERY,
    EDIT_BUILD_VALUE,
    EDIT_SETTING_VALUE,
    ADD_SUB_CHAT,
    ADD_SUB_LINK,
    GRANT_PB_USER,
) = range(9)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Управление СБОРКАМИ", callback_data="admin:builds")],
            [InlineKeyboardButton("🔒 Настроить PRIVATE BLOCK", callback_data="admin:private")],
            [InlineKeyboardButton("📢 Обязательная подписка", callback_data="admin:sub_channels")],
            [
                InlineKeyboardButton("📜 Список покупок", callback_data="admin:purchases"),
                InlineKeyboardButton("👥 Участники PRIVATE", callback_data="admin:pb_members"),
            ],
            [
                InlineKeyboardButton("👋 Приветствие", callback_data="admin:greeting"),
                InlineKeyboardButton("📊 Статистика", callback_data="admin:stats"),
            ],
            [InlineKeyboardButton("⬅️ В главное меню", callback_data="menu:main")],
        ]
    )


def cancel_keyboard(back_cb: str = "admin:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data=f"admin:cancel:{back_cb}")]]
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Open the admin panel via /admin."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ <b>Админ-панель</b>\n\nВыберите раздел:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


async def cb_admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Open the admin panel via callback button."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    await query.edit_message_text(
        "⚙️ <b>Админ-панель</b>\n\nВыберите раздел:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


async def cb_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display total sales count and Stars revenue."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    stats = db.get_stats()
    text = (
        "📊 <b>Статистика продаж</b>\n\n"
        f"🛒 Всего покупок: <b>{stats['count']}</b>\n"
        f"⭐ Заработано звёзд: <b>{stats['total_stars']} ⭐</b>"
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")]]
        ),
    )


async def cb_admin_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display list of recent purchases."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    purchases = db.list_purchases(limit=30)
    if not purchases:
        text = "📜 <b>Список покупок</b>\n\nПокупок пока не было."
    else:
        lines = []
        for p in purchases:
            who = html.escape(p["username"] or str(p["user_id"]))
            title = html.escape(p["item_title"])
            date_str = str(p["created_at"])[:16]
            lines.append(f"• {who} — <b>{title}</b> ({p['amount']} ⭐) <i>[{date_str}]</i>")
        text = "📜 <b>Последние покупки (до 30):</b>\n\n" + "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")]]
        ),
    )


async def cb_admin_pb_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display list of Private Block members (paid or admin-granted)."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    members = db.list_private_members(limit=50)
    if not members:
        text = "👥 <b>Участники PRIVATE BLOCK</b>\n\nСписок пока пуст."
    else:
        lines = []
        for m in members:
            uname = m["username"]
            who = f"@{html.escape(uname)}" if uname and not uname.isdigit() else f"<code>{m['user_id'] or uname}</code>"
            badge = "⭐ оплата" if m["source"] == "stars" else "🎁 админ"
            date_str = str(m["created_at"])[:16]
            lines.append(f"• {who} — {badge} <i>[{date_str}]</i>")
        text = "👥 <b>Участники PRIVATE BLOCK (до 50):</b>\n\n" + "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")]]
        ),
    )


# ---------------------------------------------------------------------------
# Builds Management
# ---------------------------------------------------------------------------

async def cb_admin_builds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show builds management menu."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    builds = db.list_builds(active_only=True)
    kb = [[InlineKeyboardButton("➕ Добавить сборку", callback_data="admin:add_build")]]
    for b in builds:
        price_label = "Бесплатно" if b["price"] == 0 else f"{b['price']} ⭐"
        kb.append(
            [
                InlineKeyboardButton(
                    f"✏️ {b['title']} ({price_label})",
                    callback_data=f"admin:edit_build:{b['id']}",
                )
            ]
        )
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")])

    await query.edit_message_text(
        "📦 <b>Управление СБОРКАМИ</b>\n\nДобавьте новую сборку или выберите существующую для редактирования:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_admin_edit_build_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show edit/delete options for a specific build."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    build_id = int(query.data.split(":")[2])
    build = db.get_build(build_id)
    if not build:
        await query.edit_message_text(
            "❌ Сборка не найдена.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:builds")]]
            ),
        )
        return

    delivery_info = "Файл прикреплён" if build["delivery_file_id"] else (
        build["delivery_text"][:80] + ("..." if len(build["delivery_text"]) > 80 else "")
        if build["delivery_text"]
        else "Не задано"
    )
    text = (
        f"✏️ <b>Редактирование сборки</b>\n\n"
        f"<b>Название:</b> {html.escape(build['title'])}\n"
        f"<b>Цена:</b> {build['price']} ⭐\n"
        f"<b>Описание:</b> {html.escape(build['description'])}\n"
        f"<b>Выдача:</b> {html.escape(delivery_info)}"
    )
    kb = [
        [
            InlineKeyboardButton("✏️ Название", callback_data=f"admin:ef:{build_id}:title"),
            InlineKeyboardButton("💰 Цена", callback_data=f"admin:ef:{build_id}:price"),
        ],
        [
            InlineKeyboardButton("📝 Описание", callback_data=f"admin:ef:{build_id}:description"),
            InlineKeyboardButton("🎁 Выдача", callback_data=f"admin:ef:{build_id}:delivery"),
        ],
        [InlineKeyboardButton("🗑 Удалить сборку", callback_data=f"admin:del_build:{build_id}")],
        [InlineKeyboardButton("⬅️ К списку сборок", callback_data="admin:builds")],
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_admin_delete_build(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Soft-delete a build and return to builds list."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    build_id = int(query.data.split(":")[2])
    db.delete_build(build_id)
    await query.answer("🗑 Сборка удалена", show_alert=True)
    await cb_admin_builds(update, context)


# --- Add Build Conversation ---

async def cb_add_build_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    context.user_data["new_build"] = {}
    await query.edit_message_text(
        "➕ <b>Новая сборка (шаг 1/4)</b>\n\nВведите <b>название</b> сборки:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:builds"),
    )
    return ADD_TITLE


async def msg_add_build_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_build"]["title"] = update.message.text.strip()
    await update.message.reply_text(
        "➕ <b>Новая сборка (шаг 2/4)</b>\n\nВведите <b>описание</b> сборки:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:builds"),
    )
    return ADD_DESC


async def msg_add_build_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_build"]["description"] = update.message.text.strip()
    await update.message.reply_text(
        "➕ <b>Новая сборка (шаг 3/4)</b>\n\nВведите <b>цену в звёздах ⭐</b> (целое число, например <code>50</code>, или <code>0</code> для бесплатной сборки):",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:builds"),
    )
    return ADD_PRICE


async def msg_add_build_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if not raw.isdigit() or int(raw) < 0:
        await update.message.reply_text(
            "❗ Введите целое число ≥ 0 (например, <code>50</code> или <code>0</code> для бесплатной):",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard("admin:builds"),
        )
        return ADD_PRICE

    context.user_data["new_build"]["price"] = int(raw)
    await update.message.reply_text(
        "➕ <b>Новая сборка (шаг 4/4)</b>\n\n"
        "Отправьте то, что получит покупатель после оплаты:\n"
        "• <b>текст / ссылку</b>, ИЛИ\n"
        "• <b>файл (документ / архив)</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:builds"),
    )
    return ADD_DELIVERY


async def msg_add_build_delivery(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get("new_build", {})
    delivery_text = ""
    delivery_file_id = ""

    if update.message.document:
        delivery_file_id = update.message.document.file_id
        delivery_text = (update.message.caption or "").strip()
    elif update.message.text:
        delivery_text = update.message.text.strip()
    else:
        await update.message.reply_text(
            "❗ Отправьте текст/ссылку или файл-документ.",
            reply_markup=cancel_keyboard("admin:builds"),
        )
        return ADD_DELIVERY

    build_id = db.add_build(
        title=data["title"],
        description=data["description"],
        price=data["price"],
        delivery_text=delivery_text,
        delivery_file_id=delivery_file_id,
    )
    context.user_data.pop("new_build", None)

    await update.message.reply_text(
        f"✅ Сборка <b>{html.escape(data['title'])}</b> (#{build_id}) за <b>{data['price']} ⭐</b> добавлена в каталог!",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


# --- Edit Build Field Conversation ---

async def cb_edit_build_field(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    _, _, build_id_str, field = query.data.split(":")
    build_id = int(build_id_str)
    context.user_data["edit_build"] = {"id": build_id, "field": field}

    prompts = {
        "title": "Введите новое <b>название</b> сборки:",
        "description": "Введите новое <b>описание</b> сборки:",
        "price": "Введите новую <b>цену в звёздах ⭐</b> (целое число):",
        "delivery": "Отправьте новый <b>текст/ссылку</b> или <b>файл</b> для выдачи после оплаты:",
    }
    await query.edit_message_text(
        prompts[field],
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(f"admin:edit_build:{build_id}"),
    )
    return EDIT_BUILD_VALUE


async def msg_edit_build_value(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    info = context.user_data.get("edit_build", {})
    build_id = info["id"]
    field = info["field"]

    if field == "price":
        raw = (update.message.text or "").strip()
        if not raw.isdigit() or int(raw) < 0:
            await update.message.reply_text(
                "❗ Введите целое число ≥ 0 (0 = бесплатно):",
                reply_markup=cancel_keyboard(f"admin:edit_build:{build_id}"),
            )
            return EDIT_BUILD_VALUE
        db.update_build_field(build_id, "price", int(raw))
    elif field == "delivery":
        if update.message.document:
            db.update_build_field(
                build_id, "delivery_file_id", update.message.document.file_id
            )
            db.update_build_field(
                build_id, "delivery_text", (update.message.caption or "").strip()
            )
        elif update.message.text:
            db.update_build_field(build_id, "delivery_file_id", "")
            db.update_build_field(
                build_id, "delivery_text", update.message.text.strip()
            )
        else:
            await update.message.reply_text(
                "❗ Отправьте текст или файл-документ.",
                reply_markup=cancel_keyboard(f"admin:edit_build:{build_id}"),
            )
            return EDIT_BUILD_VALUE
    else:
        if not update.message.text:
            await update.message.reply_text(
                "❗ Отправьте текстовое сообщение.",
                reply_markup=cancel_keyboard(f"admin:edit_build:{build_id}"),
            )
            return EDIT_BUILD_VALUE
        db.update_build_field(build_id, field, update.message.text.strip())

    context.user_data.pop("edit_build", None)
    await update.message.reply_text(
        "✅ Изменения сохранены!",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ К сборке", callback_data=f"admin:edit_build:{build_id}"
                    )
                ],
                [InlineKeyboardButton("⚙️ В админ-панель", callback_data="admin:main")],
            ]
        ),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Private Block & Greeting Settings
# ---------------------------------------------------------------------------

async def cb_admin_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Private Block settings menu."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    price = db.get_setting("private_block_price", "100")
    discord_link = db.get_setting("private_channel_link") or "Не задана"
    channel_id = db.get_setting("private_channel_id") or "Не задан"

    text = (
        "🔒 <b>Настройки PRIVATE BLOCK</b>\n\n"
        f"💰 <b>Цена:</b> {price} ⭐\n"
        f"🔗 <b>Ссылка на ДС сервер:</b> {html.escape(discord_link)}\n"
        f"🆔 <b>ID ТГ-канала (если нужен вместо ДС):</b> <code>{html.escape(channel_id)}</code>\n\n"
        "<i>После оплаты или выдачи по @username бот отправит пользователю ссылку на Discord-сервер.</i>"
    )
    kb = [
        [
            InlineKeyboardButton("💰 Изменить цену", callback_data="admin:set:private_block_price"),
            InlineKeyboardButton("📝 Описание", callback_data="admin:set:private_block_description"),
        ],
        [
            InlineKeyboardButton("🔗 Ссылка на ДС сервер", callback_data="admin:set:private_channel_link"),
            InlineKeyboardButton("🆔 ID ТГ-канала", callback_data="admin:set:private_channel_id"),
        ],
        [InlineKeyboardButton("🎁 Выдать доступ по @username", callback_data="admin:grant_pb")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")],
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_admin_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start editing greeting text."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    context.user_data["edit_setting"] = "greeting_text"
    current = db.get_setting("greeting_text")
    await query.edit_message_text(
        f"👋 <b>Текущее приветствие:</b>\n\n{current}\n\n"
        "Отправьте новый текст приветствия:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:main"),
    )
    return EDIT_SETTING_VALUE


async def cb_admin_set_setting(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Start editing a Private Block setting."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    key = query.data.split(":")[2]
    context.user_data["edit_setting"] = key

    prompts = {
        "private_block_price": "Введите новую <b>цену PRIVATE BLOCK в звёздах ⭐</b> (целое число):",
        "private_block_description": "Введите новое <b>описание</b> для PRIVATE BLOCK:",
        "private_channel_id": (
            "Отправьте <b>ID приватного канала</b> (например <code>-1001234567890</code>)\n"
            "или просто <b>перешлите любое сообщение</b> из этого канала сюда:"
        ),
        "private_channel_link": "Отправьте <b>ссылку на Discord-сервер</b> (например <code>https://discord.gg/...</code>):",
    }
    await query.edit_message_text(
        prompts[key],
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:private"),
    )
    return EDIT_SETTING_VALUE


async def msg_edit_setting_value(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    key = context.user_data.get("edit_setting")
    back_cb = "admin:main" if key == "greeting_text" else "admin:private"

    if key == "private_block_price":
        raw = (update.message.text or "").strip()
        if not raw.isdigit() or int(raw) <= 0:
            await update.message.reply_text(
                "❗ Введите целое положительное число:",
                reply_markup=cancel_keyboard(back_cb),
            )
            return EDIT_SETTING_VALUE
        value = raw
    elif key == "private_channel_id":
        # Allow forwarding a message from the channel to auto-detect its ID
        if update.message.forward_origin and hasattr(
            update.message.forward_origin, "chat"
        ):
            value = str(update.message.forward_origin.chat.id)
        elif update.message.text:
            value = update.message.text.strip()
        else:
            await update.message.reply_text(
                "❗ Отправьте ID канала (например <code>-100...</code>) или перешлите пост из канала.",
                parse_mode=ParseMode.HTML,
                reply_markup=cancel_keyboard(back_cb),
            )
            return EDIT_SETTING_VALUE
    else:
        if not update.message.text:
            await update.message.reply_text(
                "❗ Отправьте текстовое сообщение.",
                reply_markup=cancel_keyboard(back_cb),
            )
            return EDIT_SETTING_VALUE
        value = update.message.text.strip()

    db.set_setting(key, value)
    context.user_data.pop("edit_setting", None)

    await update.message.reply_text(
        f"✅ Настройка сохранена!\nЗначение: <code>{html.escape(value)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)]]
        ),
    )
    return ConversationHandler.END


async def cb_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any active admin input conversation."""
    query = update.callback_query
    await query.answer("Отменено")
    context.user_data.pop("new_build", None)
    context.user_data.pop("edit_build", None)
    context.user_data.pop("edit_setting", None)
    context.user_data.pop("new_sub_ch", None)

    target = query.data.replace("admin:cancel:", "", 1)
    await query.edit_message_text(
        "❌ Действие отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data=target)]]
        ),
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_build", None)
    context.user_data.pop("edit_build", None)
    context.user_data.pop("edit_setting", None)
    context.user_data.pop("new_sub_ch", None)
    await update.message.reply_text("❌ Действие отменено.", reply_markup=admin_main_keyboard())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Mandatory Subscription Channels
# ---------------------------------------------------------------------------

async def cb_admin_sub_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show mandatory subscription channels management menu."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()

    channels = db.list_required_channels()
    if channels:
        lines = [
            f"• <b>{html.escape(ch['title'])}</b> (<code>{html.escape(ch['chat_id'])}</code>)"
            for ch in channels
        ]
        list_text = "\n".join(lines)
    else:
        list_text = "<i>Список пуст — обязательная подписка отключена.</i>"

    text = (
        "📢 <b>Обязательная подписка на каналы</b>\n\n"
        f"{list_text}\n\n"
        "<i>Важно: бот должен быть администратором в добавленном канале, "
        "чтобы проверять подписку пользователей.</i>"
    )
    kb = [[InlineKeyboardButton("➕ Добавить канал", callback_data="admin:add_sub_ch")]]
    for ch in channels:
        kb.append(
            [
                InlineKeyboardButton(
                    f"🗑 Удалить: {ch['title']}",
                    callback_data=f"admin:del_sub_ch:{ch['id']}",
                )
            ]
        )
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin:main")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_admin_del_sub_channel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Delete a mandatory subscription channel."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    row_id = int(query.data.split(":")[2])
    db.delete_required_channel(row_id)
    await query.answer("🗑 Канал удалён", show_alert=True)
    await cb_admin_sub_channels(update, context)


async def cb_add_sub_channel_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    context.user_data["new_sub_ch"] = {}
    await query.edit_message_text(
        "📢 <b>Добавление канала (шаг 1/2)</b>\n\n"
        "<b>Перешлите любое сообщение</b> из нужного канала сюда,\n"
        "или отправьте его <code>@username</code> / ID (например <code>-1001234567890</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:sub_channels"),
    )
    return ADD_SUB_CHAT


async def msg_add_sub_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = ""
    title = ""
    auto_link = ""

    if update.message.forward_origin and hasattr(update.message.forward_origin, "chat"):
        chat = update.message.forward_origin.chat
        chat_id = str(chat.id)
        title = chat.title or chat_id
        if getattr(chat, "username", None):
            auto_link = f"https://t.me/{chat.username}"
    elif update.message.text:
        raw = update.message.text.strip()
        chat_ref: int | str = int(raw) if raw.lstrip("-").isdigit() else raw
        try:
            chat = await context.bot.get_chat(chat_ref)
            chat_id = str(chat.id)
            title = chat.title or raw
            if getattr(chat, "username", None):
                auto_link = f"https://t.me/{chat.username}"
        except Exception:
            chat_id = raw
            title = raw
            if raw.startswith("@"):
                auto_link = f"https://t.me/{raw[1:]}"
    else:
        await update.message.reply_text(
            "❗ Перешлите сообщение из канала или отправьте его @username / ID.",
            reply_markup=cancel_keyboard("admin:sub_channels"),
        )
        return ADD_SUB_CHAT

    context.user_data["new_sub_ch"] = {"chat_id": chat_id, "title": title}
    hint = f"\n\nПодсказка (найдена ссылка): <code>{auto_link}</code>" if auto_link else ""
    await update.message.reply_text(
        f"📢 <b>Добавление канала (шаг 2/2)</b>\n\n"
        f"Канал: <b>{html.escape(title)}</b> (<code>{html.escape(chat_id)}</code>)\n"
        f"Отправьте <b>ссылку для подписки</b> (например <code>https://t.me/+...</code> или <code>https://t.me/channel</code>):{hint}",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:sub_channels"),
    )
    return ADD_SUB_LINK


async def msg_add_sub_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text:
        await update.message.reply_text(
            "❗ Отправьте текстовую ссылку (например <code>https://t.me/...</code>).",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard("admin:sub_channels"),
        )
        return ADD_SUB_LINK

    link = update.message.text.strip()
    if link.startswith("@"):
        link = f"https://t.me/{link[1:]}"

    info = context.user_data.pop("new_sub_ch", {})
    db.add_required_channel(
        chat_id=info["chat_id"],
        title=info["title"],
        invite_link=link,
    )
    await update.message.reply_text(
        f"✅ Канал <b>{html.escape(info['title'])}</b> добавлен в обязательную подписку!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📢 К списку каналов", callback_data="admin:sub_channels")],
                [InlineKeyboardButton("⚙️ В админ-панель", callback_data="admin:main")],
            ]
        ),
    )
    return ConversationHandler.END


async def cb_grant_pb_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start granting Private Block access by @username or user_id."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    await query.edit_message_text(
        "🎁 <b>Выдача PRIVATE BLOCK</b>\n\n"
        "Отправьте <code>@username</code> (или числовой ID) пользователя, "
        "которому нужно выдать доступ в канал:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard("admin:private"),
    )
    return GRANT_PB_USER


async def msg_grant_pb_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Look up user, create 1-time invite link, and deliver it."""
    if not update.message.text:
        await update.message.reply_text(
            "❗ Отправьте @username или числовой ID пользователя.",
            reply_markup=cancel_keyboard("admin:private"),
        )
        return GRANT_PB_USER

    raw_target = update.message.text.strip()
    clean_name = raw_target.lstrip("@")
    invite_url = await create_private_invite_link(context.bot, f"Admin @{clean_name}")

    if not invite_url:
        await update.message.reply_text(
            "❌ Не удалось выдать доступ: сначала задайте <b>🔗 Ссылка на ДС сервер</b> "
            "в настройках PRIVATE BLOCK.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:private")]]
            ),
        )
        return ConversationHandler.END

    user_row = db.find_user_by_username_or_id(raw_target)
    db.add_private_member(
        user_id=user_row["user_id"] if user_row else None,
        username=clean_name,
        source="admin",
    )
    sent_dm = False
    if user_row:
        try:
            await context.bot.send_message(
                chat_id=user_row["user_id"],
                text=(
                    "🎁 <b>Вам выдан доступ в PRIVATE BLOCK!</b>\n\n"
                    f"Ссылка на Discord-сервер:\n👉 {invite_url}"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔓 Перейти на Discord-сервер", url=invite_url)]]
                ),
            )
            sent_dm = True
        except TelegramError:
            sent_dm = False

    if sent_dm:
        msg_text = (
            f"✅ Доступ в <b>PRIVATE BLOCK</b> выдан пользователю <b>{html.escape(raw_target)}</b> "
            f"и отправлен ему в личные сообщения!\n\n"
            f"🔗 Ссылка: {invite_url}"
        )
    else:
        msg_text = (
            f"✅ Пользователь <b>{html.escape(raw_target)}</b> добавлен в список участников, "
            f"но бот не смог написать ему в ЛС (он ещё не запускал бота или заблокировал его).\n\n"
            f"Отправьте ссылку вручную:\n👉 {invite_url}"
        )

    await update.message.reply_text(
        msg_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="admin:private")]]
        ),
    )
    return ConversationHandler.END


def build_admin_conversation() -> ConversationHandler:
    """Create the ConversationHandler for all admin input flows."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_add_build_start, pattern=r"^admin:add_build$"),
            CallbackQueryHandler(cb_edit_build_field, pattern=r"^admin:ef:\d+:(title|description|price|delivery)$"),
            CallbackQueryHandler(cb_admin_greeting, pattern=r"^admin:greeting$"),
            CallbackQueryHandler(cb_admin_set_setting, pattern=r"^admin:set:(private_block_price|private_block_description|private_channel_id|private_channel_link)$"),
            CallbackQueryHandler(cb_add_sub_channel_start, pattern=r"^admin:add_sub_ch$"),
            CallbackQueryHandler(cb_grant_pb_start, pattern=r"^admin:grant_pb$"),
        ],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_add_build_title)],
            ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_add_build_desc)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_add_build_price)],
            ADD_DELIVERY: [
                MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, msg_add_build_delivery)
            ],
            EDIT_BUILD_VALUE: [
                MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, msg_edit_build_value)
            ],
            EDIT_SETTING_VALUE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, msg_edit_setting_value)
            ],
            ADD_SUB_CHAT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, msg_add_sub_chat)
            ],
            ADD_SUB_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_add_sub_link)
            ],
            GRANT_PB_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_grant_pb_user)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cb_admin_cancel, pattern=r"^admin:cancel:"),
            CommandHandler("cancel", cmd_cancel),
        ],
        per_message=False,
    )
