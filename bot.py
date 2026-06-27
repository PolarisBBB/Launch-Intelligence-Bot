import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from fetcher import fetch_faa_notams, fetch_navarea_warnings, fetch_upcoming_launches, find_matching_launch
from formatter import format_reservation

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

sent_ids = set()


async def send_reservations(bot: Bot, daily=False):
    logger.info("Fetching reservations...")
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    all_items = []
    try:
        all_items.extend(fetch_faa_notams())
    except Exception as e:
        logger.error(f"FAA error: {e}")
    try:
        all_items.extend(fetch_navarea_warnings())
    except Exception as e:
        logger.error(f"NAVAREA error: {e}")

    # Загружаем запуски один раз для всех резерваций
    launches = fetch_upcoming_launches()

    if daily:
        to_send = all_items
        sent_ids.clear()
    else:
        to_send = [x for x in all_items if x.get("id") not in sent_ids]

    if daily:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🛰 *Ежедневная сводка резерваций*\n🕐 {now}",
            parse_mode="Markdown"
        )
        if not to_send:
            await bot.send_message(
                chat_id=CHAT_ID,
                text="📭 Активных резерваций не найдено.",
                parse_mode="Markdown"
            )
            return
    else:
        if not to_send:
            return
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🆕 *Новые резервации*\n🕐 {now}",
            parse_mode="Markdown"
        )

    for item in to_send:
        try:
            # Ищем совпадение с запуском
            launch_match = find_matching_launch(item, launches)

            await bot.send_message(
                chat_id=CHAT_ID,
                text=format_reservation(item, item.get("type", "sea"), launch_match),
                parse_mode="Markdown"
            )
            sent_ids.add(item.get("id"))
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n/check — резервации сейчас\n/help — помощь"
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Получаю данные...")
    await send_reservations(context.bot, daily=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌊 NAVAREA/HYDROPAC/HYDROLANT — морские резервации\n"
        "✈️ FAA TFR — воздушные резервации\n\n"
        "📅 Ежедневная сводка в 03:00 МСК\n"
        "🔄 Новые резервации — каждый час\n"
        "🚀 Совпадение с запуском — автоматически"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("help", cmd_help))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        send_reservations,
        CronTrigger(hour=3, minute=0, timezone="Europe/Moscow"),
        args=[app.bot, True]
    )

    scheduler.add_job(
        send_reservations,
        "interval",
        hours=1,
        args=[app.bot, False]
    )

    scheduler.start()
    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
