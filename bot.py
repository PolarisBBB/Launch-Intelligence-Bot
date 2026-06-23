rm bot.py
cat > bot.py << 'EOF'
import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from fetcher import fetch_faa_notams, fetch_navarea_warnings
from formatter import format_reservation

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
        await bot.send_message(chat_id=CHAT_ID, text=f"🕐 *{now}*\n\nАктивных резерваций не найдено.", parse_mode="Markdown")
        return
    await bot.send_message(chat_id=CHAT_ID, text=f"🛰 *Резервации воздушного и морского пространства*\n🕐 {now}", parse_mode="Markdown")
    for msg in messages:
        try:
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет!\n\n/check — резервации сейчас\n/help — помощь")

async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Получаю данные...")
    await send_reservations(context.bot)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✈️ FAA TFR — воздушные\n🌊 NAVAREA/HYDROPAC — морские\n\nОбновления каждый час.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("help", cmd_help))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reservations, "interval", hours=1, args=[app.bot], next_run_time=datetime.now(timezone.utc))
    scheduler.start()
    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
EOF
