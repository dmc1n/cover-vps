"""The website's pages for AI agents and the people they help (ADR-139): the measuring guide
(/measure and /measure/<kind>), the existing covers (/covers and /covers/<code>), each with its
schema.org JSON-LD, /llms-full.txt, and the API's docs (/api/v2/docs).

Plain server-rendered HTML without scripts, so a crawler or a model reads everything at once and
the website's CSP holds. On this server they live under /shop/ like the shop's own pages; the
Worker passes them only where the agent API is on (the preview until the owner's go). They
answer only where `agent_api.agent_on` (else a 404), and show the public prices only.
"""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from coverapi import agent_ld

STYLE = """
:root{color-scheme:light;--ink:#2b2620;--sand:#f6f1e8;--line:#d9cfbf;--muted:#5f564b;--accent:#7a4b1f}
*{box-sizing:border-box}body{margin:0;background:var(--sand);color:var(--ink);
font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:46rem;margin:0 auto;padding:1.5rem 1rem 4rem}
a{color:var(--accent)}h1{font-size:1.8rem;line-height:1.2;margin:.5rem 0 1rem}
h2{font-size:1.25rem;margin:2rem 0 .5rem}nav{font-size:.95rem;margin-bottom:1rem}
.muted{color:var(--muted)}dl{margin:0}dt{font-weight:600;margin-top:.9rem}dd{margin:.15rem 0 0}
table{border-collapse:collapse;width:100%;font-size:.95rem}
td,th{border-bottom:1px solid var(--line);
padding:.4rem .3rem;text-align:left;vertical-align:top}code{font-size:.9em}
.cta{display:inline-block;margin-top:1rem;padding:.6rem 1rem;border-radius:.5rem;
background:var(--ink);color:var(--sand);text-decoration:none}
"""


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def page(title: str, body: str, canonical: str, description: str, ld: str = "") -> HTMLResponse:
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(title)}</title>"
        f'<meta name="description" content="{_e(description)}">'
        f'<link rel="canonical" href="{_e(canonical)}">'
        f"<style>{STYLE}</style>{ld}</head><body><main>{body}</main></body></html>"
    )
    return HTMLResponse(doc, headers={"Cache-Control": "public, max-age=300"})


