import asyncio
import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

from fetcher import fetch_faa_notams, fetch_navarea_warnings
from formatter import format_reservation

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


async def send_reservations(bot: Bot):
    logger.info("Fetching reservations...")
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    messages = []

    try:
        notams = fetch_faa_notams()
        for notam in notams:
            messages.append(format_reservation(notam, notam.get("type", "air")))
    except Exception as e:
        logger.error(f"FAA fetch error: {e}")

    try:
        navareas = fetch_navarea_warnings()
        for nav in navareas:
            messages.append(format_reservation(nav, nav.get("type", "sea")))
    except Exception as e:
        logger.error(f"NAVAREA fetch error: {e}")

    if not messages:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🕐 *{now}*\n\nАктивных резерваций не найдено.",
            parse_mode="Markdown"
        )
        return

    # Шапка — одно отдельное сообщение
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"🛰 *Резервации воздушного и морского пространства*\n🕐 {now}",
        parse_mode="Markdown"
    )

    # Каждая резервация — отдельное сообщение
    for msg in messages:
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для мониторинга резерваций воздушного и морского пространства.\n\n"
        "📡 Доступные команды:\n"
        "/check — получить актуальные резервации прямо сейчас\n"
        "/help — помощь\n\n"
        "⏰ Автоматические обновления приходят каждый час."
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Получаю данные, подождите...")
    await send_reservations(context.bot)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Справка по боту*\n\n"
        "Бот отслеживает:\n"
        "✈️ *FAA NOTAM* — воздушные резервации (NASA, SpaceX, военные и др.)\n"
        "🌊 *NAVAREA* — морские резервации (ракетные пуски, учения)\n\n"
        "Каждое уведомление содержит:\n"
        "• Тип резервации (воздушная / морская)\n"
        "• Временное окно запуска\n"
        "• Полигон / зона запуска\n"
        "• Координаты для копирования\n\n"
        "Обновления — каждый час автоматически.",
        parse_mode="Markdown"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("help", cmd_help))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_reservations,
        "interval",
        hours=1,
        args=[app.bot],
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler.start()

    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
