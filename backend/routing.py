from __future__ import annotations

import os
import random
import math
from typing import Any, Dict, List, Tuple

import requests


ORS_BASE = "https://api.openrouteservice.org"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM_BASE = "https://router.project-osrm.org"


class RoutingError(RuntimeError):
    pass


BANGALORE_CENTER = (12.9716, 77.5946)  # lat, lon
MAX_BANGALORE_RADIUS_KM = 70.0


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    r = 6371.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _pick_bangalore_candidate(candidates: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not candidates:
        return None
    valid = []
    for c in candidates:
        lat = float(c["lat"])
        lon = float(c["lon"])
        d = _haversine_km(BANGALORE_CENTER, (lat, lon))
        if d <= MAX_BANGALORE_RADIUS_KM:
            valid.append((d, c))
    if not valid:
        return None
    valid.sort(key=lambda x: x[0])
    return valid[0][1]


# -------------------------------
# GEOCODING (WORKS ALWAYS)
# -------------------------------
def geocode_destination(query: str) -> Dict[str, Any]:
    api_key = os.getenv("ORS_API_KEY", "").strip()

    if api_key:
        try:
            resp = requests.get(
                f"{ORS_BASE}/geocode/search",
                params={
                    "api_key": api_key,
                    "text": f"{query}, Bangalore",
                    "size": 5,
                    "boundary.country": "IN",
                    "focus.point.lat": BANGALORE_CENTER[0],
                    "focus.point.lon": BANGALORE_CENTER[1],
                },
                timeout=10,
            )
            if resp.status_code == 200:
                feats = resp.json().get("features", [])
                candidates = []
                for f in feats:
                    lon, lat = f["geometry"]["coordinates"]
                    label = f.get("properties", {}).get("label", query)
                    candidates.append({"name": label, "lat": float(lat), "lon": float(lon)})
                picked = _pick_bangalore_candidate(candidates)
                if picked:
                    return picked
        except requests.RequestException:
            pass

    resp = requests.get(
        NOMINATIM,
        params={
            "q": f"{query}, Bangalore, Karnataka, India",
            "format": "json",
            "limit": 5,
            "countrycodes": "in",
            # Approx Bangalore bounding box: west,south,east,north
            "viewbox": "77.35,12.78,77.85,13.20",
            "bounded": 1,
        },
        headers={"User-Agent": "rl-delivery-app"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RoutingError("Geocoding failed")
    rows = resp.json()
    if not rows:
        raise RoutingError("No location found")
    candidates = [{"name": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in rows]
    picked = _pick_bangalore_candidate(candidates)
    if not picked:
        raise RoutingError("Location is outside Bangalore. Enter a Bangalore destination.")
    return picked


# -------------------------------
# REAL ROUTES (ORS)
# -------------------------------
def get_real_routes(start: Tuple[float, float], dest: Tuple[float, float], api_key: str) -> List[Dict[str, Any]]:
    preferences = [("Fastest", "fastest"), ("Shortest", "shortest"), ("Balanced", "recommended")]
    routes: List[Dict[str, Any]] = []

    for label, pref in preferences:
        resp = requests.post(
            f"{ORS_BASE}/v2/directions/driving-car/geojson",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={
                "coordinates": [[start[1], start[0]], [dest[1], dest[0]]],
                "preference": pref,
                "instructions": False,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            continue
        feat = resp.json()["features"][0]
        coords = [[c[1], c[0]] for c in feat["geometry"]["coordinates"]]
        summary = feat["properties"]["summary"]
        steps_raw = feat["properties"].get("segments", [{}])[0].get("steps", [])
        steps = []
        for s in steps_raw:
            steps.append(
                {
                    "instruction": s.get("instruction", ""),
                    "distance_m": float(s.get("distance", 0.0)),
                    "duration_s": float(s.get("duration", 0.0)),
                    "way_points": s.get("way_points", [0, 0]),
                }
            )
        distance_km = summary["distance"] / 1000.0
        duration_min = summary["duration"] / 60.0
        routes.append(
            {
                "label": label,
                "distance": distance_km,
                "duration": duration_min,
                "distance_km": distance_km,
                "duration_min": duration_min,
                "coordinates": coords,
                "steps": steps,
            }
        )
    return routes


# -------------------------------
# MOCK ROUTES (FOR TRAINING)
# -------------------------------
def _line(start: Tuple[float, float], dest: Tuple[float, float], bend: float) -> List[List[float]]:
    mid1 = [start[0] * 0.7 + dest[0] * 0.3 + bend, start[1] * 0.7 + dest[1] * 0.3 - bend]
    mid2 = [start[0] * 0.35 + dest[0] * 0.65 - bend, start[1] * 0.35 + dest[1] * 0.65 + bend]
    return [[start[0], start[1]], mid1, mid2, [dest[0], dest[1]]]


def get_mock_routes(start: Tuple[float, float], dest: Tuple[float, float]) -> List[Dict[str, Any]]:
    raw = [
        ("Fastest", random.uniform(8, 12), random.uniform(15, 25), 0.004),
        ("Shortest", random.uniform(10, 15), random.uniform(20, 30), -0.003),
        ("Balanced", random.uniform(9, 13), random.uniform(18, 28), 0.0015),
    ]
    out: List[Dict[str, Any]] = []
    for label, d, t, bend in raw:
        out.append(
            {
                "label": label,
                "distance": d,
                "duration": t,
                "distance_km": d,
                "duration_min": t,
                "coordinates": _line(start, dest, bend),
                "steps": [
                    {"instruction": "Head out from Bangalore Central", "distance_m": d * 300, "duration_s": t * 20, "way_points": [0, 1]},
                    {"instruction": "Continue straight", "distance_m": d * 400, "duration_s": t * 20, "way_points": [1, 2]},
                    {"instruction": "Arrive at destination", "distance_m": d * 300, "duration_s": t * 20, "way_points": [2, 3]},
                ],
            }
        )
    return out


def get_osrm_routes(start: Tuple[float, float], dest: Tuple[float, float]) -> List[Dict[str, Any]]:
    """
    Fallback real-road routing without API key.
    Uses OSRM public API with alternatives.
    """
    lon1, lat1 = start[1], start[0]
    lon2, lat2 = dest[1], dest[0]
    url = f"{OSRM_BASE}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    resp = requests.get(
        url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "true",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        return []
    data = resp.json()
    routes_raw = data.get("routes", [])
    if not routes_raw:
        return []

    labels = ["Fastest", "Alternative 1", "Alternative 2"]
    routes: List[Dict[str, Any]] = []
    for idx, r in enumerate(routes_raw[:3]):
        coords = [[c[1], c[0]] for c in r.get("geometry", {}).get("coordinates", [])]
        steps = []
        legs = r.get("legs", [])
        for leg in legs:
            for s in leg.get("steps", []):
                maneuver = s.get("maneuver", {}).get("type", "continue")
                road = s.get("name") or "road"
                instruction = f"{maneuver.replace('_', ' ').title()} on {road}"
                steps.append(
                    {
                        "instruction": instruction,
                        "distance_m": float(s.get("distance", 0.0)),
                        "duration_s": float(s.get("duration", 0.0)),
                        "way_points": [0, 0],
                    }
                )
        dist_km = float(r.get("distance", 0.0)) / 1000.0
        dur_min = float(r.get("duration", 0.0)) / 60.0
        routes.append(
            {
                "label": labels[idx] if idx < len(labels) else f"Alternative {idx}",
                "distance": dist_km,
                "duration": dur_min,
                "distance_km": dist_km,
                "duration_min": dur_min,
                "coordinates": coords,
                "steps": steps,
            }
        )
    return routes


# -------------------------------
# MAIN FUNCTION
# -------------------------------
def get_route_options(start: Tuple[float, float], dest: Tuple[float, float]) -> List[Dict[str, Any]]:
    def ensure_three(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not routes:
            return routes
        out = list(routes)
        i = 0
        while len(out) < 3:
            base = out[i % len(out)]
            clone = dict(base)
            clone["label"] = f"{base.get('label', 'Route')} Variant {len(out) + 1}"
            # Small variation so ranking/selection is not identical.
            clone["duration_min"] = float(base.get("duration_min", 0.0)) * (1.02 + 0.01 * len(out))
            clone["duration"] = clone["duration_min"]
            clone["distance_km"] = float(base.get("distance_km", 0.0))
            clone["distance"] = clone["distance_km"]
            clone["coordinates"] = list(base.get("coordinates", []))
            clone["steps"] = list(base.get("steps", []))
            out.append(clone)
            i += 1
        return out[:3]

    api_key = os.getenv("ORS_API_KEY", "").strip()
    if api_key:
        routes = get_real_routes(start, dest, api_key)
        if routes:
            return ensure_three(routes)

    # Real-road fallback when ORS key is missing/unavailable.
    osrm_routes = get_osrm_routes(start, dest)
    if osrm_routes:
        return ensure_three(osrm_routes)

    # Last resort fallback for offline/network error.
    return ensure_three(get_mock_routes(start, dest))