def install(app: FastAPI, auth: Any, sub: FastAPI) -> None:
    from coverapi.agent_api import RULES, agent_on
    from coverapi.shop import SHOP_DEFAULTS, SHOP_SETTING, merged

    def company() -> str:
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        return str(s["company"]["name"] or "S2DIO")

    def gate(request: Request, page: str | None = None) -> None:
        """404 where the agent API is off; a counted page (`page`) answers 429 over the
        anonymous limits."""
        from fastapi import HTTPException

        from coverapi.agent_api import ApiError

        if not agent_on(auth, request):
            raise HTTPException(404, "not here")
        if page is not None:
            try:
                sub.state.count_page(request, page)
            except ApiError as e:
                raise HTTPException(e.status, e.message, headers=e.headers) from None

    def kinds_of(request: Request) -> dict[str, Any]:
        out: dict[str, Any] = sub.state.kinds(request)
        return out

    def nav(site: str) -> str:
        return (
            f'<nav><a href="{_e(site)}">Home</a> · <a href="{_e(site)}measure">How to '
            f'measure</a> · <a href="{_e(site)}covers">Our covers</a> · '
            f'<a href="{_e(site)}configure">Design your cover</a></nav>'
        )

    # ---- the measuring guide ---------------------------------------------------------------
    @app.get("/shop/measure", include_in_schema=False)
    def measure(request: Request) -> HTMLResponse:
        gate(request, "/measure")
        doc = kinds_of(request)
        site = sub.state.site_root(request)
        g = doc["how_to_measure"]
        rows = "".join(
            f'<tr><td><a href="{_e(k["guide_url"])}">{_e(k["label"])}</a></td>'
            f"<td><code>{_e(k['kind'])}</code></td>"
            f"<td>{_e(', '.join(s['name'] for s in k['sizes'] if s['required'] and not s['required_when']))}</td></tr>"  # noqa: E501
            for k in doc["kinds"]
        )
        body = (
            f"{nav(site)}<h1>How to measure your furniture for a cover</h1>"
            f"<p>{_e(g['how'])}</p><p class=muted>{_e(g['units'])}</p><ul>"
            + "".join(f"<li>{_e(t)}</li>" for t in g["tips"])
            + "</ul><h2>Per kind of furniture</h2><table><tr><th>Furniture</th><th>Kind (API)</th>"
            f"<th>Sizes we need</th></tr>{rows}</table>"
            f"<p class=muted>For software and AI assistants: the same guide as JSON at "
            f'<a href="{_e(site)}api/v2/kinds">/api/v2/kinds</a>, the API at '
            f'<a href="{_e(site)}api/v2/docs">/api/v2/docs</a>.</p>'
        )
        return page(
            "How to measure for a cover",
            body,
            f"{site}measure",
            "How to measure garden furniture and barbecues for a made-to-measure cover.",
        )

    @app.get("/shop/measure/{kind}", include_in_schema=False)
    def measure_kind(kind: str, request: Request) -> HTMLResponse:
        gate(request, "/measure/{kind}")
        doc = kinds_of(request)
        k = next((x for x in doc["kinds"] if x["kind"] == kind), None)
        if k is None:
            from fastapi import HTTPException

            raise HTTPException(404, "no such kind")
        site = sub.state.site_root(request)
        items = "".join(
            f"<dt>{_e(s['name'])}"
            + (" (yes/no)" if s["type"] == "boolean" else f" · {s['min_cm']:g}–{s['max_cm']:g} cm")
            + (
                " · needed"
                if s["required"] and not s["required_when"]
                else f" · needed when {s['required_when']} is yes"
                if s["required_when"]
                else " · optional"
            )
            + f"</dt><dd>{_e(s['means'])} {_e(s['how_to_measure'])}</dd>"
            for s in k["sizes"]
        )
        hand = f"<h2>Left or right</h2><p>{_e(k['left_right'])}</p>" if k["left_right"] else ""
        k_ld = {**k, "order_url": f"{site}configure?product={k['product']}"}
        body = (
            f"{nav(site)}<h1>How to measure: {_e(k['label'])}</h1><p>{_e(k['how'])}</p>"
            f"<p class=muted>{_e(doc['how_to_measure']['how'])}</p>"
            f"<h2>The sizes</h2><dl>{items}</dl>"
            f'{hand}<a class=cta href="{_e(k_ld["order_url"])}">Design your cover</a>'
            f'<p class=muted>API: <code>POST /api/v2/match</code> with <code>"kind": '
            f'"{_e(k["kind"])}"</code> and these sizes.</p>'
        )
        return page(
            f"How to measure: {k['label']}",
            body,
            k["guide_url"],
            f"The sizes we need for a {k['label'].lower()} cover and how to measure them.",
            agent_ld.script_tags(agent_ld.kind_ld(k_ld, company())),
        )

    # ---- the existing covers ---------------------------------------------------------------
    @app.get("/shop/covers", include_in_schema=False)
    def covers_page(request: Request) -> HTMLResponse:
        gate(request, "/covers")
        site = sub.state.site_root(request)
        items = sub.state.covers(request)["covers"]
        rows = "".join(
            f'<tr><td><a href="{_e(c["page_url"])}">{_e(c["name"])}</a></td>'
            f"<td>{_e(', '.join(c['kinds']))}</td><td>{c['fits']['length_cm']:g} × "
            f"{c['fits']['width_cm']:g} × {c['fits']['height_cm']:g} cm</td></tr>"
            for c in items
        )
        body = (
            f"{nav(site)}<h1>Our existing covers</h1><p>Covers we already make, each for "
            "furniture of a known size. Is yours another size? We make it to measure.</p>"
            f"<table><tr><th>Cover</th><th>For</th><th>Fits furniture (L × W × H)</th></tr>{rows}"
            "</table>"
        )
        return page(
            "Our existing covers",
            body,
            f"{site}covers",
            "Outdoor furniture covers we already make, with the furniture sizes each fits.",
            agent_ld.script_tags([agent_ld.itemlist_ld(items, f"{site}covers")]),
        )

    @app.get("/shop/covers/{code}", include_in_schema=False)
    def cover_page(code: str, request: Request) -> HTMLResponse:
        from coverapi.agent_api import ApiError

        gate(request)
        site = sub.state.site_root(request)
        try:
            c = sub.state.cover_public(code, request)
        except ApiError as e:
            from fastapi import HTTPException

            if e.status == 404:  # noqa: PLR2004
                raise HTTPException(404, "no such cover") from None
            raise HTTPException(e.status, e.message, headers=e.headers) from None  # 429: limits
        f = c["fits"]
        pr = c.get("price") or {}
        price = (
            (
                f"€ {pr['amount_eur']:.2f} incl. VAT"
                + (" (indicative)" if pr.get("indicative") else "")
            )
            if pr
            else ""
        )
        body = (
            f"{nav(site)}<h1>{_e(c['name'])}</h1>"
            + (
                f'<img src="/api/v2/covers/{_e(c["code"])}/picture.jpg" alt="" '
                'style="max-width:100%;border-radius:.5rem">'
                if c["picture_url"]
                else ""
            )
            + f"<dl><dt>Fits</dt><dd>{_e(', '.join(c['kinds']))}: {f['length_cm']:g} × "
            f"{f['width_cm']:g} cm, {'up to ' if f['height_is_maximum'] else ''}"
            f"{f['height_cm']:g} cm high</dd>"
            + (f"<dt>Hand</dt><dd>{_e(c['left_right'])}</dd>" if c["left_right"] else "")
            + (f"<dt>Price</dt><dd>{_e(price)}</dd>" if price else "")
            + (f"<dt>Delivery</dt><dd>{_e(c['delivery'])}</dd>" if c["delivery"] else "")
            + f"<dt>Code</dt><dd><code>{_e(c['code'])}</code></dd></dl>"
            f'<a class=cta href="{_e(c["order_url"])}">Order this cover</a>'
            f'<p class=muted>Another size? <a href="{_e(site)}measure">Measure</a> and we make '
            "it to measure.</p>"
        )
        return page(
            c["name"],
            body,
            c["page_url"],
            f"{c['name']}: fits {f['length_cm']:g} × {f['width_cm']:g} × {f['height_cm']:g} cm.",
            agent_ld.script_tags([agent_ld.cover_ld(c, company())]),
        )

    # ---- llms-full.txt ---------------------------------------------------------------------
    @app.get("/llms-full.txt", include_in_schema=False)
    def llms_full(request: Request) -> PlainTextResponse:
        gate(request, "/llms-full.txt")
        site = sub.state.site_root(request)
        api = sub.state.api_root(request)
        doc = kinds_of(request)
        lines = [
            f"# {company()} / SUNS — premium made-to-measure outdoor covers",
            "",
            "> Covers for outdoor furniture and premium barbecues: the existing covers of "
            "our range (including the SUNS furniture range) and covers cut and sewn to "
            "measure in our own workshop. Give the sizes; get the best cover, its price "
            "and a link a person uses to order and pay.",
            "",
        ]
        lines += agent_section(site, api, sub.state.feeds_root(request))
        lines += [
            "",
            "## How to measure",
            "",
            doc["how_to_measure"]["how"],
            doc["how_to_measure"]["units"],
        ]
        lines += [f"- {t}" for t in doc["how_to_measure"]["tips"]]
        for k in doc["kinds"]:
            lines += [
                "",
                f"### {k['label']} (kind `{k['kind']}`)",
                "",
                k["how"],
                f"Guide: {k['guide_url']}",
            ]
            if k["aliases"]:
                lines.append("Also called: " + ", ".join(k["aliases"]))
            for s in k["sizes"]:
                need = (
                    "required"
                    if s["required"] and not s["required_when"]
                    else f"required when {s['required_when']} is true"
                    if s["required_when"]
                    else "optional"
                )
                rng = "" if s["type"] == "boolean" else f", {s['min_cm']:g}–{s['max_cm']:g} cm"
                lines.append(f"- `{s['name']}` ({need}{rng}): {s['means']} {s['how_to_measure']}")
            if k["left_right"]:
                lines.append(f"- `left_right`: {k['left_right']}")
        items = sub.state.covers(request)["covers"]
        lines += ["", "## Existing covers (the furniture sizes each fits: L × W × H cm)", ""]
        lines += [
            f"- `{c['code']}` {c['name']} — for {', '.join(c['kinds'])}: "
            f"{c['fits']['length_cm']:g} × {c['fits']['width_cm']:g} × "
            f"{'≤' if c['fits']['height_is_maximum'] else ''}{c['fits']['height_cm']:g} — "
            f"{c['page_url']}"
            for c in items
        ]
        lines += ["", "## Rules", ""] + [f"- {r}" for r in RULES]
        return PlainTextResponse(
            "\n".join(lines) + "\n", headers={"Cache-Control": "public, max-age=300"}
        )

    # ---- the API's docs --------------------------------------------------------------------
    @sub.get("/docs", include_in_schema=False)
    def docs(request: Request) -> HTMLResponse:
        spec = sub.openapi()
        api = sub.state.api_root(request)
        parts = [
            f"<h1>{_e(spec['info']['title'])} <span class=muted>v"
            f"{_e(spec['info']['version'])}</span></h1>",
            f'<p>Machine-readable: <a href="{_e(api)}/openapi.json">openapi.json</a> · '
            f'<a href="{_e(sub.state.feeds_root(request))}llms.txt">llms.txt</a> · base URL '
            f"<code>{_e(api)}</code></p>",
            "".join(
                f"<p>{_e(par)}</p>"
                for par in spec["info"]["description"].strip().replace("**", "").split("\n\n")
            ),
        ]
        schemas = spec.get("components", {}).get("schemas", {})
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                parts.append(
                    f"<h2><code>{method.upper()} /api/v2{_e(path)}</code></h2>"
                    f"<p><strong>{_e(op.get('summary', ''))}</strong></p>"
                    f"<p>{_e(op.get('description', ''))}</p>"
                )
                ref = (
                    op.get("requestBody", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                    .get("$ref", "")
                )
                model = schemas.get(ref.rsplit("/", 1)[-1]) if ref else None
                if model:
                    req = set(model.get("required", []))
                    rows = "".join(
                        f"<tr><td><code>{_e(n)}</code>{' *' if n in req else ''}</td>"
                        f"<td>{_e(f.get('description', ''))}</td></tr>"
                        for n, f in model.get("properties", {}).items()
                    )
                    parts.append(f"<table><tr><th>Field</th><th>Meaning</th></tr>{rows}</table>")
                for prm in op.get("parameters", []):
                    parts.append(
                        f"<p><code>{_e(prm['name'])}</code> ({_e(prm['in'])}): "
                        f"{_e(prm.get('description', ''))}</p>"
                    )
        ex = json.dumps({"kind": "sofa", "width": 230, "depth": 90, "height": 85}, indent=2)
        parts.append(
            "<h2>Example</h2><pre>curl -s -X POST " + _e(api) + "/match -H "
            "'Content-Type: application/json' -d '" + _e(ex) + "'</pre>"
        )
        return page(
            "Agent API docs",
            "".join(parts),
            f"{api}/docs",
            "The S2DIO covers API for AI agents: match, quote, order links.",
        )


def agent_section(site: str, api: str, feeds: str) -> list[str]:
    """The lines llms.txt and llms-full.txt share: the API, the CLI and the rules."""
    return [
        "## For AI agents",
        "",
        f"- [Agent API]({api}/docs): give the kind and sizes, get the best covers with price, "
        "fit and an order link. JSON, open without a key within limits.",
        f"- [OpenAPI]({api}/openapi.json)",
        f"- [Kinds and how to measure (JSON)]({api}/kinds)",
        f"- [How to measure]({site}measure)",
        f"- [Our existing covers]({site}covers)",
        f"- [Full text for models]({feeds}llms-full.txt)",
        "- CLI: `uv tool install <repo>/clients/cli`, then "
        "`covers find --kind sofa --width 230 --depth 90 --height 85 [--json]`.",
        "- Example: `POST " + api + '/match {"kind": "sofa", "width": 230, "depth": 90, '
        '"height": 85}`',
        "- Rules: open with limits (a free partner key gives more and photo recognition); public "
        "prices incl. VAT; an agent never orders or pays: a person opens the order link, gives "
        "the delivery address and pays on our site; no personal data.",
    ]
