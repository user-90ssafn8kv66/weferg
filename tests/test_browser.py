import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from outfit_picker import AvitoBlockedError, AvitoClient, AvitoError, BrowserAvitoClient, make_client
from outfit_picker.avito import parse_search_page

pytest.importorskip("playwright")

FIXTURE = (Path(__file__).parent / "fixtures" / "search.html").read_text("utf-8")
BLOCKED = "<html><head><title>Доступ ограничен: проблема с IP</title></head><body>captcha</body></html>"
PAGES = {"/ok": FIXTURE, "/blocked": BLOCKED, "/empty": "<html><head><title>Ничего</title></head></html>"}


@pytest.fixture(scope="module")
def site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path, "").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def client(tmp_path, site, monkeypatch):
    monkeypatch.setattr("outfit_picker.avito.NO_RESULTS_WAIT", 1)
    client = BrowserAvitoClient(cache_dir=tmp_path, delay=(0, 0))
    try:
        client._fetch(site + "/ok")
    except AvitoError as error:
        pytest.skip(f"браузер недоступен: {error}")
    yield client
    client.close()


def test_browser_client_loads_pages_from_any_thread(client, site):
    results = []
    thread = threading.Thread(target=lambda: results.append(client._fetch(site + "/ok")))
    thread.start()
    thread.join(30)
    assert [i.id for i in parse_search_page(results[0])] == ["4001", "4002"]
    assert parse_search_page(client._fetch(site + "/empty")) == []


def test_browser_client_reports_block_and_keeps_working(client, site):
    with pytest.raises(AvitoBlockedError, match="--show-browser"):
        client._fetch(site + "/blocked")
    assert len(parse_search_page(client._fetch(site + "/ok"))) == 2


def test_browser_client_reports_launch_failure(tmp_path, monkeypatch):
    client = BrowserAvitoClient(cache_dir=tmp_path, delay=(0, 0))
    monkeypatch.setattr(client, "_launch", lambda playwright: (_ for _ in ()).throw(AvitoError("нет браузера")))
    with pytest.raises(AvitoError, match="нет браузера"):
        client.search("джинсы")
    client.close()


def test_make_client():
    assert isinstance(make_client("auto"), BrowserAvitoClient)
    assert type(make_client("http")) is AvitoClient
