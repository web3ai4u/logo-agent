#!/usr/bin/env python3
"""LogoForge финал+v2: диалог -> бриф -> 4 концепции + монохром-тест.
Слой дизайнерских навыков вынесен в design_skills.py."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time

import requests
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

import design_skills as ds

BOT_TOKEN = os.getenv("BOT_TOKEN")
MODELS = ["flux", "sana", "turbo"]

ASK_BRIEF, ASK_FIELDS, CONFIRM = range(3)

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
VALUE_MAP = {
    "скорость": "speed and motion", "надёжность": "reliability and trust",
    "доверие": "trust and security", "статус": "premium status",
    "забота": "care and warmth", "инновации": "innovation and technology",
}
_PATTERNS = {
    "brand": r"(?:бренд|brand|название)\s*[:=]\s*([^,\n]+)",
    "value": r"(?:ценность|value)\s*[:=]\s*([^,\n]+)",
    "audience": r"(?:аудитория|audience|клиент)\s*[:=]\s*([^,\n]+)",
    "industry": r"(?:отрасль|industry|ниша|сфера)\s*[:=]\s*([^,\n]+)",
    "tone": r"(?:тон|tone|стиль|style|характер)\s*[:=]\s*([^,\n]+)",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- генерация (Pollinations + защита от 429) ----------

def build_image_url(prompt: str, model: str, negative: str) -> str:
    return (
        f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        f"?width=768&height=768&nologo=true&safe=true&model={model}"
        f"&negative_prompt={requests.utils.quote(negative)}"
    )


def fetch_image_bytes(prompt: str, negative: str):
    """2 попытки на модель, при 429 пауза и следующая. None = всё легло."""
    for model in MODELS:
        for _ in range(2):
            try:
                r = requests.get(build_image_url(prompt, model, negative), timeout=90)
                if r.status_code == 429:
                    time.sleep(4)
                    break
                if r.ok and r.headers.get("content-type", "").startswith("image/"):
                    return r.content
            except requests.RequestException as e:
                logger.warning("fetch retry: %s", e)
    return None


# ---------- ТЗ: разбор текста и файлов ----------

def parse_brief(text: str) -> dict:
    found = {}
    for f, pat in _PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            found[f] = m.group(1).strip()[:120]
    if not found and text.strip():
        found["description"] = text.strip()[:400]
    return found


def extract_doc(data: bytes, name: str):
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


# ---------- концепции с применением навыков 1-5, 10, 12 ----------

def build_concepts(b: dict) -> list:
    brand = b.get("brand", "brand")
    value = b.get("value", "")
    value_en = VALUE_MAP.get(value.lower(), value or "professionalism")
    shape = ds.shape_for(value)                      # навык 1
    pal = ds.palette_for(b.get("tone"))              # навык 3
    subj = f"{brand} ({value_en})" + (f", {b['industry']}" if b.get("industry") else "")
    craft = ds.CRAFT_RULES                           # навыки 4/7/8/11
    return [
        ("1. Symbol-led — знак",
         f"minimal flat vector logo icon, single geometric symbol representing {subj}, "
         f"{shape}, {ds.NEGSPACE_DIRECTIVE}, {craft}, colors: {pal[3]}, white background",
         f"Семантика формы: ценность «{value or '—'}» → {shape}. Негативное пространство "
         f"даёт второй слой чтения (эффект стрелки FedEx): запоминаемость без деталей.",
         f"{pal[0]} / {pal[1]} / {pal[2]}", "favicon, иконка, вывеска, упаковка"),
        ("2. Typography-led — wordmark",
         f"modern minimalist wordmark logo, elegant custom letterforms spelling '{brand}', "
         f"clean geometric sans-serif, precise kerning, {craft}, color {pal[0]} on white, no icon",
         f"Wordmark держит имя «{brand}»: кернинг и ритм литер работают без знака — "
         f"минимальный достаточный актив в нише «{b.get('industry', '—')}».",
         f"{pal[0]} / {pal[2]}", "сайт, документы, соцсети"),
        ("3. Luxury Minimal — премиум",
         f"luxury minimalist emblem for {subj}, symmetric geometric monogram, thin precise "
         f"lines, {craft}, colors: {pal[3]}, white background",
         f"Сдержанность и воздух дают статус: премиальность читается через точность "
         f"построения, а не декор. Характер: «{b.get('tone', '—')}».",
         f"{pal[0]} / {pal[1]}", "упаковка, визитки, премиум-носители"),
        ("4. Competitive Edge — отличие",
         f"unique abstract logo mark for {subj}, bold unexpected geometry, {shape} broken "
         f"by one deliberate angle, {craft}, colors: {pal[3]}, white background",
         f"Клише ниши «{b.get('industry', '—')}» исключены negative-промптом: форма вне "
         f"паттернов конкурентов, но сохраняет профессионализм и доверие.",
         f"{pal[0]} / {pal[2]}", "реклама, мерч, медиа"),
    ]


# ---------- диалог ----------

async def flow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["brief"] = {}
    await update.message.reply_text(
        "🎨 Принимаю задачу.\n\nПришли ТЗ текстом или файлом (PDF / DOCX / TXT).\n"
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
            await update.message.reply_text("Формат не читается. Пришли TXT, PDF, DOCX или текст.")
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
    field = context.user_data["missing"].pop(0)
    context.user_data["brief"][field] = update.message.text.strip()[:120]
    return await ask_next(update, context)


async def show_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = context.user_data["brief"]
    lines = [f"• {LABELS[f]}: {b[f]}" for f in FIELDS if f in b]
    if b.get("description"):
        lines.append(f"• Описание: {b['description'][:200]}")
    await update.message.reply_text(
        "📋 Бриф, который я сформулировал:\n" + "\n".join(lines) +
        "\n\nОтветь «да» — рисую 4 концепции + монохром-тест. «нет» — заново.")
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
    b = context.user_data["brief"]
    negative = ds.negative_for(b.get("industry"))    # навык 2: клише под запретом
    status = await update.message.reply_text("🎨 Рисую 4 концепции + монохром-тест (~2-4 мин)...")
    try:
        await status.delete()
    except Exception:
        pass

    concepts = build_concepts(b)
    ok = 0
    for name, prompt, rationale, palette, uses in concepts:
        img = fetch_image_bytes(prompt, negative)
        if img:
            await update.message.reply_photo(
                photo=img,
                caption=(f"**{name}**\n\n💡 {rationale}\n\n"
                         f"🎨 Палитра: {palette}\n📦 Носители: {uses}"),
                parse_mode="Markdown")
            ok += 1
        else:
            await update.message.reply_text(f"{name}: модели перегружены (429). Повтори /logo через минуту.")
        await asyncio.sleep(3)

    # Навык 9: монохром-тест — доказательство масштабируемости, а не обещание
    mono = fetch_image_bytes(concepts[0][1] + ds.MONO_SUFFIX, negative)
    if mono:
        await update.message.reply_photo(
            photo=mono,
            caption="🧪 Монохром-тест: силуэт варианта 1 в один цвет. "
                    "Выжил = знак работает в favicon, гравировке, факсе, вышивке.")

    await update.message.reply_text(
        f"✅ Готово: {ok}/4 + монохром\n\n"
        "📐 Философия: смысл → форма → сетка → отличие → проверка.\n"
        "Применены навыки: семантика формы, анти-клише, палитра ≤3, "
        "круговая сетка/golden ratio, негативное пространство, монохром-тест.\n\n"
        "Напиши номер варианта — подготовлю проработку (SVG, мокапы, мини-гайд).")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я по логотипам. Напиши /logo — начнём.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 LogoForge — агент логотипов премиум-класса.\n\n"
        "/logo — начать (ТЗ или 5 вопросов)\n/help — справка\n/cancel — прервать")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "1. /logo → ТЗ (текст/PDF/DOCX/TXT) или «вопросы»\n"
        "2. Формулирую бриф → «да»\n"
        "3. 4 концепции с пояснениями + палитрой + носителями\n"
        "4. Монохром-тест знака\n5. Проработка выбранного направления")


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
