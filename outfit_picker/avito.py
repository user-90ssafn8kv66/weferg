"""Поиск объявлений на Авито через публичную страницу поиска."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import queue
import random
import re
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from .models import Item

BASE_URL = "https://www.avito.ru"
CATEGORY = "odezhda_obuv_aksessuary"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
ITEM_SELECTOR = '[data-marker="item"]'
BLOCK_MARK = "Доступ ограничен"
NO_RESULTS_WAIT = 8  # сколько секунд ждать объявления, прежде чем считать выдачу пустой


class AvitoError(RuntimeError):
    """Не удалось получить объявления с Авито."""


class AvitoBlockedError(AvitoError):
    """Авито отказал в доступе (ограничение по IP или капча)."""


def parse_search_page(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[Item] = []
    for node in soup.select(ITEM_SELECTOR):
        link = node.select_one('a[data-marker="item-title"]') or node.select_one('a[itemprop="url"]')
        price_meta = node.select_one('meta[itemprop="price"]')
        if not link or not link.get("href") or not price_meta:
            continue
        try:
            price = int(float(price_meta.get("content", "")))
        except ValueError:
            continue
        title = link.get("title") or link.get_text(" ", strip=True)
        title = re.sub(r"^Объявление «(.*)»$", r"\1", title)
        image = node.select_one("img[src]")
        desc = node.select_one('meta[itemprop="description"]')
        geo = (node.select_one('[data-marker="item-location"]') or node.select_one('[data-marker="item-address"]')
               or node.select_one('[class*="geo-root"]'))
        url = urljoin(BASE_URL, link["href"]).split("?")[0]
        items.append(Item(
            id=node.get("data-item-id") or url.rsplit("_", 1)[-1],
            title=title,
            price=price,
            url=url,
            image=image["src"] if image else None,
            location=geo.get_text(" ", strip=True) or None if geo else None,
            description=desc.get("content", "") if desc else "",
        ))
    return items


class AvitoClient:
    """Обычный HTTP-клиент. Авито чаще всего отклоняет его запросы — см. BrowserAvitoClient."""

    def __init__(self, *, delay: tuple[float, float] = (2.0, 4.0), cache_dir: str | Path | None = None,
                 cache_ttl: int = 3600, session: requests.Session | None = None, timeout: int = 20):
        self.delay = delay
        self.cache_dir = Path(cache_dir or Path.home() / ".cache" / "outfit_picker")
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
        self._last_request = 0.0

    def search_url(self, query: str, *, city: str = "rossiya", pmin: int | None = None,
                   pmax: int | None = None) -> str:
        params = {"q": query}
        if pmin:
            params["pmin"] = pmin
        if pmax:
            params["pmax"] = pmax
        return f"{BASE_URL}/{city}/{CATEGORY}?{urlencode(params)}"

    def search(self, query: str, *, city: str = "rossiya", pmin: int | None = None,
               pmax: int | None = None, limit: int = 30) -> list[Item]:
        url = self.search_url(query, city=city, pmin=pmin, pmax=pmax)
        cache_file = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if cache_file.exists() and time.time() - cache_file.stat().st_mtime < self.cache_ttl:
            return [Item(**raw) for raw in json.loads(cache_file.read_text("utf-8"))][:limit]

        # Пауза между запросами, чтобы не нагружать сайт.
        wait = self._last_request + random.uniform(*self.delay) - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            html = self._fetch(url)
        finally:
            self._last_request = time.time()
        items = parse_search_page(html)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps([vars(i) for i in items], ensure_ascii=False), "utf-8")
        return items[:limit]

    def _fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        if response.status_code in (403, 429) or BLOCK_MARK in response.text[:3000]:
            raise AvitoBlockedError(
                f"Авито отклонил запрос (HTTP {response.status_code}): обычные HTTP-клиенты он не пускает. "
                "Установите Playwright (`pip install playwright`), и поиск пойдёт через браузер.")
        response.raise_for_status()
        return response.text

    def close(self) -> None:
        pass


class BrowserAvitoClient(AvitoClient):
    """Открывает поиск в настоящем браузере: обычный HTTP-клиент Авито отклоняет даже с домашнего IP."""

    CHANNELS = ("chrome", "msedge", None)  # None — Chromium, установленный через `playwright install`

    def __init__(self, *, headless: bool = True, captcha_timeout: int = 120, **kwargs):
        super().__init__(**kwargs)
        self.headless = headless
        self.captcha_timeout = captcha_timeout
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _fetch(self, url: str) -> str:
        # Объекты Playwright привязаны к своему потоку, а веб-сервер обслуживает каждый запрос в новом.
        future: Future = Future()
        with self._lock:
            self._jobs.put((url, future))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        return future.result()

    def close(self) -> None:
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                self._jobs.put(None)
        if thread is not None:
            thread.join(timeout=15)

    def _run(self) -> None:
        job = None
        try:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise AvitoError("Не установлен Playwright: выполните `pip install playwright`.") from None
            with sync_playwright() as playwright:
                context = self._launch(playwright)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    while (job := self._jobs.get()) is not None:
                        try:
                            job[1].set_result(self._load(page, job[0]))
                        except AvitoBlockedError as error:
                            job[1].set_exception(error)
                        job = None
                finally:
                    context.close()
        except Exception as error:
            # Браузер не запустился или окно закрыли: отвечаем всем ожидающим, следующий поиск запустит его заново.
            if not isinstance(error, AvitoError):
                error = AvitoError(f"Не удалось получить страницу через браузер: {str(error).splitlines()[0]}")
            with self._lock:
                pending = [job] if job else []
                while not self._jobs.empty():
                    pending.append(self._jobs.get_nowait())
                self._thread = None
            for item in pending:
                if item is not None:
                    item[1].set_exception(error)

    def _launch(self, playwright):
        profile = self.cache_dir / "browser"
        profile.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for channel in self.CHANNELS:
            try:
                return playwright.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=self.headless, locale="ru-RU",
                    args=["--disable-blink-features=AutomationControlled", "--window-size=1100,800"])
            except Exception as error:
                last_error = error
        raise AvitoError(
            "Не удалось запустить браузер. Нужен Chrome или Edge (либо `playwright install chromium`); "
            f"если программа уже запущена в другом окне, закройте её. Подробности: {str(last_error).splitlines()[0]}")

    def _load(self, page, url: str) -> str:
        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        started = time.time()
        while not page.locator(ITEM_SELECTOR).count():
            blocked = BLOCK_MARK in page.title()
            if blocked and self.headless:
                raise AvitoBlockedError(
                    "Авито просит подтвердить, что вы не робот. Запустите программу с флагом --show-browser "
                    "и пройдите проверку в открывшемся окне — после этого поиск продолжится сам.")
            if time.time() - started > (self.captcha_timeout if blocked else NO_RESULTS_WAIT):
                if blocked:
                    raise AvitoBlockedError("Проверка Авито не пройдена за отведённое время. Попробуйте ещё раз.")
                break
            page.wait_for_timeout(500)
        return page.content()


def make_client(engine: str = "auto", *, headless: bool = True, **kwargs) -> AvitoClient:
    """engine: "browser", "http" или "auto" — браузер, если установлен Playwright."""
    if engine == "auto":
        engine = "browser" if importlib.util.find_spec("playwright") else "http"
    return BrowserAvitoClient(headless=headless, **kwargs) if engine == "browser" else AvitoClient(**kwargs)
