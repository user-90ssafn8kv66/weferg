"""Разбор пожеланий на русском языке: стиль, сезон, цвета, бюджет, имеющиеся вещи."""
from __future__ import annotations

import datetime as dt
import re

from .models import OwnedItem, Wishes

# Основы слов -> слот. Слот вещи определяется по самому раннему совпадению в тексте.
SLOT_STEMS = {
    "outerwear": ["куртк", "пальто", "пуховик", "тренч", "плащ", "бомбер", "ветровк", "косух",
                  "шуб", "дубленк", "пиджак", "жакет", "парка", "парку"],
    "top": ["футболк", "рубашк", "свитер", "свитшот", "худи", "толстовк", "джемпер", "лонгслив",
            "блузк", "блуза", "водолазк", "кардиган", "поло"],
    "bottom": ["джинс", "брюк", "штаны", "шорт", "юбк", "чинос", "леггинс", "карго"],
    "dress": ["плать", "сарафан", "комбинезон"],
    "shoes": ["кроссовк", "кеды", "кед ", "ботин", "туфл", "сапог", "лофер", "челси", "сандал",
              "босонож", "угги", "мокасин"],
    "bag": ["сумк", "рюкзак", "шоппер", "клатч"],
    "accessory": ["шарф", "шапк", "ремень", "ремн", "очки", "кепк", "перчатк", "часы"],
}

COLOR_STEMS = {
    "black": ["черн"], "white": ["бел", "молочн"], "grey": ["сер"], "beige": ["беж", "песочн", "кремов"],
    "navy": ["темно-син", "темно син"], "blue": ["син", "голуб", "деним"], "red": ["красн"],
    "burgundy": ["бордов", "винн"], "green": ["зелен", "оливк"], "khaki": ["хаки"],
    "brown": ["коричн", "шоколад"], "pink": ["розов"], "yellow": ["желт", "горчичн"],
    "purple": ["фиолет", "сиренев", "лилов"], "orange": ["оранж"],
}
COLOR_RU = {
    "black": "черный", "white": "белый", "grey": "серый", "beige": "бежевый", "navy": "темно-синий",
    "blue": "синий", "red": "красный", "burgundy": "бордовый", "green": "зеленый", "khaki": "хаки",
    "brown": "коричневый", "pink": "розовый", "yellow": "желтый", "purple": "фиолетовый",
    "orange": "оранжевый",
}

STYLE_STEMS = {
    "classic": ["делов", "офис", "классич", "классик", "строг", "formal", "classic"],
    "sport": ["спорт", "sport", "трениров", "бег"],
    "street": ["стритвир", "уличн", "street", "оверсайз"],
    "evening": ["вечерн", "свидани", "праздн", "ресторан", "вечеринк", "evening"],
    "casual": ["кэжуал", "кежуал", "casual", "повседнев", "на каждый день"],
}
SEASON_STEMS = {"winter": ["зим"], "autumn": ["осен"], "spring": ["весн"], "summer": ["лет"]}

_ADJ_ENDINGS = ("ая", "яя", "ый", "ий", "ой", "ые", "ие", "ую", "юю", "ое", "ее", "ых", "их",
                "ым", "им", "ыми", "ими", "ого", "его", "ом", "ем")
# Начальная форма для поискового запроса: «платье», а не «платьем».
CANONICAL = {
    "куртк": "куртка", "ветровк": "ветровка", "косух": "косуха", "шуб": "шуба", "дубленк": "дубленка",
    "парк": "парка", "футболк": "футболка", "рубашк": "рубашка", "толстовк": "толстовка",
    "блуз": "блузка", "водолазк": "водолазка", "джинс": "джинсы", "брюк": "брюки", "шорт": "шорты",
    "юбк": "юбка", "леггинс": "леггинсы", "плать": "платье", "кроссовк": "кроссовки", "кед": "кеды",
    "ботин": "ботинки", "туфл": "туфли", "сапог": "сапоги", "лофер": "лоферы", "сандал": "сандалии",
    "босонож": "босоножки", "мокасин": "мокасины", "сумк": "сумка", "шапк": "шапка", "рем": "ремень",
    "кепк": "кепка", "перчатк": "перчатки", "пуховик": "пуховик", "тренч": "тренч", "плащ": "плащ",
    "бомбер": "бомбер", "пиджак": "пиджак", "жакет": "жакет", "свитер": "свитер", "свитшот": "свитшот",
    "джемпер": "джемпер", "лонгслив": "лонгслив", "кардиган": "кардиган", "сарафан": "сарафан",
    "комбинезон": "комбинезон", "рюкзак": "рюкзак", "шоппер": "шоппер", "клатч": "клатч", "шарф": "шарф",
}
_OWNED_MARKER = re.compile(r"\b(?:уже есть|у меня есть|есть|имеется|имею|под мои|под мой|под мою|к моим|к моему|к моей)\b")


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def _find(text: str, stems: list[str]) -> int:
    """Позиция самого раннего совпадения с началом слова или -1."""
    best = -1
    for stem in stems:
        m = re.search(r"(?<![а-яa-z])" + re.escape(stem), text)
        if m and (best < 0 or m.start() < best):
            best = m.start()
    return best


