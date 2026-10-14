# Agent access: the website for AI agents and models (ADR-135)

The owner (14 Oct 2026): "AI passes the sizes and the best cover's result comes straight back
into the CLI." An assistant (ChatGPT, Claude, Gemini, a shop's own bot, a coding agent in a
terminal) should be able to find the right cover for someone's furniture, say what it costs and
hand the person a link to order it, without scraping our pages and without ever paying itself.

The approved strategy has four layers. Phase 1 builds the first, third and fourth on the
preview only; phase 2 is the MCP server; phase 3 agent payments.

## The four layers

| Layer | What | Phase | Where |
|---|---|---|---|
| 1. API | `/api/v2`: versioned JSON, OpenAPI, errors with hints, limits | 1 (built) | `apps/api/coverapi/agent_api.py` |
| 2. MCP server | the same as tools for MCP clients (Claude, ChatGPT apps, IDEs) | 2 | not built |
| 3. Discovery | `/llms.txt`, `/llms-full.txt`, the measuring guide, cover pages with schema.org JSON-LD | 1 (built) | `agent_pages.py`, `agent_ld.py` |
| 4. CLI | `covers find/quote/kinds/link/cover`, table or JSON | 1 (built) | `clients/cli/` |

### 1. The API (phase 1)

`/api/v2` is a FastAPI sub-app of the studio, mounted at `/api/v2` (and at `/api/b2b/v2`
for a B2B session). Endpoints:

- `GET /kinds` — the kinds of furniture (sofa, corner_sofa, chair, side_table, footstool,
  lounger, daybed, dining_set, round_dining_set and the barbecues while they are on), each with
  the sizes it needs (required or not, the range in cm, what it means, how to measure it) and a
  link to the measuring guide. The kinds and their texts are `config/agent_kinds.json`
  (owner-editable); each maps to a configurator product (`config/quote_products.json`).
- `POST /match` — kind + sizes (+ `left_right`, colour, product name or URL as text) →
  a ranked list: existing covers (code, name, fit %, confidence, why, size differences in cm
  and mm, price, delivery promise, picture URL, 3D preview URL, page and order URL) and the
  made-to-measure cover (price, lead time, 3D, order URL). The matching is
  `coverengine.match` (ADR-064, ADR-114: SUNS, approved drawing covers, barbecues); the
  prices are the configurator's (`quote.proposal`) with the published fixed price for an
  existing cover (`shop.b2c_cover_price`, ADR-118) or the company's (`b2b.unit_price`).
- `POST /quote` — the made-to-measure price for sizes and options (vents, support balloons).
- `POST /order-link` — a link valid `limits.agent_link_hours` that opens the configurator
  prefilled, straight at the checkout. It creates no order and no payment.
- `GET /covers`, `GET /covers/{code}` (+ `/picture.jpg`, `/preview.glb`), `GET /preview.glb`.
- `POST /suggest` — sizes from photos or a product page: a partner key only (a paid AI call).
- `GET /openapi.json`, `GET /docs` (server-rendered, no scripts: the CSP holds).

Who may call and what they get:

| Caller | How | Limits | Prices | Photo/AI |
|---|---|---|---|---|
| anonymous | nothing | `agent_per_hour` per address (IPv6 /64), `agent_anon_per_day` all together | public B2C incl. VAT | no |
| partner key | `X-Api-Key` or `Authorization: Bearer` | `agent_key_per_hour`, `agent_key_per_day` | public B2C | `agent_key_photos_per_day`, `agent_key_eur_day` |
| B2B key | a partner key linked to a company | as a key | that company's ex VAT (ADR-104) | as a key |
| B2B session | the `b2b_session` cookie on `/api/b2b/v2` | as a key | that company's ex VAT | as a key |

### 2. MCP server (phase 2, not built)

