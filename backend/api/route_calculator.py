"""
Geocoding (Nominatim) and driving routes (OSRM demo server).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"

USER_AGENT = "SpotterTripPlanner/1.0 (FMCSA HOS educational demo)"


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    display_name: str


@dataclass
class RouteLeg:
    distance_m: float
    duration_s: float
    summary: str


@dataclass
class RoutePlan:
    coordinates: list[list[float]]  # [[lon, lat], ...] for LineString
    legs: list[RouteLeg]
    total_distance_m: float
    total_duration_s: float
    geometry_geojson: dict[str, Any]


def geocode(query: str, timeout: int = 15) -> GeocodeResult:
    q = (query or "").strip()
    if not q:
        raise ValueError("Address query is required.")

    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    time.sleep(1.0)  # Nominatim usage policy: max 1 req/s
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"No results for address: {q!r}")
    row = data[0]
    return GeocodeResult(
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        display_name=row.get("display_name", q),
    )


def _osrm_coords_string(points: list[tuple[float, float]]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)


def fetch_route(points_lonlat: list[tuple[float, float]], timeout: int = 30) -> RoutePlan:
    if len(points_lonlat) < 2:
        raise ValueError("At least two coordinates are required for routing.")

    coords = _osrm_coords_string(points_lonlat)
    url = OSRM_URL.format(coords=coords)
    r = requests.get(
        url,
        params={"overview": "full", "geometries": "geojson", "steps": "true"},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != "Ok" or not body.get("routes"):
        raise ValueError(f"OSRM routing failed: {body.get('message', body)}")

    route = body["routes"][0]
    geom = route.get("geometry") or {}
    coords_ll = geom.get("coordinates") or []
    waypoints = body.get("waypoints") or []
    if len(waypoints) >= len(points_lonlat):
        legs: list[RouteLeg] = []
        for i in range(len(points_lonlat) - 1):
            d = float(
                waypoints[i + 1].get("distance", 0) - waypoints[i].get("distance", 0)
            )
            t = float(
                waypoints[i + 1].get("duration", 0) - waypoints[i].get("duration", 0)
            )
            legs.append(
                RouteLeg(
                    distance_m=max(d, 0),
                    duration_s=max(t, 0),
                    summary=f"Segment {i + 1}",
                )
            )
    else:
        legs = _split_legs_proportional(points_lonlat, route)

    total_m = float(route.get("distance", 0))
    total_s = float(route.get("duration", 0))
    return RoutePlan(
        coordinates=coords_ll,
        legs=legs,
        total_distance_m=total_m,
        total_duration_s=total_s,
        geometry_geojson=geom,
    )


def _split_legs_proportional(
    points_lonlat: list[tuple[float, float]], route: dict
) -> list[RouteLeg]:
    from math import asin, cos, radians, sin, sqrt

    def hav(a, b):
        lon1, lat1 = a
        lon2, lat2 = b
        r = 6371000.0
        p1, p2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dl = radians(lon2 - lon1)
        h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
        return 2 * r * asin(sqrt(min(1.0, h)))

    dists = [hav(points_lonlat[i], points_lonlat[i + 1]) for i in range(len(points_lonlat) - 1)]
    s = sum(dists) or 1.0
    total_m = float(route.get("distance", 0))
    total_s = float(route.get("duration", 0))
    legs = []
    for d in dists:
        ratio = d / s
        legs.append(
            RouteLeg(
                distance_m=total_m * ratio,
                duration_s=total_s * ratio,
                summary="Segment",
            )
        )
    return legs


def plan_stops(
    current_query: str,
    pickup_query: str,
    dropoff_query: str,
) -> tuple[list[GeocodeResult], RoutePlan]:
    cur = geocode(current_query)
    time.sleep(1.0)
    p = geocode(pickup_query)
    time.sleep(1.0)
    d = geocode(dropoff_query)

    points = [(cur.lon, cur.lat), (p.lon, p.lat), (d.lon, d.lat)]
    route = fetch_route(points)
    return [cur, p, d], route
