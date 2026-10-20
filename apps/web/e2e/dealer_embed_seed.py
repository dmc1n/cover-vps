"""A scratch data dir for e2e/dealer_embed.py (ADR-150): an admin `tester`, a B2B company
"Dealer Demo BV" and the dealer embed switched on. Never on live data.

    uv run python apps/web/e2e/dealer_embed_seed.py /tmp/embed-data
    COVER_DATA_DIR=/tmp/embed-data COVER_PORT=18391 uv run cover-web
"""

import sys
from pathlib import Path

from coverapi.auth import Auth
from coverapi.b2b import Store

data = Path(sys.argv[1])
if (data / "models").exists() and any((data / "models").iterdir()):
    sys.exit(f"{data} has models: give an empty scratch directory")
data.mkdir(parents=True, exist_ok=True)
auth = Auth(data / "app.db")
user = auth.add_user("tester", "Tester", "admin", "tester@example.com", True)
auth.set_password(auth.invite(user.id), "browser-test-password")
auth.set_setting("two_factor", False)  # a scratch server without mail
auth.set_setting(
    "shop",
    {
        "dealer_embed_enabled": True,
        "shipping": [{"country": "NL", "name": "Nederland", "eur": 9.95}],
    },
)
Store(data / "app.db").add_company(
    {
        "name": "Dealer Demo BV",
        "email": "orders@dealer-demo.example",
        "price_list": "b2b",
        "street": "Kade 1",
        "postcode": "1000 AA",
        "city": "Amsterdam",
        "country": "NL",
    },
    "active",
)
print("seeded", data)
