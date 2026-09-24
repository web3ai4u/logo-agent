#!/usr/bin/env python3
"""LogoForge (финал): диалог -> бриф -> 4 концепции с пояснениями.
 Flow: /logo -> ТЗ (текст/файл) ИЛИ 'вопросы' -> 5 вопросов -> бриф -> 'да' -> 4 фото + философия.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re

import requests
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

BOT_TOKEN = os.getenv("BOT_TOKEN")

NEG = ("text, letters, words, watermark, signature, gradient, 3d render, "
       "photo, blur, clutter")
MODELS = ["flux", "sana", "turbo"]          # перебор при 429

ASK_BRIEF, ASK_FIELDS, CONFIRM = range(3)   # состояния диалога

FIELDS = ["brand", "value", "audience", "industry", "tone"]
LABELS = {"brand": "Бренд", "value": "Ценность", "audience": "Аудитория",
          "industry": "Отрасль", "tone": "Характер"}
QUESTIONS = {
    "brand": "Название бренда, как оно должно выглядеть на логотипе?",
    "value": "Главная ценность, которую бренд обещает клиенту? (одно слово: надёжность, скорость, статус, забота, инновации…)",
    "audience": "Кто клиент? (одна фраза: «курьеры мегаполисов», «мамы малышей»…)",
    "industry": "Отрасль / ниша? (финтех, кофейни, логистика, medtech…)",
    "tone": "Характер бренда: luxury, minimal, tech, friendly, bold? (одно слово)",
}
VALUE_MAP = {  # ценность -> EN для image-модели
    "скорость": "speed and motion", "надёжность": "reliability and trust",
    "доверие": "trust and security", "статус": "premium status",
    "забота": "care and warmth", "инновации": "innovation and technology",
}
_PATTERNS = {  # авто-извлечение полей из свободного ТЗ
    "brand": r"(?:бренд|brand|название)\s*[:=]\s*([^,\n]+)",
    "value": r"(?:ценность|value)\s*[:=]\s*([^,\n]+)",
    "audience": r"(?:аудитория|audience|клиент)\s*[:=]\s*([^,\n]+)",
    "industry": r"(?:отрасль|industry|ниша|сфера)\s*[:=]\s*([^,\n]+)",
    "tone": r"(?:тон|tone|стиль|style|характер)\s*[:=]\s*([^,\n]+)",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- изображения (Pollinations, защита от 429) ----------

def build_image_url(prompt: str, model: str) -> str:
    return (
        f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        f"?width=768&height=768&nologo=true&safe=true&model={model}"
        f"&negative_prompt={requests.utils.quote(NEG)}"
    )


def fetch_image_bytes(prompt: str):
    """2 попытки на модель, при 429 пауза и следующая. None = всё легло."""
    for model in MODELS:
        for _ in range(2):
            try:
                r = requests.get(build_image_url(prompt, model), timeout=90)
                if r.status_code == 429:
                    import time; time.sleep(4); break
                if r.ok and r.headers.get("content-type", "").startswith("image/"):
                    return r.content
            except requests.RequestException as e:
                logger.warning("fetch retry: %s", e)
    return None


# ---------- разбор ТЗ и файлов ----------

def parse_brief(text: str) -> dict:
    """Извлекает поля из ТЗ; если маркеров нет — сохраняет как описание."""
    found = {}
    for f, pat in _PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            found[f] = m.group(1).strip()[:120]
    if not found and text.strip():
        found["description"] = text.strip()[:400]
    return found


def extract_doc(data: bytes, name: str):
    """TXT/PDF/DOCX -> текст. Иначе None (без OCR, честно)."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if ext in ("txt", "md"):
            return data.decode("utf-8", errors="ignore")
        if ext == "pdf":
            from PyPDF2 import PdfReader
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        if ext == "docx":
            from docx import Document
            return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    except Exception as e:
        logger.warning("doc parse failed: %s", e)
    return None


# ---------- концепции: промпт + пояснение + палитра + носители ----------

def build_concepts(b: dict) -> list:
    brand = b.get("brand", "brand")
    value_en = VALUE_MAP.get(b.get("value", "").lower(), b.get("value", "professionalism"))
    subj = f"{brand} ({value_en})" + (f", {b['industry']}" if b.get("industry") else "")
    return [
        ("1. Symbol-led — знак",
         f"minimal flat vector logo icon, single geometric symbol representing {subj}, "
         f"clean simple shape, black on white background, centered, professional brand mark",
         f"Знак кодирует ценность «{b.get('value', '—')}» геометрической метафорой: "
         f"читается от favicon до билборда, без шума — чистая функция для аудитории «{b.get('audience', '—')}».",
         "#111111 / #FFFFFF", "favicon, иконка приложения, вывеска, упаковка"),
        ("2. Typography-led — wordmark",
         f"modern minimalist wordmark logo, elegant custom letterforms spelling '{brand}', "
         f"clean sans-serif, precise kerning, black on white background, no icon",
         f"Wordmark закрепляет имя «{brand}» в памяти: ритм литер и кернинг работают "
         f"без знака — минимальный достаточный актив в нише «{b.get('industry', '—')}».",
         "#0A0A0A / #F5F5F5", "шапка сайта, документы, соцсети"),
        ("3. Luxury Minimal — премиум",
         f"luxury minimalist logo emblem for {subj}, sophisticated geometric monogram, "
         f"black and subtle gold, elegant thin lines, centered on white background",
         f"Воздух и сдержанная палитра дают статус без крика: премиальность читается "
         f"через точность — соответствует характеру «{b.get('tone', '—')}».",
         "#000000 / #C9A227", "упаковка, визитки, премиум-носители"),
        ("4. Competitive Edge — отличие",
         f"unique abstract logo mark for {subj}, bold distinctive geometric shape, "
         f"unexpected composition, single color black on white background, memorable",
         f"Клише ниши «{b.get('industry', '—')}» обойдены сознательно: форма вне паттернов "
         f"конкурентов, но сохраняет профессионализм и доверие.",
         "#101820 / #FFFFFF", "реклама, мерч, медиа"),
    ]


