import logging
import os
import json
from datetime import datetime, timezone, timedelta
from map_generator import generate_map

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from fetcher import fetch_faa_notams, fetch_navarea_warnings, fetch_upcoming_launches, find_matching_launch
from formatter import format_reservation

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Хранилище
sent_ids = set()
archive = {}  # id -> dict резервации


def save_to_archive(item: dict):
    """Сохраняем резервацию в архив с временной меткой."""
    res_id = item.get("id")
    if res_id and res_id not in archive:
        archive[res_id] = {
            **item,
            "archived_at": datetime.now(timezone.utc).isoformat()
        }


def clean_archive():
    """Удаляем резервации старше 7 дней."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    to_delete = []
    for res_id, item in archive.items():
        try:
            archived_at = datetime.fromisoformat(item.get("archived_at", ""))
            if archived_at < cutoff:
                to_delete.append(res_id)
        except Exception:
            pass
    for res_id in to_delete:
        del archive[res_id]


def check_changes(new_items: list) -> list:
    alerts = []
    current_ids = {item.get("id") for item in new_items}

    # Проверяем снятые резервации
    for res_id in list(sent_ids):
        if res_id not in current_ids and res_id in archive:
            old = archive[res_id]
            alerts.append({
                "type": "cancelled",
                "message": (
                    f"🚨 *РЕЗЕРВАЦИЯ СНЯТА*\n"
                    f"📍 Зона: {old.get('source','')}\n"
                    f"🆔 `{res_id}`\n"
                    f"Резервация больше не активна."
                )
            })
            # Убираем из sent_ids чтобы не проверять снова
            sent_ids.discard(res_id)

    # Проверяем изменения временного окна
    for item in new_items:
        res_id = item.get("id")
        if res_id in archive:
            old_window = archive[res_id].get("time_window", "")
            new_window = item.get("time_window", "")
            if old_window and new_window and old_window != new_window:
                # Зачёркиваем старое окно через unicode
                old_struck = "\u0336".join(old_window) + "\u0336"
                alerts.append({
                    "type": "changed",
                    "item": item,
                    "message": (
                        f"⚠️ *ИЗМЕНЕНИЕ ВРЕМЕННОГО ОКНА*\n"
                        f"📍 Зона: {item.get('source','')}\n"
                        f"🆔 `{res_id}`\n"
                        f"Было: {old_struck}\n"
                        f"Стало: `{new_window}`"
                    )
                })
                # Обновляем архив — чтобы не присылать повторно
                archive[res_id]["time_window"] = new_window

    return alerts


def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🌊 Морские", callback_data="filter_sea"),
            InlineKeyboardButton("✈️ Воздушные", callback_data="filter_air"),
        ],
        [
            InlineKeyboardButton("📡 Все резервации", callback_data="filter_all"),
            InlineKeyboardButton("📂 Архив (7 дней)", callback_data="archive"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="refresh"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


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

    launches = fetch_upcoming_launches()

    # Проверяем изменения и снятия
    alerts = check_changes(all_items)
    for alert in alerts:
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=alert["message"],
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")

    if daily:
        to_send = all_items
        sent_ids.clear()
    else:
        to_send = [x for x in all_items if x.get("id") not in sent_ids]

    # Сохраняем в архив
    for item in all_items:
        save_to_archive(item)
    clean_archive()

    if daily:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"🛰 *Ежедневная сводка резерваций*\n🕐 {now}",
            reply_markup=get_main_keyboard(),
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
            launch_match = find_matching_launch(item, launches)
            await bot.send_message(
                chat_id=CHAT_ID,
                text=format_reservation(item, item.get("type", "sea"), launch_match),
                parse_mode="Markdown"
            )
            # Отправляем карту
            map_image = generate_map(item)
            if map_image:
                await bot.send_photo(
                    chat_id=CHAT_ID,
                    photo=map_image,
                    caption=f"🗺 {item.get('source','')} | {item.get('id','')}"
                )
            sent_ids.add(item.get("id"))
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")


async def cmd_start(update: Update, context):
    await update.message.reply_text(
        "👋 Привет! Я бот мониторинга резерваций.\n\n"
        "Выбери что хочешь посмотреть:",
        reply_markup=get_main_keyboard()
    )


async def cmd_check(update: Update, context):
    await update.message.reply_text("🔄 Получаю данные...")
    await send_reservations(context.bot, daily=True)


async def cmd_help(update: Update, context):
    await update.message.reply_text(
        "🌊 Морские — NAVAREA/HYDROPAC/HYDROLANT\n"
        "✈️ Воздушные — FAA TFR\n\n"
        "📅 Сводка в 03:00 МСК\n"
        "🔄 Новые резервации — каждый час\n"
        "🚨 Снятие/изменение — мгновенно\n"
        "📂 Архив — последние 7 дней"
    )


async def handle_button(update: Update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    if data == "refresh":
        await query.message.reply_text("🔄 Получаю данные...")
        await send_reservations(context.bot, daily=True)
        return

    if data == "archive":
        clean_archive()
        items = list(archive.values())
        if not items:
            await query.message.reply_text("📂 Архив пуст.")
            return

        await query.message.reply_text(
            f"📂 *Архив резерваций за 7 дней*\n🕐 {now}\nВсего: {len(items)}",
            parse_mode="Markdown"
        )
        launches = fetch_upcoming_launches()
        for item in items:
            try:
                launch_match = find_matching_launch(item, launches)
                await query.message.reply_text(
                    format_reservation(item, item.get("type", "sea"), launch_match),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Архив ошибка отправки: {e}")
        return

    # Фильтры
    all_items = []
    try:
        all_items.extend(fetch_faa_notams())
        all_items.extend(fetch_navarea_warnings())
    except Exception as e:
        logger.error(f"Fetch error: {e}")

    if data == "filter_sea":
        items = [x for x in all_items if x.get("type") == "sea"]
        title = "🌊 *Морские резервации*"
    elif data == "filter_air":
        items = [x for x in all_items if x.get("type") == "air"]
        title = "✈️ *Воздушные резервации*"
    else:
        items = all_items
        title = "📡 *Все резервации*"

    if not items:
        await query.message.reply_text("📭 Резерваций не найдено.")
        return

    await query.message.reply_text(
        f"{title}\n🕐 {now}\nНайдено: {len(items)}",
        parse_mode="Markdown"
    )

    launches = fetch_upcoming_launches()
    for item in items:
        try:
            launch_match = find_matching_launch(item, launches)
            await query.message.reply_text(
                format_reservation(item, item.get("type", "sea"), launch_match),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_button))

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
