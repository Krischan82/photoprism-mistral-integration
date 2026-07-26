import logging
import time

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_MIN_INTERVAL = 1.1  # OpenStreetMap Nominatim usage policy: max ~1 req/s
_last_request_at = 0.0


def geocode_place(place: str, user_agent: str) -> tuple[float, float] | None:
    """Resolve a place name guessed by the vision model to (lat, lng).

    We deliberately never trust coordinates hallucinated by an LLM directly -
    only a place *name* is taken from Mistral, and the actual coordinates
    come from a real geocoding service (OpenStreetMap Nominatim, no API key
    required).
    """
    global _last_request_at
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": user_agent},
            timeout=10,
        )
        _last_request_at = time.monotonic()
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        logger.warning("Geocoding lookup for %r failed: %s", place, exc)
        return None
    if not results:
        logger.info("Geocoding lookup for %r returned no results", place)
        return None
    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None
