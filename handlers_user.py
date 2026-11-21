import html
import logging
from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import database as db
from config import is_admin

logger = logging.getLogger(__name__)


async def get_missing_channels(bot, user_id: int) -> list[dict[str, Any]]:
    """Return list of required channels the user has not joined yet."""
    if is_admin(user_id):
        return []

    channels = db.list_required_channels()
    missing: list[dict[str, Any]] = []
    for ch in channels:
        chat_ref: int | str = int(ch["chat_id"]) if ch["chat_id"].lstrip("-").isdigit() else ch["chat_id"]
        try:
            member = await bot.get_chat_member(chat_id=chat_ref, user_id=user_id)
            is_member = member.status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ) or (
                member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False)
            )
            if not is_member:
                missing.append(ch)
        except TelegramError as exc:
            logger.warning("Failed to check membership in %s: %s", ch["chat_id"], exc)
    return missing


def build_subscription_prompt(missing: list[dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    """Build text and keyboard asking user to subscribe to required channels."""
    text = (
        "🔒 <b>Для использования бота подпишитесь на обязательные каналы:</b>\n\n"
        "После подписки нажмите кнопку <b>«✅ Проверить подписку»</b>."
    )
    kb = [
        [InlineKeyboardButton(f"📢 {ch['title']}", url=ch["invite_link"])]
        for ch in missing
    ]
    kb.append([InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")])
    return text, InlineKeyboardMarkup(kb)


async def ensure_subscribed_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check subscription on a message update; reply with prompt if not subscribed."""
    missing = await get_missing_channels(context.bot, update.effective_user.id)
    if not missing:
        return True
    text, kb = build_subscription_prompt(missing)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return False


async def ensure_subscribed_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check subscription on a callback query; edit message with prompt if not subscribed."""
    query = update.callback_query
    missing = await get_missing_channels(context.bot, query.from_user.id)
    if not missing:
        return True
    await query.answer("🔒 Сначала подпишитесь на каналы!", show_alert=True)
    text, kb = build_subscription_prompt(missing)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return False


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard with 3 user buttons (plus Admin if authorized)."""
    rows = [
        [InlineKeyboardButton("📦 СБОРКИ", callback_data="menu:builds")],
        [InlineKeyboardButton("🔒 PRIVATE BLOCK", callback_data="menu:private")],
        [InlineKeyboardButton("💬 ПОДДЕРЖКА", callback_data="menu:support")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin:main")])
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command: record user, check subscription, then show greeting and main 3-button menu."""
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.first_name or "")
    if not await ensure_subscribed_message(update, context):
        return
    greeting = db.get_setting("greeting_text")
    await update.message.reply_text(
        greeting,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id),
    )


async def cb_check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-check mandatory channel subscriptions when user clicks Check."""
    query = update.callback_query
    user = query.from_user
    db.upsert_user(user.id, user.username or "", user.first_name or "")
    missing = await get_missing_channels(context.bot, user.id)
    if missing:
        await query.answer("❌ Вы подписались не на все каналы!", show_alert=True)
        text, kb = build_subscription_prompt(missing)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            pass
        return

    await query.answer("✅ Подписка подтверждена!")
    greeting = db.get_setting("greeting_text")
    await query.edit_message_text(
        greeting,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(query.from_user.id),
    )


async def cb_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main menu."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()
    greeting = db.get_setting("greeting_text")
    await query.edit_message_text(
        greeting,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(query.from_user.id),
    )


async def cb_builds_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the catalog of builds with prices."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()
    builds = db.list_builds(active_only=True)

    if not builds:
        text = "📦 <b>Каталог сборок</b>\n\nПока здесь нет доступных сборок."
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]
    else:
        text = "📦 <b>Каталог сборок</b>\n\nВыберите сборку для просмотра и покупки:"
        kb = [
            [
                InlineKeyboardButton(
                    f"{b['title']} — Бесплатно 🎁"
                    if b["price"] == 0
                    else f"{b['title']} — {b['price']} ⭐",
                    callback_data=f"build:{b['id']}",
                )
            ]
            for b in builds
        ]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_build_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details and payment button for a specific build."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()
    build_id = int(query.data.split(":")[1])
    build = db.get_build(build_id)

    if not build:
        await query.edit_message_text(
            "❌ Эта сборка больше недоступна.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ К каталогу", callback_data="menu:builds")]]
            ),
        )
        return

    is_free = build["price"] == 0
    price_line = "Бесплатно 🎁" if is_free else f"{build['price']} ⭐"
    action_btn = (
        InlineKeyboardButton("🎁 Получить бесплатно", callback_data=f"free:build:{build['id']}")
        if is_free
        else InlineKeyboardButton(f"💳 Оплатить {build['price']} ⭐", callback_data=f"buy:build:{build['id']}")
    )
    text = (
        f"📦 <b>{html.escape(build['title'])}</b>\n\n"
        f"{html.escape(build['description'])}\n\n"
        f"💎 <b>Цена:</b> {price_line}"
    )
    kb = [
        [action_btn],
        [InlineKeyboardButton("⬅️ Назад к каталогу", callback_data="menu:builds")],
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_free_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deliver a free build (price == 0) immediately."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()

    build_id = int(query.data.split(":")[2])
    build = db.get_build(build_id)
    if not build or build["price"] != 0:
        await query.message.reply_text("❌ Сборка недоступна.")
        return

    delivery_text = build.get("delivery_text", "").strip()
    delivery_file_id = build.get("delivery_file_id", "").strip()

    if delivery_file_id:
        await query.message.reply_document(
            document=delivery_file_id,
            caption=delivery_text or f"Ваша сборка: {build['title']}",
        )
    elif delivery_text:
        await query.message.reply_text(
            f"🎁 <b>{html.escape(build['title'])}</b>\n\n{delivery_text}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    else:
        await query.message.reply_text("Для получения материалов напишите в поддержку: @juarezz")


async def cb_private_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the Private Block menu: Discord link for existing members, or purchase menu."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if db.is_private_member(user.id, user.username or ""):
        invite_url = await create_private_invite_link(context.bot, f"Member {user.id}")
        if invite_url:
            await query.edit_message_text(
                "🔒 <b>PRIVATE BLOCK</b>\n\n"
                "✅ <b>У вас уже есть активный доступ!</b>\n\n"
                f"Ссылка на Discord-сервер:\n👉 {invite_url}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔓 Перейти на Discord-сервер", url=invite_url)],
                        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
                    ]
                ),
            )
            return
        await query.edit_message_text(
            "🔒 <b>PRIVATE BLOCK</b>\n\n"
            "✅ У вас есть доступ, но ссылка на сервер пока не настроена. Напишите @juarezz.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")]]
            ),
        )
        return

    price = int(db.get_setting("private_block_price", "100") or "100")
    description = db.get_setting("private_block_description")
    text = f"{description}\n\n💎 <b>Цена доступа:</b> {price} ⭐"

    kb = [
        [
            InlineKeyboardButton(
                f"💳 Купить доступ ({price} ⭐)",
                callback_data="buy:private",
            )
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the Support menu pointing to @juarezz."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()

    text = (
        "💬 <b>ПОДДЕРЖКА</b>\n\n"
        "По всем вопросам, проблемам с оплатой или предложениям обращайтесь к администратору:\n"
        "👉 @juarezz"
    )
    kb = [
        [InlineKeyboardButton("✉️ Написать @juarezz", url="https://t.me/juarezz")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def cb_buy_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a Telegram Stars (XTR) invoice for a build or Private Block."""
    if not await ensure_subscribed_query(update, context):
        return
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if parts[1] == "build":
        build_id = int(parts[2])
        build = db.get_build(build_id)
        if not build or build["price"] <= 0:
            await query.message.reply_text("❌ Товар недоступен для покупки.")
            return
        title = build["title"][:32]
        description = (build["description"] or "Покупка сборки")[:255]
        payload = f"build:{build_id}"
        price = int(build["price"])
        label = f"Сборка: {title}"
    elif parts[1] == "private":
        price = int(db.get_setting("private_block_price", "100") or "100")
        if price <= 0:
            await query.message.reply_text("❌ Покупка временно недоступна.")
            return
        title = "PRIVATE BLOCK"
        description = "Доступ в закрытый приватный канал (выдача ссылки сразу после оплаты)"
        payload = "private_block"
        label = "Доступ в PRIVATE BLOCK"
    else:
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Empty string is required for Telegram Stars (XTR)
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=price)],
    )


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate Telegram Stars invoice before final charge."""
    query = update.pre_checkout_query
    payload = query.invoice_payload

    if payload.startswith("build:"):
        build_id = int(payload.split(":")[1])
        build = db.get_build(build_id)
        if not build or build["price"] != query.total_amount:
            await query.answer(
                ok=False,
                error_message="Товар изменился или больше не доступен. Попробуйте снова.",
            )
            return
    elif payload == "private_block":
        current_price = int(db.get_setting("private_block_price", "100") or "100")
        if current_price != query.total_amount:
            await query.answer(
                ok=False,
                error_message="Цена изменилась. Пожалуйста, откройте меню заново.",
            )
            return
    else:
        await query.answer(ok=False, error_message="Неизвестный товар.")
        return

    await query.answer(ok=True)


async def create_private_invite_link(bot, label: str) -> str:
    """Return Discord server invite link for PRIVATE BLOCK, or generate TG channel link if configured."""
    discord_link = db.get_setting("private_channel_link", "").strip()
    if discord_link:
        return discord_link

    channel_id = db.get_setting("private_channel_id", "").strip()
    if channel_id:
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=int(channel_id),
                member_limit=1,
                name=label[:32],
            )
            return invite.invite_link
        except (TelegramError, ValueError) as exc:
            logger.error("Failed to create invite link for %s: %s", channel_id, exc)

    return ""


async def successful_payment_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Deliver purchased build or Private Block invite link after Telegram Stars payment."""
    msg = update.message
    payment = msg.successful_payment
    user = update.effective_user
    payload = payment.invoice_payload
    username = f"@{user.username}" if user.username else str(user.id)

    if payload.startswith("build:"):
        build_id = int(payload.split(":")[1])
        build = db.get_build(build_id)
        title = build["title"] if build else f"Сборка #{build_id}"

        db.record_purchase(
            user_id=user.id,
            username=username,
            item_type="build",
            item_id=build_id,
            item_title=title,
            amount=payment.total_amount,
            charge_id=payment.telegram_payment_charge_id,
        )

        if not build:
            await msg.reply_text(
                "✅ Оплата прошла успешно! Обратитесь в поддержку @juarezz для получения заказа."
            )
            return

        delivery_text = build.get("delivery_text", "").strip()
        delivery_file_id = build.get("delivery_file_id", "").strip()

        await msg.reply_text(
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"Спасибо за покупку <b>{html.escape(title)}</b>!",
            parse_mode=ParseMode.HTML,
        )

        if delivery_file_id:
            await msg.reply_document(
                document=delivery_file_id,
                caption=delivery_text or f"Ваш заказ: {title}",
            )
        elif delivery_text:
            await msg.reply_text(delivery_text, disable_web_page_preview=False)
        else:
            await msg.reply_text("Для получения материалов напишите в поддержку: @juarezz")

    elif payload == "private_block":
        db.record_purchase(
            user_id=user.id,
            username=username,
            item_type="private_block",
            item_id=None,
            item_title="PRIVATE BLOCK",
            amount=payment.total_amount,
            charge_id=payment.telegram_payment_charge_id,
        )
        db.add_private_member(
            user_id=user.id,
            username=user.username or str(user.id),
            source="stars",
        )

        invite_url = await create_private_invite_link(context.bot, f"Buyer {user.id}")

        if invite_url:
            await msg.reply_text(
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                "Вот ваша ссылка для входа в <b>PRIVATE BLOCK</b> (Discord-сервер):\n"
                f"👉 {invite_url}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔓 Перейти на Discord-сервер", url=invite_url)]]
                ),
            )
        else:
            await msg.reply_text(
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                "Ссылка на сервер пока не настроена. Напишите @juarezz, "
                "и администратор выдаст вам доступ вручную.",
                parse_mode=ParseMode.HTML,
            )
