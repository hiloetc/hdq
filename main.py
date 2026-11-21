import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

import database as db
import handlers_admin as admin_h
import handlers_user as user_h

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error(
            "BOT_TOKEN не задан! Укажите токен от @BotFather в файле .env (на ПК) "
            "или в переменных окружения Bothost."
        )
        sys.exit(1)

    db.init_db()
    logger.info("База данных инициализирована.")

    builder = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(20.0)
        .read_timeout(20.0)
        .write_timeout(20.0)
        .pool_timeout(20.0)
        .get_updates_connect_timeout(20.0)
        .get_updates_read_timeout(20.0)
    )
    proxy_url = os.getenv("PROXY_URL", "").strip()
    if proxy_url:
        logger.info("Используется прокси: %s", proxy_url)
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    app = builder.build()

    # Admin conversation flows (must be registered before generic callbacks)
    app.add_handler(admin_h.build_admin_conversation())

    # Commands
    app.add_handler(CommandHandler("start", user_h.cmd_start))
    app.add_handler(CommandHandler("admin", admin_h.cmd_admin))

    # User menu callbacks
    app.add_handler(CallbackQueryHandler(user_h.cb_check_subscription, pattern=r"^check_sub$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_main_menu, pattern=r"^menu:main$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_builds_catalog, pattern=r"^menu:builds$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_private_block, pattern=r"^menu:private$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_support, pattern=r"^menu:support$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_build_detail, pattern=r"^build:\d+$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_free_build, pattern=r"^free:build:\d+$"))
    app.add_handler(CallbackQueryHandler(user_h.cb_buy_stars, pattern=r"^buy:(build:\d+|private)$"))

    # Admin menu callbacks
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_main, pattern=r"^admin:main$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_builds, pattern=r"^admin:builds$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_edit_build_menu, pattern=r"^admin:edit_build:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_delete_build, pattern=r"^admin:del_build:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_private, pattern=r"^admin:private$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_sub_channels, pattern=r"^admin:sub_channels$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_del_sub_channel, pattern=r"^admin:del_sub_ch:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_purchases, pattern=r"^admin:purchases$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_pb_members, pattern=r"^admin:pb_members$"))
    app.add_handler(CallbackQueryHandler(admin_h.cb_admin_stats, pattern=r"^admin:stats$"))

    # Telegram Stars payments
    app.add_handler(PreCheckoutQueryHandler(user_h.precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, user_h.successful_payment_handler))

    logger.info("Бот запущен (Long Polling)...")
    # Python 3.14+ requires an explicit event loop on the main thread for run_polling()
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
