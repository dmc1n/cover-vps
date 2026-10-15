"""Public JSON-LD for cover products, measuring guides and cover lists."""

import json
from typing import Any

import pytest
from coverapi.agent_ld import cover_ld, itemlist_ld, kind_ld, script_tags


@pytest.fixture
def cover() -> dict[str, Any]:
    return {
        "code": "suns-2-seater-kota",
        "name": "Kota & café",
        "kinds": ["sofa", "bench"],
        "fits": {
            "length_cm": 230.0,
            "width_cm": 95.5,
            "height_cm": 80.0,
            "height_is_maximum": False,
        },
        "left_right": None,
        "price": {
            "amount_eur": 849.0,
            "currency": "EUR",
            "vat_included": True,
            "indicative": False,
        },
        "delivery": "Ordered today, delivered tomorrow",
        "picture_url": "https://example.com/kota.jpg",
        "page_url": "https://example.com/covers/kota",
        "order_url": "https://example.com/order/kota",
    }


@pytest.fixture
def kind() -> dict[str, Any]:
    return {
        "kind": "sofa",
        "label": "Garden Sofa",
        "how": "Measure the furniture at its widest points.",
        "guide_url": "https://example.com/measure/sofa",
        "order_url": "https://example.com/order/sofa",
        "sizes": [
            {
                "name": "Length",
                "type": "number",
                "required": True,
                "required_when": None,
                "min_cm": 20.0,
                "max_cm": 400.5,
                "means": "The overall length.",
                "how_to_measure": "Measure from end to end.",
            },
            {
                "name": "Has arms",
                "type": "boolean",
                "required": True,
                "required_when": None,
                "min_cm": None,
                "max_cm": None,
                "means": "Whether arms are present.",
                "how_to_measure": "Check both sides.",
            },
            {
                "name": "Arm height",
                "type": "number",
                "required": False,
                "required_when": "has_arms",
                "min_cm": None,
                "max_cm": 100.0,
                "means": "The height of the arms.",
                "how_to_measure": "Measure from the ground.",
            },
        ],
    }


def test_cover_offer(cover: dict[str, Any]) -> None:
    node = cover_ld(cover, company="A & B")
    assert node["@context"] == "https://schema.org"
    assert node["@type"] == "Product"
    assert node["name"] == cover["name"]
    assert node["sku"] == node["productID"] == cover["code"]
    assert node["url"] == cover["page_url"]
    assert node["brand"] == {"@type": "Brand", "name": "A & B"}
    assert node["category"] == "Outdoor furniture cover"
    assert node["material"] == "Sunbrella Coverlast: polyester with an acrylic coating"
    assert node["image"] == cover["picture_url"]
    assert node["size"] == "230 × 95.5 × 80 cm"
    assert (
        node["description"] == "Cover for a sofa, bench that fits furniture of 230 × 95.5 × 80 cm"
    )
    assert type(node["additionalProperty"][0]["value"]) is int
    assert node["additionalProperty"][1]["value"] == 95.5
    assert node["offers"] == {
        "@type": "Offer",
        "price": "849.00",
        "priceCurrency": "EUR",
        "url": cover["order_url"],
        "availability": "https://schema.org/MadeToOrder",
        "itemCondition": "https://schema.org/NewCondition",
        "priceSpecification": {
            "@type": "UnitPriceSpecification",
            "price": "849.00",
            "priceCurrency": "EUR",
            "valueAddedTaxIncluded": True,
        },
        "shippingDetails": {
            "@type": "OfferShippingDetails",
            "description": cover["delivery"],
        },
    }
    assert "deliveryTime" not in node["offers"]["shippingDetails"]


@pytest.mark.parametrize("missing", [False, True])
def test_cover_without_price(cover: dict[str, Any], missing: bool) -> None:
    cover["price"] = None
    if missing:
        del cover["price"]
    cover["picture_url"] = None
    node = cover_ld(cover)
    assert "offers" not in node
    assert "image" not in node


