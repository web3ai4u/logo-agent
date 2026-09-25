#!/usr/bin/env python3
"""LogoForge v3: модель = карандаш, агент = рука дизайнера.
Любой выход модели детерминированно превращается в плоский 2-цветный знак."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import time

import requests
from PIL import Image
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


# ---------- СЛОЙ 1: английский бриф (MyMemory, без ключа) ----------

def translate_ru_en(text: str) -> str:
    """Перевод описательных полей. Бренд НЕ переводим (это имя)."""
    if not re.search(r"[а-яА-Я]", text or ""):
        return text
    try:
        r = requests.get("https://api.mymemory.translated.net/get",
                         params={"q": text[:400], "langpair": "ru|en"}, timeout=10)
        out = r.json().get("responseData", {}).get("translatedText", "")
        if out and len(out) > 2:
            return out
    except Exception as e:
        logger.warning("translate failed: %s", e)
    return text  # fallback: сырой текст


# ---------- СЛОЙ 3: рука дизайнера (детерминированная постобработка) ----------

def flatten_logo(data: bytes, fg=(17, 17, 17), size=1024) -> bytes:
    """Любой выход модели -> плоский 2-цветный знак.
    1) grayscale 2) фон = среднее по углам 3) маска 'не фон'
    4) crop по bbox 5) квадрат с полями 6) заливка fg/bg.
    Убивает: градиенты, тени, металл, серый фон, текстуры."""
    im = Image.open(io.BytesIO(data)).convert("L")
    w, h = im.size
    px = im.load()
    bg_lum = (px[0, 0] + px[w - 1, 0] + px[0, h - 1] + px[w - 1, h - 1]) / 4
    mask = im.point(lambda p: 255 if abs(p - bg_lum) > 60 else 0)
    bbox = mask.getbbox()
    if bbox:
        mask = mask.crop(bbox)
    mw, mh = mask.size
    if mw == 0 or mh == 0:
        return data  # маска пустая — отдаём оригинал, не падаем
    side = int(max(mw, mh) * 1.25)
    canvas = Image.new("L", (side, side), 0)
    canvas.paste(mask, ((side - mw) // 2, (side - mh) // 2))
    canvas = canvas.resize((size, size), Image.LANCZOS)
    out = Image.composite(Image.new("RGB", (size, size), fg),
                          Image.new("RGB", (size, size), (255, 255, 255)),
                          canvas)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


# ---------- генерация ----------

def build_image_url(prompt: str, model: str, negative: str) -> str:
    return (
        f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        f"?width=768&height=768&nologo=true&safe=true&model={model}"
        f"&negative_prompt={requests.utils.quote(negative)}"
    )


def fetch_image_bytes(prompt: str, negative: str):
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


# ---------- ТЗ ----------

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


# ---------- СЛОЙ 2: анти-3D концепции ----------

def build_concepts(b: dict) -> list:
    brand = b.get("brand", "brand")
    brand_en = ds.translit(brand)
    letter = brand_en[0].upper()
    value = b.get("value", "")
    value_en = VALUE_MAP.get(value.lower(), translate_ru_en(value)) if value else "professionalism"
    ind_en = translate_ru_en(b.get("industry", ""))
    aud_en = translate_ru_en(b.get("audience", ""))
    shape = ds.shape_for(value)
    pal = ds.palette_for(b.get("tone"))
    subj = f"{brand_en} ({value_en})" + (f", {ind_en}" if ind_en else "")
    flat, craft = ds.STYLE_FLAT, ds.CRAFT_RULES
    return [
        ("1. Symbol-led — знак",
         f"{flat}, single geometric symbol representing {subj}, {shape}, "
         f"{ds.NEGSPACE_DIRECTIVE}, {craft}, shape color {pal['names']}",
         f"Семантика формы: «{value or '—'}» → {shape}. Негативное пространство даёт "
         f"второй слой чтения (эффект FedEx).",
         pal),
        ("2. Monogram — литера",
         f"{flat}, geometric monogram of single letter '{letter}', built from clean "
         f"geometry, {craft}, shape color {pal['names']}",
         f"Монограмма «{letter}» вместо слова: одну букву модель пишет точно, слово — "
         f"кривит. Имя закрепляется формой литеры.",
         pal),
        ("3. Luxury Minimal — премиум",
         f"{flat}, symmetric minimal mark for {subj}, thin precise uniform lines, "
         f"{craft}, shape color {pal['names']}",
         f"Статус через точность построения и воздух, а не через декор и металл.",
         pal),
        ("4. Competitive Edge — отличие",
         f"{flat}, bold unexpected abstract mark for {subj}, {shape} broken by one "
         f"deliberate angle, {craft}, shape color {pal['names']}",
         f"Клише ниши «{b.get('industry', '—')}» исключены: форма вне паттернов конкурентов.",
         pal),
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
        "\n\nОтветь «да» — рисую 4 плоских концепции + монохром. «нет» — заново.")
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
    negative = ds.negative_for(b.get("industry"))
    status = await update.message.reply_text("🎨 Рисую и уплощаю 4 концепции (~2-4 мин)...")
    try:
        await status.delete()
    except Exception:
        pass

    concepts = build_concepts(b)
    ok = 0
    first_raw = None
    for name, prompt, rationale, pal in concepts:
        raw = fetch_image_bytes(prompt, negative)
        if raw:
            if first_raw is None:
                first_raw = raw
            flat = flatten_logo(raw, fg=pal["fg"])   # рука дизайнера
            await update.message.reply_photo(
                photo=flat,
                caption=(f"**{name}**\n\n💡 {rationale}\n\n"
                         f"🎨 Палитра: {pal['hexc']} / {pal['hexa']} ({pal['names']})\n"
                         f"✅ Плоский 2-цветный знак: favicon/печать/гравировка безопасны"),
                parse_mode="Markdown")
            ok += 1
        else:
            await update.message.reply_text(f"{name}: модели перегружены (429). Повтори /logo через минуту.")
        await asyncio.sleep(3)

    if first_raw:
        mono = flatten_logo(first_raw, fg=(0, 0, 0))  # монохром-тест теперь честно чёрно-белый
        await update.message.reply_photo(
            photo=mono,
            caption="🧪 Монохром-тест: чистый чёрный силуэт на белом. "
                    "Выжил = знак живёт в favicon, гравировке, факсе, вышивке.")

    await update.message.reply_text(
        f"✅ Готово: {ok}/4 + монохром\n\n"
        "📐 Принцип v3: модель — карандаш, агент — рука дизайнера.\n"
        "Плоскость гарантирована постобработкой, а не надеждой на модель.\n\n"
        "Напиши номер варианта — подготовлю проработку (SVG, мокапы, мини-гайд).")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог завершён. /logo — начать заново.")
    return ConversationHandler.END


async def nudge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я по логотипам. Напиши /logo — начнём.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 LogoForge v3 — плоские логотипы премиум-класса.\n\n"
        "/logo — начать (ТЗ или 5 вопросов)\n/help — справка\n/cancel — прервать")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "1. /logo → ТЗ (текст/PDF/DOCX/TXT) или «вопросы»\n"
        "2. Формулирую бриф, перевожу на EN → «да»\n"
        "3. 4 плоских концепции + монохром-тест\n"
        "4. Проработка выбранного направления")


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