A thin MCP server (Streamable HTTP, `/mcp` on the same Worker or the studio) with tools
`list_kinds`, `match_cover`, `quote`, `make_order_link` and `get_cover`, each calling the v2
API with the caller's key (or anonymously), so the limits, the scoping and the "never pays" rule
stay in one place. Tool descriptions from the OpenAPI descriptions. To decide then: the
hosting (the Worker can proxy; a Python MCP SDK in the studio is simpler), and whether partner
keys are passed by OAuth (MCP's authorisation spec) or as a header.

### 3. Discovery (phase 1)

- `/llms.txt`: the existing one plus a "For AI agents" section (API, OpenAPI, kinds, guide,
  covers, CLI, rules) where the agent API is on.
- `/llms-full.txt`: who we are, the API, the full measuring guide per kind, every existing
  cover with the furniture sizes it fits, the rules.
- `/measure`, `/measure/<kind>`: the measuring guide as pages (Product with the size ranges as
  `additionalProperty`, and a `HowTo`).
- `/covers`, `/covers/<code>`: the existing covers (ItemList; Product with `size`,
  `additionalProperty` sizes, `Offer` with price incl. VAT, `MadeToOrder`, the delivery
  promise as `shippingDetails` when set).

### 4. The CLI (phase 1)

`clients/cli/covers.py`, standard library only, installable with
`uv tool install ./clients/cli` or `pipx install ./clients/cli`:

```
covers find --kind sofa --width 230 --depth 90 --height 85 [--json]
covers quote --kind dining_set --width 220 --depth 100 --height 75 --support balloons
covers kinds [--kind corner_sofa]
covers link --kind sofa --width 230 --depth 90 --height 85 [--cover CODE]
covers cover CODE
```

`--api` (or `COVERS_API`) sets the base URL (default the preview), `--key` (or
`COVERS_API_KEY`) a partner key.

## Preview only, and switching it on for live

Two switches, both off for the live website:

1. **The Worker** (`apps/site`): `/api/v2/*`, `/api/b2b/v2/*`, `/llms-full.txt`, `/measure*`
   and `/covers*` pass to the studio only on the preview (`PREVIEW`), or on the live site with
   `AGENT_API = "1"` in `wrangler.toml` `[vars]`; elsewhere they are a 404 at the edge. The
   preview's `/llms.txt` comes from the studio (with the agent section); the live one is
   unchanged.
2. **The studio**: the shop setting `agent_api_enabled` (Settings → Website & API keys); the
   preview website always has it (its host and the Worker's key, as `bbq_enabled`).

For live after the owner's go: tick *API for AI agents* in Settings → Website & API keys, add
`AGENT_API = "1"` under `[vars]` in `apps/site/wrangler.toml`, `npm run deploy` in apps/site.

## Phase 3: agent payments (later; to verify first)

Today an agent never pays: it hands the person a link and the person pays with Mollie on our
site. Agentic checkout protocols are arriving: OpenAI's **Agentic Commerce Protocol (ACP)**
(with Stripe; a merchant exposes a checkout API and accepts a delegated, scoped payment token)
and Google's **Agent Payments Protocol (AP2)** / **Universal Commerce Protocol (UCP)** (signed
"mandates" that prove the person approved this purchase). What to verify before we build:

- Does **Mollie** support ACP's delegated payment tokens, AP2/UCP mandates, or network
  tokens (Visa Intelligent Commerce, Mastercard Agent Pay)? Without it we would need a second
  payment provider only for agents (and its fees, its payouts, our bookkeeping).
- Dutch and EU consumer law: the order button's wording ("bestellen met betaalverplichting",
  art. 6:230v BW), the 14-day right for existing covers versus none for made to measure
  (ADR-103): how does a mandate show the person the terms before the payment?
- Strong customer authentication (PSD2): who authenticates, and is a mandate enough?
- Fraud and returns: chargebacks on agent-made orders; a limit per mandate.
- Made-to-measure covers need sizes a person measured: an agent must not order on estimated
  sizes. Probably only existing covers at first.

Until then: no endpoint creates a paid order, and the order link expires.

## Open questions for the owner

See ADR-135 and the report of 14 Oct: the measuring texts, the left/right convention, the
made-to-measure lead time, the delivery promise on live, matching in shadow mode, partner keys
for whom, and the live switch.
