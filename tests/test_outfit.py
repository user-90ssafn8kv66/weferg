from pathlib import Path

import pytest

from outfit_picker import AvitoBlockedError, AvitoClient, Item, parse_wishes, pick_outfit
from outfit_picker.avito import parse_search_page
from outfit_picker.cli import format_outfit
from outfit_picker.stylist import build_query, color_harmony, needed_slots

FIXTURE = (Path(__file__).parent / "fixtures" / "search.html").read_text("utf-8")


class FakeClient:
    def __init__(self, catalog):
        self.catalog = catalog
        self.calls = []

    def search(self, query, *, city="rossiya", pmin=None, pmax=None, limit=30):
        self.calls.append((query, city, pmax))
        for key, items in self.catalog.items():
            if key in query:
                return [i for i in items if not pmax or i.price <= pmax]
        return []


def item(id, title, price):
    return Item(id=str(id), title=title, price=price, url=f"https://www.avito.ru/x_{id}", image="i.jpg")


def test_parse_search_page():
    items = parse_search_page(FIXTURE)
    assert [i.id for i in items] == ["4001", "4002"]
    first = items[0]
    assert first.title == "Джинсы Levis 501 синие"
    assert first.price == 3500
    assert first.url == "https://www.avito.ru/moskva/odezhda_obuv_aksessuary/dzhinsy_levis_501_4001"
    assert first.location == "Москва"
    assert first.description == "Новые, с биркой"


def test_parse_wishes_text():
    w = parse_wishes("Хочу деловой мужской образ на осень до 20 тыс, размер 50. У меня есть чёрные туфли и белая рубашка")
    assert (w.gender, w.style, w.season, w.budget, w.size) == ("male", "classic", "autumn", 20000, "50")
    assert [(o.slot, o.color) for o in w.owned] == [("shoes", "black"), ("top", "white")]
    assert needed_slots(w) == ["outerwear", "bottom"]
    assert build_query("outerwear", w) == "пальто мужское размер 50"


def test_requested_garment_and_colors():
    w = parse_wishes("женский летний образ с красным платьем, в бежевых тонах", have=["белые кеды"])
    assert w.requested == {"dress": "красный платье"}
    assert w.colors == ["beige"]
    assert needed_slots(w) == ["dress"]
    assert build_query("dress", w) == "красный платье женское"


def test_unknown_owned_item():
    with pytest.raises(ValueError):
        parse_wishes(have=["что-то непонятное"])


def test_color_harmony():
    assert color_harmony("black", "red") == 1.0
    assert color_harmony("red", "green") < color_harmony("blue", "brown")


def test_pick_outfit_respects_budget_and_colors():
    client = FakeClient({
        "футболка": [item(1, "Футболка зеленая", 1500), item(2, "Футболка серая", 1500),
                     item(3, "Кепка к футболке", 300), item(4, "Футболка даром", 1)],
        "джинсы": [item(5, "Джинсы синие", 2500), item(6, "Джинсы черные женские", 1000),
                   item(7, "Джинсы черные", 9000)],
    })
    w = parse_wishes("повседневный мужской образ на лето до 5000", have=["красные кроссовки"], city="moskva")
    outfit = pick_outfit(w, client)
    assert set(outfit.picks) == {"top", "bottom"}
    # зелёный с красными кроссовками не сочетается, женские джинсы отфильтрованы
    assert outfit.picks["top"].id == "2"
    assert outfit.picks["bottom"].id == "5"
    assert outfit.total == 4000 <= w.budget
    assert all(city == "moskva" for _, city, _ in client.calls)
    assert "Итого: 4000 ₽ из 5000 ₽" in format_outfit(outfit)


def test_pick_outfit_reports_missing_slot():
    w = parse_wishes("летний образ", have=["белые кроссовки"])
    outfit = pick_outfit(w, FakeClient({"футболка": [item(1, "Футболка белая", 500)]}))
    assert set(outfit.picks) == {"top"}
    assert any("джинсы" in n for n in outfit.notes)


class _Response:
    def __init__(self, status_code, text):
        self.status_code, self.text = status_code, text

    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, response):
        self.headers, self.response, self.urls = {}, response, []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return self.response


def test_client_fetches_parses_and_caches(tmp_path):
    session = _Session(_Response(200, FIXTURE))
    client = AvitoClient(session=session, cache_dir=tmp_path, delay=(0, 0))
    assert len(client.search("джинсы", city="moskva", pmax=5000)) == 2
    assert len(client.search("джинсы", city="moskva", pmax=5000)) == 2
    assert len(session.urls) == 1
    assert session.urls[0].startswith("https://www.avito.ru/moskva/odezhda_obuv_aksessuary?q=")
    assert "pmax=5000" in session.urls[0]


def test_client_reports_block(tmp_path):
    client = AvitoClient(session=_Session(_Response(429, "Доступ ограничен: проблема с IP")),
                         cache_dir=tmp_path, delay=(0, 0))
    with pytest.raises(AvitoBlockedError):
        client.search("джинсы")
