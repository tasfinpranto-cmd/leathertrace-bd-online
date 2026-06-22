from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote_plus

import requests


def maps_url(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    return f"https://www.google.com/maps?q={lat:.7f},{lon:.7f}"


def geocode_address(address: str, api_key: str) -> dict[str, Any]:
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY has not been configured")
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": api_key}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK" or not payload.get("results"):
        raise ValueError(f"Google Maps could not find the location: {payload.get('status')}")
    first = payload["results"][0]
    location = first["geometry"]["location"]
    return {
        "latitude": float(location["lat"]),
        "longitude": float(location["lng"]),
        "formatted_address": first.get("formatted_address", address),
        "place_id": first.get("place_id"),
        "capture_method": "Google Map Search",
    }


def reverse_geocode(lat: float, lon: float, api_key: str) -> dict[str, Any]:
    if not api_key:
        return {"formatted_address": "", "place_id": None}
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"latlng": f"{lat},{lon}", "key": api_key}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK" or not payload.get("results"):
        return {"formatted_address": "", "place_id": None}
    first = payload["results"][0]
    return {"formatted_address": first.get("formatted_address", ""), "place_id": first.get("place_id")}


def embed_html(lat: float, lon: float, api_key: str, zoom: int = 14) -> str:
    if api_key:
        src = (
            "https://www.google.com/maps/embed/v1/view"
            f"?key={quote_plus(api_key)}&center={lat},{lon}&zoom={zoom}&maptype=roadmap"
        )
        return f'<iframe width="100%" height="360" style="border:0" loading="lazy" allowfullscreen src="{escape(src)}"></iframe>'
    url = maps_url(lat, lon)
    return f'<a href="{escape(url or "#")}" target="_blank">Open this GPS point in Google Maps</a>'
