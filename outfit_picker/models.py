from __future__ import annotations

from dataclasses import asdict, dataclass, field

SLOTS = ("outerwear", "top", "bottom", "dress", "shoes", "bag", "accessory")

SLOT_NAMES = {
    "outerwear": "Верхняя одежда",
    "top": "Верх",
    "bottom": "Низ",
    "dress": "Платье",
    "shoes": "Обувь",
    "bag": "Сумка",
    "accessory": "Аксессуар",
}


@dataclass
class Item:
    """Объявление с Авито."""

    id: str
    title: str
    price: int
    url: str
    image: str | None = None
    location: str | None = None
    description: str = ""


@dataclass
class OwnedItem:
    """Вещь, которая уже есть у пользователя."""

    text: str
    slot: str
    color: str | None = None


@dataclass
class Wishes:
    text: str = ""
    gender: str | None = None  # "male" | "female"
    style: str = "casual"
    season: str = "summer"
    colors: list[str] = field(default_factory=list)
    budget: int | None = None
    size: str | None = None
    shoe_size: str | None = None
    city: str = "rossiya"
    owned: list[OwnedItem] = field(default_factory=list)
    # Конкретные вещи, названные в пожеланиях: слот -> поисковая фраза
    requested: dict[str, str] = field(default_factory=dict)
    # Незнакомый стиль или бренд: слова добавляются к каждому поисковому запросу
    keywords: str = ""


@dataclass
class Outfit:
    picks: dict[str, Item]
    owned: list[OwnedItem]
    total: int
    budget: int | None
    notes: list[str] = field(default_factory=list)
    style: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
