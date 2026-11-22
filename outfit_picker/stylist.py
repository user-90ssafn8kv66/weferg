"""Подбор образа: какие слоты нужны, что искать и какая комбинация лучше."""
from __future__ import annotations

import itertools
from typing import Protocol

from .models import Item, Outfit, Wishes
from .wishes import COLOR_RU, detect_color, detect_slot, normalize

NEUTRALS = {"black", "white", "grey", "beige", "navy"}
# Проверенные сочетания ненейтральных цветов.
GOOD_PAIRS = {frozenset(p) for p in [
    ("blue", "brown"), ("blue", "burgundy"), ("blue", "khaki"), ("blue", "yellow"), ("blue", "pink"),
    ("green", "brown"), ("khaki", "brown"), ("burgundy", "brown"), ("burgundy", "green"),
    ("pink", "burgundy"), ("khaki", "orange"), ("blue", "green"), ("purple", "pink"),
]}

# Что искать в каждом слоте: стиль -> слот -> запрос. "*" — запасной вариант для всех стилей.
GARMENTS = {
    "*": {"top": "футболка", "bottom": "джинсы", "dress": "платье", "bag": "сумка", "accessory": "шарф"},
    "casual": {"bottom": "джинсы", "bag": "рюкзак"},
    "classic": {"top": "рубашка", "bottom": "брюки классические", "bag": "сумка кожаная"},
    "sport": {"top": "худи спортивное", "bottom": "спортивные штаны", "bag": "рюкзак спортивный"},
    "street": {"top": "худи оверсайз", "bottom": "карго", "bag": "сумка через плечо"},
    "evening": {"top": "рубашка", "bottom": "брюки", "dress": "вечернее платье", "bag": "клатч"},
}
SEASONAL = {  # сезон -> слот -> запрос
    "winter": {"outerwear": "пуховик", "shoes": "ботинки зимние", "top": "свитер", "accessory": "шапка"},
    "autumn": {"outerwear": "куртка демисезонная", "shoes": "ботинки", "top": "свитшот"},
    "spring": {"outerwear": "ветровка", "shoes": "кроссовки", "top": "свитшот"},
    "summer": {"shoes": "кроссовки", "top": "футболка", "accessory": "очки солнцезащитные"},
}
STYLE_OVERRIDES = {  # (стиль, сезон) -> слот -> запрос; стиль важнее сезона
    ("classic", "winter"): {"outerwear": "пальто", "top": "рубашка"},
    ("classic", "autumn"): {"outerwear": "пальто", "shoes": "туфли"},
    ("classic", "spring"): {"outerwear": "тренч", "shoes": "туфли"},
    ("classic", "summer"): {"shoes": "лоферы", "top": "рубашка"},
    ("evening", "summer"): {"shoes": "туфли"},
    ("evening", "spring"): {"shoes": "туфли", "outerwear": "пиджак"},
    ("evening", "autumn"): {"shoes": "туфли", "outerwear": "пальто"},
    ("evening", "winter"): {"outerwear": "пальто"},
    ("sport", "summer"): {"bottom": "шорты спортивные"},
}
BUDGET_SHARE = {"outerwear": 0.35, "top": 0.15, "bottom": 0.2, "dress": 0.35, "shoes": 0.25,
                "bag": 0.1, "accessory": 0.05}
GENDER_WORD = {"male": "мужское", "female": "женское"}
WRONG_GENDER = {"male": ["женск", "для девоч"], "female": ["мужск", "для мальч"]}
MIN_PRICE = 100  # объявления «за 1 рубль» — обычно не настоящая цена
TOP_K = 6


class SearchClient(Protocol):
    def search(self, query: str, *, city: str = ..., pmin: int | None = ..., pmax: int | None = ...,
               limit: int = ...) -> list[Item]: ...


def needed_slots(wishes: Wishes) -> list[str]:
    owned = {o.slot for o in wishes.owned}
    wants_dress = "dress" in wishes.requested or "dress" in owned or (
        wishes.gender == "female" and wishes.style == "evening"
        and not {"top", "bottom"} & (owned | set(wishes.requested)))
    slots = ["dress"] if wants_dress else ["top", "bottom"]
    slots.append("shoes")
    if wishes.season != "summer" or "outerwear" in wishes.requested:
        slots.insert(0, "outerwear")
    slots += [s for s in ("bag", "accessory") if s in wishes.requested]
    return [s for s in slots if s not in owned]


