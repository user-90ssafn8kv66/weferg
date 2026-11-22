from __future__ import annotations

import argparse
import json
import sys

from .avito import AvitoError, make_client
from .models import SLOT_NAMES, Outfit
from .stylist import pick_outfit
from .wishes import parse_wishes


def format_outfit(outfit: Outfit) -> str:
    lines = []
    for owned in outfit.owned:
        lines.append(f"{SLOT_NAMES[owned.slot]}: {owned.text} (уже есть)")
    for slot, item in outfit.picks.items():
        place = f", {item.location}" if item.location else ""
        lines.append(f"{SLOT_NAMES[slot]}: {item.title} — {item.price} ₽{place}\n  {item.url}")
    budget = f" из {outfit.budget} ₽" if outfit.budget else ""
    lines.append(f"Итого: {outfit.total} ₽{budget}")
    lines += [f"! {note}" for note in outfit.notes]
    return "\n".join(lines)


def add_engine_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", choices=["auto", "browser", "http"], default="auto",
                        help="как открывать Авито: через браузер (по умолчанию, если установлен Playwright) или по HTTP")
    parser.add_argument("--show-browser", action="store_true",
                        help="показать окно браузера — нужно, если Авито просит пройти проверку")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="outfit", description="Подбирает образ из объявлений Авито по пожеланиям и имеющимся вещам.")
    parser.add_argument("wishes", nargs="?", default="",
                        help='пожелания, например: "деловой образ на осень до 20000, есть черные туфли"')
    parser.add_argument("--have", action="append", default=[], metavar="ВЕЩЬ",
                        help="вещь, которая уже есть (можно указать несколько раз)")
    parser.add_argument("--city", default=None, help="город в адресе Авито, например moskva (по умолчанию вся Россия)")
    parser.add_argument("--budget", type=int, default=None, help="бюджет на весь образ, ₽")
    parser.add_argument("--gender", choices=["male", "female"], default=None)
    parser.add_argument("--style", choices=["casual", "classic", "sport", "street", "evening"], default=None)
    parser.add_argument("--season", choices=["winter", "spring", "summer", "autumn"], default=None)
    parser.add_argument("--size", default=None, help="размер одежды")
    parser.add_argument("--shoe-size", default=None, help="размер обуви")
    parser.add_argument("--json", action="store_true", help="вывести результат в JSON")
    add_engine_arguments(parser)
    args = parser.parse_args(argv)

    if not args.wishes and not args.have:
        parser.error("укажите пожелания или хотя бы одну вещь через --have")
    client = make_client(args.engine, headless=not args.show_browser)
    try:
        wishes = parse_wishes(args.wishes, have=args.have, city=args.city, budget=args.budget,
                              gender=args.gender, style=args.style, season=args.season,
                              size=args.size, shoe_size=args.shoe_size)
        outfit = pick_outfit(wishes, client)
    except (AvitoError, ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        client.close()
    print(json.dumps(outfit.to_dict(), ensure_ascii=False, indent=2) if args.json else format_outfit(outfit))
    return 0 if outfit.picks else 2


if __name__ == "__main__":
    sys.exit(main())
