#!/usr/bin/env python3
"""design_skills.py — пак навыков дизайнера логотипов для LogoForge.
Даёт агенту стратегию, геометрию, палитры и запреты, которых нет у голой модели."""

# Навык 8/11: базовые запреты (перегруз, мусор, несколько лого)
BASE_NEG = ("text, letters, words, watermark, signature, gradient, 3d render, "
            "photo, blur, clutter, multiple logos, frame, border")

# Навык 1: семантика формы — ценность -> геометрический язык
SHAPE_SEMANTICS = {
    "скорость": "diagonal dynamic lines, forward-leaning arrow motif, motion cut",
    "надёжность": "stable square base, strong horizontal baseline, solid mass",
    "доверие": "closed circle, interlocking symmetric forms",
    "статус": "vertical symmetry, thin precise lines, crest-like balance",
    "забота": "soft rounded curves, enclosing circle, gentle overlap",
    "инновации": "modular grid fragments, one deliberate angle break, node connections",
}

# Навык 2: клише отраслей -> уходят в negative_prompt
CLICHES = {
    "финтех": "coins, dollar sign, candlestick chart, padlock, generic shield",
    "медицина": "red cross, heartbeat line, caduceus, pill capsule",
    "кофейн": "steaming cup, coffee bean outline, barista portrait",
    "логистик": "delivery truck, globe with arrow, cardboard box",
    "edtech": "graduation cap, open book, lightbulb",
    "образован": "graduation cap, open book, lightbulb",
    "недвижим": "house roof outline, key, skyline silhouette",
    "эко": "green leaf, sprout, recycling arrows",
    "it": "binary code, circuit board, cloud with lines",
}

# Навык 3: палитры по характеру (hex + описание для промпта)
PALETTES = {
    "luxury": ("#0B0B0C", "#C9A227", "#F4F1EA", "black, warm gold, ivory"),
    "премиум": ("#0B0B0C", "#C9A227", "#F4F1EA", "black, warm gold, ivory"),
    "minimal": ("#111111", "#FFFFFF", "#8A8A8A", "black, white, grey accent"),
    "tech": ("#0E1B2C", "#2DD4BF", "#F5F7FA", "deep navy, electric teal, off-white"),
    "friendly": ("#1F2937", "#F59E0B", "#FFF7E6", "charcoal, warm amber, cream"),
    "bold": ("#000000", "#E63946", "#FFFFFF", "black, signal red, white"),
}

# Навыки 4/7/8/11: ремесленные токены построения (общие для всех промптов)
CRAFT_RULES = ("constructed on circular geometric grid, golden ratio proportions, "
               "uniform stroke weight, optically centered, flat solid color shapes, "
               "clear silhouette readable at 16 px, one idea only")

# Навык 5: директива негативного пространства (эффект FedEx)
NEGSPACE_DIRECTIVE = "clever use of negative space forming a hidden secondary shape"

# Навык 9: второй проход — монохром-тест
MONO_SUFFIX = ", solid pure black silhouette on pure white background, one color only"


def shape_for(value: str) -> str:
    """Ценность -> геометрический язык (навык 1)."""
    v = (value or "").lower()
    for key, lang in SHAPE_SEMANTICS.items():
        if key in v:
            return lang
    return "balanced geometric composition"


def cliches_for(industry: str) -> str:
    """Отрасль -> список клише для запрета (навык 2)."""
    i = (industry or "").lower()
    for key, list_ in CLICHES.items():
        if key in i:
            return list_
    return "generic clipart symbols"


def palette_for(tone: str) -> tuple:
    """Характер -> палитра (навык 3). Возвращает (hex, hex, hex, описание)."""
    t = (tone or "").lower()
    for key, pal in PALETTES.items():
        if key in t:
            return pal
    return PALETTES["minimal"]


def negative_for(industry: str) -> str:
    """Полный negative: база + клише отрасли (навыки 2+8)."""
    return BASE_NEG + ", " + cliches_for(industry)
