#!/usr/bin/env python3
"""design_skills v3: анти-3D рецепт, семантика формы, палитры, транслит."""

# Запреты: всё, что превращает лого в медаль (negative часто игнорируется,
# поэтому дублируем эти слова отсутствием в позитиве)
BASE_NEG = ("3d, metallic, chrome, emboss, bevel, shadow, gradient, texture, mockup, "
            "badge, coin, medal, ring, frame, studio light, grey background, "
            "text, words, watermark, photo, blur, clutter, multiple logos")

# Плоский стиль: главные токены против 3D-медалей
STYLE_FLAT = ("flat 2d vector logo mark, solid single-color shape, minimalist glyph, "
              "clean sharp edges, no gradient, no shadow, no texture, no 3d, "
              "isolated on plain pure white background")

CRAFT_RULES = ("constructed on circular geometric grid, uniform stroke weight, "
               "optically centered, clear silhouette readable at 16 px, one idea only")

NEGSPACE_DIRECTIVE = "clever use of negative space forming a hidden secondary shape"

SHAPE_SEMANTICS = {
    "скорость": "diagonal dynamic lines, forward-leaning arrow motif, motion cut",
    "speed": "diagonal dynamic lines, forward-leaning arrow motif, motion cut",
    "надёжность": "stable square base, strong horizontal baseline, solid mass",
    "доверие": "closed circle, interlocking symmetric forms",
    "статус": "vertical symmetry, thin precise lines, tall balanced proportions",
    "забота": "soft rounded curves, enclosing circle, gentle overlap",
    "инновации": "modular grid fragments, one deliberate angle break, node connections",
}

CLICHES = {
    "финтех": "coins, dollar sign, candlestick chart, padlock, generic shield",
    "fintech": "coins, dollar sign, candlestick chart, padlock, generic shield",
    "медицина": "red cross, heartbeat line, caduceus, pill capsule",
    "кофейн": "steaming cup, coffee bean outline, barista portrait",
    "coffee": "steaming cup, coffee bean outline, barista portrait",
    "логистик": "delivery truck, globe with arrow, cardboard box",
    "строит": "house roof outline, crane, brick wall, key",
    "build": "house roof outline, crane, brick wall, key",
    "construct": "house roof outline, crane, brick wall, key",
    "edtech": "graduation cap, open book, lightbulb",
    "недвижим": "house roof outline, key, skyline silhouette",
    "эко": "green leaf, sprout, recycling arrows",
    "it": "binary code, circuit board, cloud with lines",
}

# Палитры: fg — RGB для постобработки (заливка знака)
PALETTES = {
    "luxury": dict(hexc="#0B0B0C", hexa="#C9A227", names="black, warm gold", fg=(11, 11, 12)),
    "премиум": dict(hexc="#0B0B0C", hexa="#C9A227", names="black, warm gold", fg=(11, 11, 12)),
    "minimal": dict(hexc="#111111", hexa="#8A8A8A", names="black, grey", fg=(17, 17, 17)),
    "tech": dict(hexc="#0E1B2C", hexa="#2DD4BF", names="deep navy, electric teal", fg=(14, 27, 44)),
    "friendly": dict(hexc="#1F2937", hexa="#F59E0B", names="charcoal, warm amber", fg=(31, 41, 55)),
    "bold": dict(hexc="#000000", hexa="#E63946", names="black, signal red", fg=(0, 0, 0)),
}

TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
            "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
            "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
            "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}


def translit(text: str) -> str:
    """Бренд кириллицей -> латиница (для монограммы и промптов)."""
    return "".join(TRANSLIT.get(ch.lower(), ch) for ch in text).strip() or "brand"


def shape_for(value: str) -> str:
    v = (value or "").lower()
    for key, lang in SHAPE_SEMANTICS.items():
        if key in v:
            return lang
    return "balanced geometric composition"


def cliches_for(industry: str) -> str:
    i = (industry or "").lower()
    for key, list_ in CLICHES.items():
        if key in i:
            return list_
    return "generic clipart symbols"


def palette_for(tone: str) -> dict:
    t = (tone or "").lower()
    for key, pal in PALETTES.items():
        if key in t:
            return pal
    return PALETTES["minimal"]


def negative_for(industry: str) -> str:
    return BASE_NEG + ", " + cliches_for(industry)
