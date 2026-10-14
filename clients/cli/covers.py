"""covers: the S2DIO / SUNS agent API from the command line (ADR-135, docs/handbook/agent-api.md).

Give the furniture's kind and sizes; get the best existing covers and the made-to-measure one,
with prices and order links, as a table or as JSON for agents. Standard library only. A person
always orders and pays on the site: nothing here orders or pays.
"""

import argparse
import json
import os
import shutil
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request

SIZES = (
    "width depth height length diameter front-height long-side short-side headrest-height "
    "headrest-length egg-diameter closed-height handle-depth tables-width table-length "
    "table-width table-height shelf-height hood-width lid-length fire-width"
).split()
CLOSING = "A person orders and pays on the site; nothing is ordered by this command."
DEFAULT_API = "https://preview.s2dio.living/api/v2"
Json = dict[str, object]


def call(
    method: str, path: str, body: Json | None = None, *, api: str, key: str | None
) -> tuple[int, dict[str, str], Json]:
    """Return decoded JSON for both successful and HTTP error responses."""
    headers = {"User-Agent": "s2dio-covers-cli/1.0", "Accept": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        api.rstrip("/") + path, data=data, headers=headers, method=method
    )
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            data = json.loads(raw)
        except ValueError:  # not our API's JSON (a proxy's page, a plain 404)
            data = {"error": "not_json", "message": f"HTTP {response.status}: not a JSON answer",
                    "hint": "Check --api: it should end in /api/v2."}  # fmt: skip
        return response.status, dict(response.headers.items()), data


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api", default=argparse.SUPPRESS)
    common.add_argument("--key", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    root = argparse.ArgumentParser(prog="covers", parents=[common])
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("find", "quote", "link", "kinds", "cover"):
        sub = commands.add_parser(command, parents=[common])
        if command == "cover":
            sub.add_argument("code")
            continue
        sub.add_argument("--kind", required=command != "kinds")
        if command == "kinds":
            continue
        for size in SIZES:
            sub.add_argument("--" + size, type=float)
        for flag in ("chairs", "headrest", "side-tables", "square"):
            sub.add_argument("--" + flag, action=argparse.BooleanOptionalAction, default=None)
        sub.add_argument("--size", action="append", default=[], type=size_pair)
        sub.add_argument("--unit", choices=("cm", "mm"))
        sub.add_argument("--left-right", choices=("left", "right"))
        for field in ("colour", "lang"):
            sub.add_argument("--" + field)
        if command == "find":
            sub.add_argument("--product-name")
            sub.add_argument("--product-url")
            sub.add_argument("--top", type=int)
        else:
            sub.add_argument("--no-vents", dest="vents", action="store_false")
            sub.add_argument("--support", choices=("none", "balloons"), default="none")
            if command == "link":
                sub.add_argument("--cover", dest="cover_code")
    return root


def size_pair(value: str) -> tuple[str, float | bool]:
    name, sep, raw = value.partition("=")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError("size must be name=number or name=true/false")
    if raw.lower() in ("true", "false"):
        return name.replace("-", "_"), raw.lower() == "true"
    try:
        number = float(raw)
        if not -float("inf") < number < float("inf"):
            raise ValueError
        return name.replace("-", "_"), number
    except ValueError as error:
        raise argparse.ArgumentTypeError("size must be name=number or name=true/false") from error


def price(value: Json | None) -> str:
    if not value:
        return "-"
    amount = float(value["amount_eur"])
    vat = "incl. VAT" if value.get("vat_included") else "ex VAT"
    suffix = " (indicative)" if value.get("indicative") else ""
    return f"{value.get('currency', 'EUR')} {amount:.2f} {vat}{suffix}"


def sizes_text(sizes: Json) -> str:
    return ", ".join(f"{name} {value}" for name, value in sizes.items())


def show_find(data: Json) -> None:
    given = {k: v for k, v in data.get("your_sizes", {}).items() if not str(k).endswith("_mm")}
    print(f"{data.get('kind', '')}: {sizes_text(given)}")
    rows = []
    for result in data.get("results", []):
        rows.append(
            [
                str(result.get("rank", "")),
                str(result.get("type", "")).replace("_", " "),
                str(result.get("code") or "-"),
                str(result.get("name", "")),
                f"{result.get('fit_pct', '-')}%",
                price(result.get("price")),
                str(result.get("delivery") or result.get("lead_time") or "-"),
            ]
        )
    headings = ["#", "type", "code", "name", "fit %", "price", "delivery/lead time"]
    widths = [max(len(row[i]) for row in [headings, *rows]) for i in range(7)]
    available = shutil.get_terminal_size().columns - sum(widths) + widths[3] - 18
    widths[3] = max(20, min(widths[3], available))
    for row in [headings, *rows]:
        row = row.copy()
        if len(row[3]) > widths[3]:
            row[3] = textwrap.shorten(row[3], width=widths[3], placeholder="...")
        print(" | ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))
    for result in data.get("results", []):
        print(f"  #{result.get('rank')} order: {result.get('order_url', '-')}")
        if result.get("type") == "existing" and result.get("why"):
            print(f"  {result['why']}")
    notes(data)
    for assumed in data.get("assumed", []):
        print(f"assumed: {assumed['size']} {assumed['value_cm']} cm ({assumed['why']})")
    print(CLOSING)


def notes(data: Json) -> None:
    for note in data.get("notes", []):
        print(f"note: {note}")


def show(command: str, data: Json, kind: str | None) -> int:
    if command == "find":
        show_find(data)
    elif command == "quote":
        print(f"Price: {price(data.get('price'))}")
        if data.get("support_price"):
            print(f"Support: {price(data['support_price'])}")
        print(f"Lead time: {data.get('lead_time') or '-'}")
        print(f"Cover sizes (cm): {sizes_text(data.get('cover_sizes_cm', {}))}")
        print(f"Order: {data.get('order_url', '-')}")
        notes(data)
    elif command == "link":
        print(f"Order link (valid until {data.get('expires_at')}): {data.get('order_url')}")
        for step in data.get("what_happens_next", []):
            print(f"- {step}")
        print(CLOSING)
    elif command == "cover":
        print(f"{data.get('name')} ({data.get('code')})")
        fits = {k: v for k, v in data.get("fits", {}).items() if str(k).endswith("_cm")}
        print(f"Fits furniture: {sizes_text(fits)}")
        print(f"Price: {price(data.get('price'))}")
        print(f"Delivery: {data.get('delivery') or '-'}")
        print(f"Page: {data.get('page_url')}")
        print(f"Order: {data.get('order_url')}")
    elif command == "kinds":
        kinds = data.get("kinds", [])

        def norm(name: object) -> str:
            return "_".join(str(name).casefold().replace("-", " ").split())

        selected = [
            item
            for item in kinds
            if kind is None
            or norm(kind) in [norm(name) for name in [item["kind"], *item.get("aliases", [])]]
        ]
        if not selected:
            print(
                f"error: unknown kind {kind}; kinds: " + ", ".join(k["kind"] for k in kinds),
                file=sys.stderr,
            )
            return 2
        for item in selected:
            print(f"{item['kind']} — {item.get('label', '')}")
            print("Aliases: " + ", ".join(item.get("aliases", [])))
            for size in item.get("sizes", []):
                required = "required" if size.get("required") else "optional"
                if size.get("required_when"):
                    required = f"required when {size['required_when']}"
                print(
                    f"  {size['name']} ({required}) "
                    f"{size.get('min_cm', '-')}–{size.get('max_cm', '-')} cm: "
                    f"{size.get('means', '')} / {size.get('how_to_measure', '')}"
                )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    api = getattr(args, "api", os.environ.get("COVERS_API", DEFAULT_API))
    key = getattr(args, "key", os.environ.get("COVERS_API_KEY"))
    as_json = getattr(args, "json", False)
    body = {
        name: value
        for name, value in vars(args).items()
        if name not in {"command", "api", "key", "json", "size", "code"} and value is not None
    }
    body.update(dict(getattr(args, "size", [])))
    paths = {"find": "/match", "quote": "/quote", "link": "/order-link", "kinds": "/kinds"}
    path = paths.get(
        args.command, "/covers/" + urllib.parse.quote(getattr(args, "code", ""), safe="")
    )
    try:
        status, headers, data = call(
            "GET" if args.command in ("kinds", "cover") else "POST",
            path,
            None if args.command in ("kinds", "cover") else body,
            api=api,
            key=key,
        )
    except (OSError, ValueError, urllib.error.URLError) as error:
        reason = str(getattr(error, "reason", error))
        message = f"could not reach {api}: {reason}"
        if key:
            message = message.replace(key, "[redacted]")
        if as_json:
            print(json.dumps({"error": "network_error", "message": message}, indent=2))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    if not 200 <= status < 300:
        if not as_json:
            print(
                f"error: {data.get('message', data.get('error', 'request failed'))}",
                file=sys.stderr,
            )
            if data.get("hint"):
                print(f"hint: {data['hint']}", file=sys.stderr)
            retry = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
            if status == 429 and retry:
                print(f"retry after {retry} s", file=sys.stderr)
        return 3 if status == 429 else 2 if 400 <= status < 500 else 1
    return 0 if as_json else show(args.command, data, getattr(args, "kind", None))


if __name__ == "__main__":
    sys.exit(main())
