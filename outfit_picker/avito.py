"""Поиск объявлений на Авито через публичную страницу поиска."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from .models import Item

BASE_URL = "https://www.avito.ru"
CATEGORY = "odezhda_obuv_aksessuary"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")


class AvitoBlockedError(RuntimeError):
    """Авито отказал в доступе (ограничение по IP или капча)."""


def parse_search_page(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[Item] = []
    for node in soup.select('[data-marker="item"]'):
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
        geo = node.select_one('[class*="geo-root"]') or node.select_one('[data-marker="item-address"]')
        url = urljoin(BASE_URL, link["href"]).split("?")[0]
        items.append(Item(
            id=node.get("data-item-id") or url.rsplit("_", 1)[-1],
            title=title,
            price=price,
            url=url,
            image=image["src"] if image else None,
            location=geo.get_text(" ", strip=True) if geo else None,
            description=desc.get("content", "") if desc else "",
        ))
    return items


class AvitoClient:
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
        response = self.session.get(url, timeout=self.timeout)
        self._last_request = time.time()

        if response.status_code in (403, 429) or "Доступ ограничен" in response.text[:3000]:
            raise AvitoBlockedError(
                f"Авито ограничил доступ (HTTP {response.status_code}). Обычно так бывает при запросах "
                "с серверных IP или слишком частых запросах: запустите с домашнего подключения и повторите позже.")
        response.raise_for_status()
        items = parse_search_page(response.text)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps([vars(i) for i in items], ensure_ascii=False), "utf-8")
        return items[:limit]
