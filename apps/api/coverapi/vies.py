"""VIES checks for company administration; never called while pricing an order."""

import json
import re
import time
from urllib.request import Request, urlopen

EU_MEMBERS = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE EL HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
)
URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"


def normalise(country: str, vat_number: str) -> tuple[str, str]:
    country = country.strip().upper()
    country = "EL" if country == "GR" else country
    number = re.sub(r"[\s.]", "", vat_number).upper()
    prefixes = ("EL", "GR") if country == "EL" else (country,)
    for prefix in prefixes:
        if prefix and number.startswith(prefix):
            number = number[len(prefix) :]
            break
    return country, number


def check(country: str, vat_number: str) -> dict:
    """Return an indeterminate result on transport, service or malformed-response errors."""
    country, number = normalise(country, vat_number)
    result = {
        "valid": None,
        "name": "",
        "address": "",
        "checked": time.time(),
        "request_id": None,
        "error": None,
    }
    if country not in EU_MEMBERS or not number:
        return {**result, "valid": False}
    request = Request(
        URL,
        data=json.dumps({"countryCode": country, "vatNumber": number}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed EU endpoint
            data = json.load(response)
        error = data.get("error") or data.get("errorWrappers")
        if data.get("userError") not in (None, "", "VALID", "INVALID"):
            error = data["userError"]
        if data.get("actionSucceed") is False and not error:
            error = "VIES check failed"
        if error:
            return {**result, "error": str(error)}
        valid = data.get("isValid", data.get("valid"))
        if not isinstance(valid, bool):
            raise ValueError("VIES response has no validity result")
        return {
            **result,
            "valid": valid,
            "name": data.get("name") or "",
            "address": data.get("address") or "",
            "request_id": data.get("requestIdentifier")
            or data.get("requestId")
            or data.get("consultationNumber"),
        }
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return {**result, "error": str(exc)}
