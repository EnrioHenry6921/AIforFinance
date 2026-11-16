"""
calendar_api.py - Public holidays from the free Nager.Date API (no key needed).
Falls back to the `holidays` Python library if the API is unreachable.
Results are cached in data/output so the API is called once per year/country.
"""
import json

import requests

from . import config


def public_holidays(years, country=config.HOLIDAY_COUNTRY):
    """Return ({date: holiday name}, source) for the given years."""
    cache = config.OUT_DIR / f"holidays_{country}.json"
    data = json.loads(cache.read_text()) if cache.exists() else {}
    source = "cache"
    for y in years:
        if str(y) in data:
            continue
        try:
            r = requests.get(config.NAGER_URL.format(year=y, country=country), timeout=10)
            r.raise_for_status()
            # keep national holidays only (global=True); regional ones (e.g. Alsace-Moselle) are excluded
            data[str(y)] = {h["date"]: h["localName"] for h in r.json() if h.get("global", True)}
            source = "Nager.Date API"
        except (requests.RequestException, ValueError):
            import holidays
            data[str(y)] = {str(d): n for d, n in holidays.country_holidays(country, years=y).items()}
            source = "holidays library (API unreachable)"
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    merged = {d: n for y in years for d, n in data[str(y)].items()}
    return merged, source