def build_query(slot: str, wishes: Wishes) -> str:
    if slot in wishes.requested:
        parts = [wishes.requested[slot]]
    else:
        garment = {**GARMENTS["*"], **SEASONAL[wishes.season], **GARMENTS.get(wishes.style, {}),
                   **STYLE_OVERRIDES.get((wishes.style, wishes.season), {})}[slot]
        parts = [garment]
        if wishes.colors:
            parts.append(COLOR_RU[wishes.colors[0]])
    if wishes.gender:
        parts.append(GENDER_WORD[wishes.gender])
    size = wishes.shoe_size if slot == "shoes" else wishes.size
    if size and slot not in ("bag", "accessory"):
        parts.append(f"размер {size}")
    return " ".join(parts)


def color_harmony(a: str | None, b: str | None) -> float:
    if a is None or b is None:
        return 0.6
    if a in NEUTRALS or b in NEUTRALS:
        return 1.0
    if a == b:
        return 0.8
    return 0.9 if frozenset((a, b)) in GOOD_PAIRS else 0.2


def _item_score(item: Item, slot: str, wishes: Wishes) -> float:
    text = normalize(f"{item.title} {item.description}")
    score = 1.0 if item.image else 0.7
    color = detect_color(item.title)
    wanted = detect_color(wishes.requested.get(slot, "")) or (wishes.colors[0] if wishes.colors else None)
    if wanted:
        score += 1.0 if color == wanted else (0.0 if color else 0.3)
    if any(w in text for w in ("новый", "новая", "новое", "новые", "с биркой", "отличном состоянии")):
        score += 0.3
    return score


def _candidates(items: list[Item], slot: str, wishes: Wishes) -> list[Item]:
    seen, result = set(), []
    for item in items:
        title = normalize(item.title)
        if item.id in seen or item.price < MIN_PRICE or detect_slot(item.title) != slot:
            continue
        if wishes.gender and any(w in title for w in WRONG_GENDER[wishes.gender]):
            continue
        seen.add(item.id)
        result.append(item)
    result.sort(key=lambda i: (-_item_score(i, slot, wishes), i.price))
    return result[:TOP_K]


def _combo_score(combo: tuple[Item, ...], slots: list[str], wishes: Wishes) -> float:
    colors = [detect_color(i.title) for i in combo] + [o.color for o in wishes.owned]
    pairs = list(itertools.combinations(colors, 2))
    harmony = sum(color_harmony(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0
    accents = {c for c in colors if c and c not in NEUTRALS}
    score = sum(_item_score(i, s, wishes) for i, s in zip(combo, slots)) / len(combo)
    score += 2.0 * harmony - 0.5 * max(0, len(accents) - 2)
    if wishes.budget:
        # При прочих равных чуть предпочитаем более дешёвый комплект.
        score -= 0.3 * sum(i.price for i in combo) / wishes.budget
    return score


def pick_outfit(wishes: Wishes, client: SearchClient) -> Outfit:
    slots = needed_slots(wishes)
    notes: list[str] = []
    pool: dict[str, list[Item]] = {}
    share_total = sum(BUDGET_SHARE[s] for s in slots) or 1.0
    for slot in slots:
        # Потолок цены на слот — его доля бюджета с запасом, чтобы оставить выбор комбинатору.
        pmax = int(wishes.budget * min(1.0, 1.6 * BUDGET_SHARE[slot] / share_total)) if wishes.budget else None
        query = build_query(slot, wishes)
        found = _candidates(client.search(query, city=wishes.city, pmax=pmax), slot, wishes)
        if found:
            pool[slot] = found
        else:
            notes.append(f"По запросу «{query}» подходящих объявлений не нашлось.")

    filled = list(pool)
    best, best_score = None, float("-inf")
    for combo in itertools.product(*(pool[s] for s in filled)) if filled else ():
        if wishes.budget and sum(i.price for i in combo) > wishes.budget:
            continue
        score = _combo_score(combo, filled, wishes)
        if score > best_score:
            best, best_score = combo, score
    if best is None and filled:
        best = tuple(min(pool[s], key=lambda i: i.price) for s in filled)
        notes.append(f"В бюджет {wishes.budget} ₽ уложиться не удалось — показан самый дешёвый комплект.")

    picks = dict(zip(filled, best or ()))
    return Outfit(picks=picks, owned=wishes.owned, total=sum(i.price for i in picks.values()),
                  budget=wishes.budget, notes=notes)
