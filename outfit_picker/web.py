"""Локальный веб-интерфейс: одна страница и JSON-эндпоинт поверх pick_outfit."""
from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .avito import AvitoError, make_client
from .cli import add_engine_arguments
from .stylist import SearchClient, pick_outfit
from .wishes import parse_wishes

INDEX = Path(__file__).with_name("index.html")
FIELDS = ("city", "budget", "gender", "style", "season", "size", "shoe_size")


def handle_request(payload: dict, client: SearchClient) -> tuple[int, dict]:
    """Возвращает HTTP-статус и тело ответа для запроса на подбор образа."""
    text = str(payload.get("wishes") or "").strip()
    have = [str(h).strip() for h in payload.get("have") or [] if str(h).strip()]
    if not text and not have:
        return 400, {"error": "Опишите пожелания или добавьте хотя бы одну вещь, которая у вас есть."}
    options = {k: payload.get(k) or None for k in FIELDS}
    try:
        if options["budget"] is not None:
            options["budget"] = int(options["budget"])
        outfit = pick_outfit(parse_wishes(text, have=have, **options), client)
    except ValueError as error:
        return 400, {"error": str(error)}
    except AvitoError as error:
        return 502, {"error": str(error)}
    except OSError as error:  # сеть недоступна, таймаут и т. п.
        return 502, {"error": f"Не удалось связаться с Авито: {error}"}
    return 200, outfit.to_dict()


def create_server(client: SearchClient, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?")[0] == "/":
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/api/outfit":
                self._send(404, b"Not found", "text/plain")
                return
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                if not isinstance(payload, dict):
                    raise ValueError
            except ValueError:
                status, body = 400, {"error": "Некорректный запрос."}
            else:
                status, body = handle_request(payload, client)
            self._send(status, json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def log_message(self, *args) -> None:
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="outfit-web", description="Веб-интерфейс подбора образа.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true", help="не открывать страницу интерфейса автоматически")
    add_engine_arguments(parser)
    args = parser.parse_args(argv)

    client = make_client(args.engine, headless=not args.show_browser)
    server = create_server(client, args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    print(f"Интерфейс запущен: {url} (Ctrl+C — остановить)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