@pytest.mark.parametrize("hand", ["left", "right"])
def test_maximum_height_and_hand(cover: dict[str, Any], hand: str) -> None:
    cover["fits"]["height_is_maximum"] = True
    cover["left_right"] = hand
    node = cover_ld(cover)
    assert node["additionalProperty"][2] == {
        "@type": "PropertyValue",
        "name": "Fits furniture height",
        "maxValue": 80,
        "unitCode": "CMT",
        "unitText": "cm",
    }
    assert node["additionalProperty"][3] == {
        "@type": "PropertyValue",
        "name": "Hand",
        "value": hand,
    }
    assert node["description"] == (
        f"Cover for a sofa, bench ({hand} hand) "
        "that fits furniture of 230 × 95.5 cm, up to 80 cm high"
    )


def test_indicative_offer_without_delivery(cover: dict[str, Any]) -> None:
    cover["price"]["indicative"] = True
    cover["price"]["vat_included"] = False
    cover["delivery"] = None
    offer = cover_ld(cover)["offers"]
    assert offer["description"] == "Indicative price"
    assert offer["priceSpecification"]["valueAddedTaxIncluded"] is False
    assert "shippingDetails" not in offer


def test_kind_ranges_and_steps(kind: dict[str, Any]) -> None:
    product, howto = kind_ld(kind)
    assert product["name"] == "Made-to-measure cover: Garden Sofa"
    assert product["description"] == kind["how"]
    assert product["additionalProperty"] == [
        {
            "@type": "PropertyValue",
            "name": "Length (cm)",
            "minValue": 20,
            "maxValue": 400.5,
            "unitCode": "CMT",
            "unitText": "cm",
            "description": "The overall length.",
        },
        {
            "@type": "PropertyValue",
            "name": "Arm height (cm)",
            "maxValue": 100,
            "unitCode": "CMT",
            "unitText": "cm",
            "description": "The height of the arms.",
        },
    ]
    assert product["offers"] == {
        "@type": "AggregateOffer",
        "priceCurrency": "EUR",
        "availability": "https://schema.org/MadeToOrder",
        "url": kind["order_url"],
    }
    assert howto["@type"] == "HowTo"
    assert howto["name"] == "How to measure for a garden sofa cover"
    assert howto["url"] == kind["guide_url"]
    assert howto["tool"] == [{"@type": "HowToTool", "name": "Tape measure"}]
    assert howto["step"] == [
        {
            "@type": "HowToStep",
            "position": i,
            "name": size["name"],
            "text": size["means"]
            + " "
            + size["how_to_measure"]
            + (" (only when has_arms is true)" if i == 3 else ""),
        }
        for i, size in enumerate(kind["sizes"], 1)
    ]


def test_itemlist() -> None:
    items = [{"name": "First", "page_url": "/first"}, {"name": "Second", "page_url": "/second"}]
    assert itemlist_ld(items, "/covers") == {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "url": "/covers",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "First", "url": "/first"},
            {"@type": "ListItem", "position": 2, "name": "Second", "url": "/second"},
        ],
    }
    assert itemlist_ld([], "/covers")["itemListElement"] == []


def test_script_tags(cover: dict[str, Any]) -> None:
    cover["name"] = 'café </script><script> & "cover"'
    nodes = [cover_ld(cover), itemlist_ld([cover], "/covers")]
    markup = script_tags(nodes)
    assert "<\\/script>" in markup
    assert "café" in markup
    assert "&amp;" not in markup
    for line, node in zip(markup.splitlines(), nodes, strict=True):
        payload = line.removeprefix('<script type="application/ld+json">').removesuffix("</script>")
        assert "</script>" not in payload
        assert json.loads(payload) == node
    assert script_tags([]) == ""


def test_no_internal_keys(cover: dict[str, Any], kind: dict[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                assert not any(word in key.lower() for word in ("cost", "margin", "labour"))
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    cover.update(cost=123, margin=45, labour=67, costing={"secret": 89})
    kind.update(cost=123, margin=45, labour=67, costing={"secret": 89})
    nodes = [cover_ld(cover), *kind_ld(kind), itemlist_ld([cover], "/covers")]
    walk(nodes)
    for line in script_tags(nodes).splitlines():
        walk(
            json.loads(
                line.removeprefix('<script type="application/ld+json">').removesuffix("</script>")
            )
        )
