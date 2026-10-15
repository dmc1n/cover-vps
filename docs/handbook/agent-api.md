# The API and MCP server for AI agents (ADR-139, ADR-145)

AI assistants and their users can ask our website which cover fits a piece of furniture: they
pass the kind and the sizes, and the best covers come straight back with a price and a link the
person uses to order and pay. For now this is **on the preview website only**
(https://preview.s2dio.living). The plan with all four layers: [docs/plans/agent-access.md](../plans/agent-access.md).

## What is there

| Address (on the preview) | What |
|---|---|
| `/api/v2/docs` | the API's documentation, for people and models |
| `/api/v2/openapi.json` | the same, machine-readable (OpenAPI 3.1) |
| `/api/v2/kinds` | the kinds of furniture, the sizes each needs, how to measure (JSON) |
| `POST /api/v2/match` | kind + sizes → the best existing covers and made to measure |
| `POST /api/v2/quote` | the made-to-measure price for sizes and options |
| `POST /api/v2/order-link` | a link (valid 24 h) that opens the checkout prefilled |
| `/api/v2/covers`, `/api/v2/covers/<code>` | our existing covers, one cover's facts and price |
| `/measure`, `/measure/<kind>` | the measuring guide as pages |
| `/covers`, `/covers/<code>` | the existing covers as pages (with schema.org data) |
| `/llms.txt`, `/llms-full.txt` | short and full texts for AI assistants |
| `/mcp` | the MCP server for Claude, ChatGPT and other assistants (below) |

Example (no key needed):

```
curl -s -X POST https://preview.s2dio.living/api/v2/match \
  -H 'Content-Type: application/json' \
  -d '{"kind": "sofa", "width": 230, "depth": 90, "height": 85}'
```

The answer lists, best first, each existing cover that fits (its fit in %, why, the size
differences, the price incl. VAT, the delivery promise, a picture, a 3D preview, an order link)
and the made-to-measure cover (price, lead time, order link). A fit under 90 % is marked
"possible"; under 80 % it is not listed. Missing or wrong sizes give an error that says what to
do ("depth missing for kind sofa", with how to measure it).

## The MCP server: the shop inside Claude, ChatGPT and other assistants (ADR-145)

MCP (Model Context Protocol) is how assistants such as Claude and ChatGPT use outside services
as tools. Our MCP server is at **https://preview.s2dio.living/mcp** (preview only, like the
API). It offers six tools, each the same as one API call, with the same limits and prices:

| Tool | What it does |
|---|---|
| `list_kinds` | the kinds of furniture, the sizes each needs and how to measure them |
| `find_cover` | kind + sizes (cm) → the best existing covers and made to measure, with prices and order links |
| `get_quote` | the made-to-measure price for sizes and options |
| `get_cover` | one existing cover by its code |
| `create_order_link` | a 24-hour link that opens the checkout prefilled; **a person orders and pays** |
| `suggest_from_photo` | kind and sizes from a product page or photos: a **partner key only** |

**Add it to Claude (claude.ai or the Claude Desktop app):** Settings → Connectors → *Add custom
connector*; name "S2DIO covers", URL `https://preview.s2dio.living/mcp`, no authentication. In a
chat, switch it on under the tools button and ask, for example: *"Which S2DIO cover fits my
sofa of 230 × 90 × 85 cm?"* (On Team/Enterprise plans an owner adds the connector for the
organisation first.)

**Add it to Claude Code (terminal):**

```
claude mcp add --transport http s2dio-covers https://preview.s2dio.living/mcp
# with a partner key (higher limits, photo recognition, a B2B key: that company's prices):
claude mcp add --transport http s2dio-covers https://preview.s2dio.living/mcp \
  --header "Authorization: Bearer cvk_…"
```

**Add it to ChatGPT:** Settings → Apps & Connectors → Advanced settings → turn on *Developer
mode*; then *Create* (a connector): name "S2DIO covers", URL `https://preview.s2dio.living/mcp`,
authentication *No authentication*. In a chat choose it under the + menu (Developer mode).

