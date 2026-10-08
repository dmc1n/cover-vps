"""The consumer shop's legal pages as drafts (ADR-099): terms (algemene voorwaarden), privacy,
returns (herroepingsrecht), cookies, contact (imprint) and warranty, in Dutch and English; the
texts live in config/shop_legal.json.

Every draft starts with a clear "draft — to approve" line. A page shows its draft only while the
site's own content (the AI CMS) has no text for it; once the owner publishes a text of his own,
that text is shown instead. Company details are placeholders ({kvk}, {address}, ...) filled
from Shop settings → company; a detail not filled in yet shows as "[to fill in: ...]".

These are drafts written for Dutch consumer law (Boek 6 BW, afdeling 9A; EU 2011/83): prices
incl. VAT; no right of withdrawal for goods made to the consumer's specifications (art. 6:230p
sub f BW), but a 14-day right for covers from our standard range; the statutory warranty
(conformiteit, art. 7:17 BW). A lawyer or the owner must approve them before go-live.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FILE = Path(__file__).resolve().parents[3] / "config" / "shop_legal.json"
_DOC: dict[str, Any] = json.loads(_FILE.read_text(encoding="utf-8"))

PAGES = ("terms", "privacy", "returns", "cookies", "contact", "warranty")
DRAFT_MARK: dict[str, str] = _DOC["mark"]
MISSING = {"nl": "[nog in te vullen: {}]", "en": "[to fill in: {}]"}
FIELD_NAMES = {
    "company_name": {"nl": "handelsnaam", "en": "trade name"},
    "legal_name": {"nl": "statutaire naam", "en": "legal name"},
    "address": {"nl": "adres", "en": "address"},
    "kvk": {"nl": "KvK-nummer", "en": "Chamber of Commerce number"},
    "vat_number": {"nl": "btw-nummer", "en": "VAT number"},
    "email": {"nl": "e-mailadres", "en": "e-mail address"},
    "phone": {"nl": "telefoonnummer", "en": "phone number"},
}

DRAFTS: dict[str, dict[str, str]] = _DOC["pages"]


def _fields(company: dict[str, Any], lang: str) -> dict[str, str]:
    key = "nl" if lang == "nl" else "en"
    addr = ", ".join(
        str(x)
        for x in (
            company.get("street"),
            " ".join(str(y) for y in (company.get("postcode"), company.get("city")) if y),
            company.get("country"),
        )
        if x
    )
    given = {
        "company_name": company.get("name") or "",
        "legal_name": company.get("legal_name") or company.get("name") or "",
        "address": addr if company.get("street") else "",
        "kvk": company.get("kvk") or "",
        "vat_number": company.get("vat_number") or "",
        "email": company.get("email") or "",
        "phone": company.get("phone") or "",
    }
    return {k: v or MISSING[key].format(FIELD_NAMES[k][key]) for k, v in given.items()}


def fill(text: str, company: dict[str, Any], lang: str) -> str:
    """The company's details in a legal text ({kvk}, {address}, ...); others left alone."""
    for k, v in _fields(company, lang).items():
        text = text.replace("{" + k + "}", v)
    return text


def texts(content: dict[str, Any], company: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Every legal page in every language the content has: the owner's own text when there is
    one, else our draft (marked "draft — to approve"); the company's details filled in."""
    out: dict[str, dict[str, str]] = {}
    own = content.get("legal") or {}
    for page in PAGES:
        given = own.get(page) or {}
        langs = set(given) | set(DRAFTS[page])
        page_out = {}
        for lang in sorted(langs):
            text = str(given.get(lang) or "")
            if not text.strip() and lang in DRAFTS[page]:
                text = DRAFT_MARK[lang] + "\n\n" + DRAFTS[page][lang]
            page_out[lang] = fill(text, company, lang)
        out[page] = page_out
    return out


def is_draft(text: str) -> bool:
    return any(text.startswith(m) for m in DRAFT_MARK.values())