def garment_stem(text: str) -> str | None:
    """Основа названия вещи, стоящего в тексте первым: «брюки классические» -> «брюк»."""
    text = normalize(text) + " "
    hits = [(m.start(), stem) for stems in SLOT_STEMS.values() for stem in stems
            if (m := re.search(r"(?<![а-яa-z])" + re.escape(stem), text))]
    return min(hits)[1] if hits else None


def detect_slot(text: str) -> str | None:
    text = normalize(text) + " "
    hits = [(pos, slot) for slot, stems in SLOT_STEMS.items() if (pos := _find(text, stems)) >= 0]
    return min(hits)[1] if hits else None


def detect_color(text: str) -> str | None:
    text = normalize(text)
    hits = [(pos, c) for c, stems in COLOR_STEMS.items() if (pos := _find(text, stems)) >= 0]
    # navy перечислен раньше blue, поэтому при равной позиции выигрывает уточнённый цвет
    return min(hits, key=lambda h: h[0])[1] if hits else None


def detect_colors(text: str) -> list[str]:
    text = normalize(text)
    hits = sorted((pos, c) for c, stems in COLOR_STEMS.items() if (pos := _find(text, stems)) >= 0)
    return [c for _, c in hits]


def _garment_phrases(text: str) -> dict[str, str]:
    """Вещи, названные в тексте: слот -> слово вместе со стоящим перед ним прилагательным."""
    found: dict[str, str] = {}
    words = re.findall(r"[а-яa-z-]+", text)
    for i, word in enumerate(words):
        slot = detect_slot(word)
        if slot and slot not in found:
            prev = words[i - 1] if i and words[i - 1].endswith(_ADJ_ENDINGS) else ""
            if color := detect_color(prev):
                prev = COLOR_RU[color]
            noun = next((n for stem, n in CANONICAL.items() if word.startswith(stem)), word)
            found[slot] = f"{prev} {noun}".strip()
    return found


def parse_owned(text: str) -> OwnedItem | None:
    slot = detect_slot(text)
    return OwnedItem(text=text.strip(), slot=slot, color=detect_color(text)) if slot else None


def current_season(today: dt.date | None = None) -> str:
    month = (today or dt.date.today()).month
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(month, "autumn")


def _parse_budget(text: str) -> int | None:
    m = re.search(r"(?:до|бюджет\w*|не дороже|в пределах)\s*(\d[\d\s]*)(\s*(?:к\b|тыс|т\.р|k\b))?", text)
    if not m:
        return None
    value = int(re.sub(r"\s", "", m.group(1)))
    return value * 1000 if m.group(2) else value


def parse_wishes(text: str = "", *, have: list[str] | None = None, **overrides) -> Wishes:
    """Собирает Wishes из свободного текста, списка имеющихся вещей и явных параметров."""
    norm = normalize(text)
    wishes = Wishes(text=text, season=current_season())

    # Всё, что идёт после «есть …» до конца предложения, считаем имеющимися вещами.
    wanted_text = norm
    for sentence in re.split(r"[.;!?\n]", norm):
        m = _OWNED_MARKER.search(sentence)
        if not m:
            continue
        wanted_text = wanted_text.replace(sentence[m.start():], " ")
        for part in re.split(r",|\s+и\s+", sentence[m.end():]):
            if owned := parse_owned(part):
                wishes.owned.append(owned)
    for raw in have or []:
        if owned := parse_owned(raw):
            wishes.owned.append(owned)
        else:
            raise ValueError(f"Не понял, что за вещь: «{raw}». Назовите её, например «белые кроссовки».")

    if re.search(r"женск|девушк|женщин|для нее\b|для жены", norm):
        wishes.gender = "female"
    elif re.search(r"мужск|парн|мужчин|для него\b|для мужа", norm):
        wishes.gender = "male"
    for style, stems in STYLE_STEMS.items():
        if _find(norm, stems) >= 0:
            wishes.style = style
            break
    for season, stems in SEASON_STEMS.items():
        if _find(norm, stems) >= 0:
            wishes.season = season
            break
    wishes.budget = _parse_budget(norm)
    if m := re.search(r"размер\w*\s+(?:одежды\s+)?([a-z]{1,4}|\d{2,3})\b", norm):
        wishes.size = m.group(1).upper()
    if m := re.search(r"(?:размер\w* обуви|обувь)\s+(\d{2}(?:[.,]5)?)", norm):
        wishes.shoe_size = m.group(1)

    wishes.requested = _garment_phrases(wanted_text)
    requested_colors = set(detect_colors(" ".join(wishes.requested.values())))
    # Цвет, стоящий при конкретной вещи, относится только к ней, а не ко всему образу.
    wishes.colors = [c for c in detect_colors(wanted_text) if c not in requested_colors]

    for key, value in overrides.items():
        if value is not None:
            setattr(wishes, key, value)
    return wishes
