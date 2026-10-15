"""The JSON-LD of the website's cover and measuring pages (ADR-139).

These pure functions describe public products and measuring instructions using
only the supplied public fields, ready for JSON serialization.
"""

import json
from typing import Any

_CONTEXT = "https://schema.org"
_CATEGORY = "Outdoor furniture cover"
_MATERIAL = "Sunbrella Coverlast: polyester with an acrylic coating"


def _number(value: float) -> int | float:
    return int(value) if value == int(value) else value


def _product(name: str, url: str, company: str) -> dict[str, Any]:
    return {
        "@context": _CONTEXT,
        "@type": "Product",
        "name": name,
        "url": url,
        "brand": {"@type": "Brand", "name": company},
        "category": _CATEGORY,
        "material": _MATERIAL,
    }


def cover_ld(cover: dict[str, Any], company: str = "S2DIO") -> dict[str, Any]:
    """Describe an existing cover and its optional public offer."""
    node = _product(cover["name"], cover["page_url"], company)
    node.update(sku=cover["code"], productID=cover["code"])
    fits = cover["fits"]
    length, width, height = (_number(fits[f"{axis}_cm"]) for axis in ("length", "width", "height"))
    node["size"] = f"{length} × {width} × {height} cm"
    dimensions = (
        f"{length} × {width} cm, up to {height} cm high"
        if fits["height_is_maximum"]
        else node["size"]
    )
    hand = cover["left_right"]
    handedness = f" ({hand} hand)" if hand else ""
    node["description"] = (
        f"Cover for a {', '.join(cover['kinds'])}{handedness} that fits furniture of {dimensions}"
    )
    properties: list[dict[str, Any]] = []
    for axis, value in zip(("length", "width", "height"), (length, width, height), strict=True):
        value_key = "maxValue" if axis == "height" and fits["height_is_maximum"] else "value"
        properties.append(
            {
                "@type": "PropertyValue",
                "name": f"Fits furniture {axis}",
                value_key: value,
                "unitCode": "CMT",
                "unitText": "cm",
            }
        )
    if hand:
        properties.append({"@type": "PropertyValue", "name": "Hand", "value": hand})
    node["additionalProperty"] = properties
    if cover["picture_url"]:
        node["image"] = cover["picture_url"]
    price = cover.get("price")
    if price is not None:
        amount = f"{price['amount_eur']:.2f}"
        offer: dict[str, Any] = {
            "@type": "Offer",
            "price": amount,
            "priceCurrency": "EUR",
            "url": cover["order_url"],
            "availability": f"{_CONTEXT}/MadeToOrder",
            "itemCondition": f"{_CONTEXT}/NewCondition",
            "priceSpecification": {
                "@type": "UnitPriceSpecification",
                "price": amount,
                "priceCurrency": "EUR",
                "valueAddedTaxIncluded": price["vat_included"],
            },
        }
        if price["indicative"]:
            offer["description"] = "Indicative price"
        if cover["delivery"]:
            offer["shippingDetails"] = {
                "@type": "OfferShippingDetails",
                "description": cover["delivery"],
            }
        node["offers"] = offer
    return node


def kind_ld(kind: dict[str, Any], company: str = "S2DIO") -> list[dict[str, Any]]:
    """Describe a made-to-measure product and the steps for measuring it."""
    product = _product(f"Made-to-measure cover: {kind['label']}", kind["guide_url"], company)
    product["description"] = kind["how"]
    properties: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for position, size in enumerate(kind["sizes"], start=1):
        if size["type"] == "number":
            prop: dict[str, Any] = {
                "@type": "PropertyValue",
                "name": f"{size['name']} (cm)",
                "unitCode": "CMT",
                "unitText": "cm",
                "description": size["means"],
            }
            for source, target in (("min_cm", "minValue"), ("max_cm", "maxValue")):
                if size[source] is not None:
                    prop[target] = _number(size[source])
            properties.append(prop)
        text = f"{size['means']} {size['how_to_measure']}"
        if size["required_when"]:
            text += f" (only when {size['required_when']} is true)"
        steps.append(
            {"@type": "HowToStep", "position": position, "name": size["name"], "text": text}
        )
    product["additionalProperty"] = properties
    product["offers"] = {
        "@type": "AggregateOffer",
        "priceCurrency": "EUR",
        "availability": f"{_CONTEXT}/MadeToOrder",
        "url": kind["order_url"],
    }
    howto = {
        "@context": _CONTEXT,
        "@type": "HowTo",
        "name": f"How to measure for a {kind['label'].lower()} cover",
        "url": kind["guide_url"],
        "tool": [{"@type": "HowToTool", "name": "Tape measure"}],
        "step": steps,
    }
    return [product, howto]


def itemlist_ld(items: list[dict[str, Any]], url: str) -> dict[str, Any]:
    """Describe the covers listed on an index page in their given order."""
    return {
        "@context": _CONTEXT,
        "@type": "ItemList",
        "url": url,
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": item["name"],
                "url": item["page_url"],
            }
            for position, item in enumerate(items, start=1)
        ],
    }


def script_tags(nodes: list[dict[str, Any]]) -> str:
    """Serialize nodes into script elements without allowing closing tags in JSON."""
    return "\n".join(
        '<script type="application/ld+json">'
        + json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
        + "</script>"
        for node in nodes
    )