Claude.ai and ChatGPT connectors cannot send our partner key (they only know OAuth or no
login), so they use the server anonymously: public prices and the anonymous limits. Partner
keys work where a header can be set: Claude Code, the Claude API's MCP connector
(`authorization_token`), the OpenAI Responses API (`headers`), and the official SDKs.

Try it without an assistant (the official MCP Inspector, in a terminal):

```
npx @modelcontextprotocol/inspector --cli https://preview.s2dio.living/mcp --transport http \
  --method tools/call --tool-name find_cover --tool-arg kind=sofa --tool-arg width=230 \
  --tool-arg depth=90 --tool-arg height=85
```

The same rules hold as for the API: open with limits (each tool call counts as one API
request; the protocol's own messages have a separate, generous hourly cap,
`limits.agent_mcp_per_hour`), no personal data, an agent never pays. On the live website
`/mcp` is a 404 until the API is switched on there (below).

## The command line

```
uv tool install ./clients/cli        # or: pipx install ./clients/cli
covers find --kind sofa --width 230 --depth 90 --height 85
covers find --kind sofa --width 230 --depth 90 --height 85 --json
covers kinds --kind corner_sofa
covers link --kind sofa --width 230 --depth 90 --height 85
```

## The rules

- **Open without a key, with limits:** 60 requests an hour per address and 1,000 a day for all
  anonymous use together (`limits.agent_per_hour`, `limits.agent_anon_per_day` in
  config/defaults.yaml, server-only). The answers carry `RateLimit-*` headers; over the limit
  a 429 with `Retry-After`.
- **No photo or AI recognition without a key** (it costs money). With a partner key:
  `POST /api/v2/suggest` with up to 3 photos or a product page, at most
  `limits.agent_key_photos_per_day` a day and `limits.agent_key_eur_day` of AI per key a day;
  the month's AI budget still stops everything.
- **Prices:** the public prices incl. VAT. A key linked to a B2B customer, or that customer's
  B2B login (on `/api/b2b/v2`), gets that customer's own prices ex VAT and order links into the
  B2B shop; no other caller ever sees them.
- **A person always pays.** An order link opens our configurator with the choices made; the
  person checks them, gives the delivery address and pays on the site (Mollie). B2B: the
  person logs in and orders on account. No API call creates an order or a payment.
- **No personal data:** the API accepts no name, e-mail or address (an unknown field is
  refused) and answers none. No cost or margin is ever in an answer.

## Partner keys (Settings → Website & API keys)

Under **API for AI agents: partner keys** an admin makes a key: a name (who it is for) and,
for a business customer, their B2B account. The key is shown once; give it to the partner.
**Revoke** stops it at once. The table below shows the requests per day for the last 7 days,
per key and "anonymous" (counts only: no addresses, no contents). The limits are shown
there and set in config/defaults.yaml.

The partner sends the key as `X-Api-Key: cvk_…` (or `Authorization: Bearer cvk_…`). A wrong or
revoked key is refused (not treated as anonymous), and a key whose B2B account is blocked too.

## Switching it on for the live website (after the owner's go)

1. Settings → Website & API keys: tick **API for AI agents**.
2. In `apps/site/wrangler.toml` under `[vars]`: `AGENT_API = "1"`, then `npm run deploy` in
   apps/site.

Until both are done the live website answers 404 on these addresses (the MCP server `/mcp`
included) and its `/llms.txt` is unchanged.

## Lead time and delivery promise

- The made-to-measure lead time the API states comes from **Made-to-measure lead time** (per
  language) in Settings → Website & API keys; empty: "confirmed after the order".
- The delivery promise of an existing cover is the shop's **Delivery promise** (Settings →
  Company & shop, ADR-118); empty: none is stated.

## The measuring guide

The texts are in `config/agent_kinds.json`: per kind its sizes, what each means and how to
measure it, drafted from what the configurator asks. Edit them there (one commit); the API,
the pages and llms-full.txt follow.
