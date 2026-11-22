import json
import threading
import urllib.error
import urllib.request

import pytest

from outfit_picker import AvitoBlockedError, Item
from outfit_picker.web import create_server, handle_request


class FakeClient:
    def __init__(self, items=(), error=None):
        self.items, self.error = list(items), error

    def search(self, query, *, city="rossiya", pmin=None, pmax=None, limit=30):
        if self.error:
            raise self.error
        return self.items


ITEMS = [Item(id="1", title="Футболка белая", price=700, url="https://www.avito.ru/x_1"),
         Item(id="2", title="Джинсы синие", price=2500, url="https://www.avito.ru/x_2")]


def test_handle_request_returns_outfit():
    status, body = handle_request(
        {"wishes": "летний образ", "have": ["белые кроссовки", " "], "budget": "5000", "city": ""}, FakeClient(ITEMS))
    assert status == 200
    assert set(body["picks"]) == {"top", "bottom"}
    assert body["total"] == 3200 and body["budget"] == 5000
    assert body["owned"][0]["slot"] == "shoes"


@pytest.mark.parametrize("payload, client, status", [
    ({"wishes": "  "}, FakeClient(), 400),
    ({"have": ["нечто"]}, FakeClient(), 400),
    ({"wishes": "образ", "budget": "много"}, FakeClient(), 400),
    ({"wishes": "образ"}, FakeClient(error=AvitoBlockedError("блок")), 502),
    ({"wishes": "образ"}, FakeClient(error=ConnectionError("нет сети")), 502),
])
def test_handle_request_errors(payload, client, status):
    got, body = handle_request(payload, client)
    assert got == status and body["error"]


def test_server_serves_page_and_api():
    server = create_server(FakeClient(ITEMS), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "Образ с Авито" in page
        request = urllib.request.Request(base + "/api/outfit", data=json.dumps({"wishes": "летний образ"}).encode())
        assert json.load(urllib.request.urlopen(request))["total"] == 3200
        with pytest.raises(urllib.error.HTTPError) as bad:
            urllib.request.urlopen(urllib.request.Request(base + "/api/outfit", data=b"[]"))
        assert bad.value.code == 400
    finally:
        server.shutdown()