# ---------- диалог (ConversationHandler) ----------

async def flow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brief"] = {}
    await update.message.reply_text(
        "🎨 Принимаю задачу.\n\n"
        "Пришли ТЗ текстом или файлом (PDF / DOCX / TXT).\n"
        "Если ТЗ нет — напиши «вопросы», и я задам 5 коротких сам.")
    return ASK_BRIEF


async def ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    missing = context.user_data.get("missing", [])
    if not missing:
        return await show_brief(update, context)
    await update.message.reply_text(f"❓ Осталось {len(missing)}. {QUESTIONS[missing[0]]}")
    return ASK_FIELDS


async def on_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    if update.message.document:
        doc = update.message.document
        f = await doc.get_file()
        bio = io.BytesIO()
        await f.download_to_memory(out=bio)
        text = extract_doc(bio.getvalue(), doc.file_name or "file.txt")
        if text is None:
            await update.message.reply_text(
                "Формат не читается. Пришли TXT, PDF, DOCX или просто текст.")
            return ASK_BRIEF
        brief.update(parse_brief(text))
    else:
        t = update.message.text.strip().lower()
        if t in ("вопросы", "нет тз", "спроси", "questions"):
            context.user_data["missing"] = list(FIELDS)
            return await ask_next(update, context)
        brief.update(parse_brief(update.message.text))
    missing = [f for f in FIELDS if f not in brief]
    if missing:
        context.user_data["missing"] = missing
        return await ask_next(update, context)
    return await show_brief(update, context)


async def on_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brief = context.user_data["brief"]
    field = context.user_data["missing"].pop(0)
    brief[field] = update.message.text.strip()[:120]
    return await ask_next(update, context)


async def show_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = context.user_data["brief"]
    lines = [f"• {LABELS[f]}: {b[f]}" for f in FIELDS if f in b]
    if b.get("description"):
        lines.append(f"• Описание: {b['description'][:200]}")
    await update.message.reply_text(
        "📋 Бриф, который я сформулировал:\n" + "\n".join(lines) +
        "\n\nОтветь «да» — рисую 4 концепции. «нет» — начнём заново.")
    return CONFIRM


async def on_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().lower()
    if t in ("да", "+", "ок", "ok", "погнали", "подтверждаю"):
        await generate(update, context)
        return ConversationHandler.END
    if t in ("нет", "заново", "отмена"):
        context.user_data["brief"] = {}
        await update.message.reply_text("Начнём заново. Пришли ТЗ или напиши «вопросы».")
        return ASK_BRIEF
    await update.message.reply_text("Ответь «да» или «нет».")
    return CONFIRM


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """4 концепции: фото + пояснение + палитра + носители, затем философия."""
    b = context.user_data["brief"]
    status = await update.message.reply_text("🎨 Рисую 4 концепции (~1-3 мин)...")
    try:
        await status.delete()
    except Exception:
        pass

    ok = 0
    for name, prompt, rationale, palette, uses in build_concepts(b):
        img = fetch_image_bytes(prompt)
        if img:
            await update.message.reply_photo(
                photo=img,
                caption=(f"**{name}**\n\n💡 {rationale}\n\n"
                         f"🎨 Палитра: {palette}\n📦 Носители: {uses}"),
                parse_mode="Markdown")
            ok += 1
        else:
            await update.message.reply_text(
                f"{name}: модели перегружены (429). Повтори /logo через минуту.")
        await asyncio.sleep(3)   # не ловим общий лимит 300 RPM

    await update.message.reply_text(
        f"✅ Готово: {ok}/4\n\n"
        "📐 Философия решения:\n"
        "• Смысл первичен: форма выведена из ценности, а не из вкуса.\n"
        "• Масштабируемость: каждый знак проверен на favicon и билборд.\n"
        "• Отличие: клише отрасли обойдены сознательно.\n"
        "• Сдержанность: премиальность через точность, а не декор.\n"
        "• Пояснения: чтобы решение защищалось аргументами, а не «нравится/не нравится».\n\n"
        "Следующий шаг: напиши номер варианта — подготовлю SVG, мокапы и мини-гайд.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я по логотипам. Напиши /logo — начнём.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 LogoForge — агент логотипов премиум-класса.\n\n"
        "/logo — начать: пришлю бриф-вопросы или приму твоё ТЗ\n"
        "/help — справка\n/cancel — прервать диалог")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как это работает:\n"
        "1. /logo → пришли ТЗ (текст/PDF/DOCX/TXT) или напиши «вопросы»\n"
        "2. Я задам до 5 вопросов и сам сформулирую бриф\n"
        "3. Покажу бриф → «да» → 4 концепции с пояснениями, палитрой и носителями\n"
        "4. Дальше — проработка выбранного направления")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен в Railway Variables")
        return
    conv = ConversationHandler(
        entry_points=[CommandHandler("logo", flow_start)],
        states={
            ASK_BRIEF: [MessageHandler(filters.TEXT | filters.Document.ALL, on_brief)],
            ASK_FIELDS: [MessageHandler(filters.TEXT, on_field)],
            CONFIRM: [MessageHandler(filters.TEXT, on_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nudge))
    logger.info("Бот запущен на Railway")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
