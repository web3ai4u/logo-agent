#!/usr/bin/env python3
"""
Logo Agent - Railway + Pollinations.ai
Генерирует 4 концепции логотипа по ТЗ, отдаёт картинки + rationale.
"""

from __future__ import annotations

import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Кэш update_id — защита от повторной доставки (Telegram иногда шлёт один update дважды)
_seen_updates = set()

# Negative prompt: что НЕ должно попадать в кадр (текст, водянки, мусор)
NEG = "text, letters, words, watermark, signature, gradient, 3d render, photo, blur, clutter, extra details"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_image_url(prompt: str) -> str:
    """Собирает URL Pollinations.ai: промпт + параметры + negative."""
    encoded = requests.utils.quote(prompt)
    neg_encoded = requests.utils.quote(NEG)
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1024&nologo=true&model=flux&safe=true"
        f"&negative={neg_encoded}"
    )


def fetch_image_bytes(url: str, tries: int = 2, timeout: int = 90):
    """Скачивает PNG. Возвращает bytes или None. Не падает."""
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=timeout)
            ctype = r.headers.get("content-type", "")
            if r.ok and ctype.startswith("image/"):
                return r.content
        except requests.RequestException as e:
            logger.warning("pollinations try %d failed: %s", attempt + 1, e)
    return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие + формат ТЗ."""
    await update.message.reply_text(
        "🎨 Logo Agent активен\n\n"
        "Отправь: /logo бренд=Название ценность=скорость\n\n"
        "Пример:\n"
        "/logo бренд=СеверныйПоток ценность=надёжность отрасль=логистика"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка с форматом и примерами."""
    await update.message.reply_text(
        "📋 Команды:\n\n"
        "/start - приветствие\n"
        "/logo [ТЗ] - 4 концепции логотипа\n"
        "/help - эта справка\n\n"
        "Формат ТЗ (в одну строку):\n"
        "бренд=Название\n"
        "ценность=доверие|скорость|статус|забота|инновации\n"
        "аудитория=кто клиент\n"
        "отрасль=финтех|edtech|медицина|ритейл|логистика\n\n"
        "Пример:\n"
        "/logo бренд=CoffeeFlow ценность=скорость отрасль=кофейни"
    )


async def logo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/logo -> 4 концепции картинками."""
    # Идемпотентность: повторяющийся update_id игнорируем
    uid = update.update_id
    if uid in _seen_updates:
        return
    _seen_updates.add(uid)
    if len(_seen_updates) > 2000:
        _seen_updates.clear()

    text = update.message.text.replace("/logo", "", 1).strip()

    if not text:
        await update.message.reply_text(
            "Отправь ТЗ в формате:\n"
            "/logo бренд=Название ценность=скорость\n\n"
            "Нажми /help для примеров"
        )
        return

    status_msg = await update.message.reply_text("🎨 Генерирую 4 концепции (~1-2 мин)...")

    # 4 направления = 4 гипотезы бренда
    concepts = [
        {
            "name": "Symbol-led (символ)",
            "prompt": f"minimal vector logo symbol for {text}, single geometric shape, flat, centered, white background, professional brand identity",
            "rationale": "метафора бренда через знак",
        },
        {
            "name": "Typography-led (типографика)",
            "prompt": f"modern typography wordmark logo for {text}, custom letterforms, precise kerning, elegant spacing, minimalist, white background",
            "rationale": "узнаваемость через шрифт",
        },
        {
            "name": "Luxury Minimal (премиум)",
            "prompt": f"luxury minimalist logo for {text}, black with subtle gold accent, sophisticated geometry, high-end brand, white background",
            "rationale": "премиальность через сдержанность",
        },
        {
            "name": "Competitive Edge (отличие)",
            "prompt": f"distinctive abstract logo for {text}, unexpected innovative shape, professional, memorable, stands out, white background",
            "rationale": "отличие от клише отрасли",
        },
    ]

    try:
        await status_msg.delete()
    except Exception:
        pass

    success_count = 0
    for i, concept in enumerate(concepts, 1):
        url = build_image_url(concept["prompt"])
        img = fetch_image_bytes(url)

        caption = (
            f"**Вариант {i}: {concept['name']}**\n\n"
            f"💡 {concept['rationale']}\n\n"
            f"ТЗ: {text[:100]}{'...' if len(text) > 100 else ''}"
        )

        if img:
            await update.message.reply_photo(
                photo=img,
                caption=caption,
                parse_mode="Markdown",
            )
            success_count += 1
        else:
            # Graceful degrade: кадр не удался — отдаём прямую ссылку, бот не падает
            await update.message.reply_text(
                f"Вариант {i} ({concept['name']}): генерация не удалась.\n"
                f"Открой в браузере: {url}",
                parse_mode="Markdown",
            )

    # Финальный блок: философия + что дальше
    footer = (
        f"✅ Сгенерировано: {success_count}/4 концепций\n\n"
        "📐 Философия:\n"
        "• Symbol-led: смысл через знак\n"
        "• Typography: узнаваемость через шрифт\n"
        "• Luxury: премиальность через сдержанность\n"
        "• Competitive Edge: отличие от клише\n\n"
        "Выбери направление для детальной проработки (SVG, мокапы, фирменный стиль)."
    )
    await update.message.reply_text(footer)


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен в Railway Variables")
        return

    logger.info("Инициализация Logo Agent...")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("logo", logo_command))

    logger.info("Бот запущен на Railway")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
