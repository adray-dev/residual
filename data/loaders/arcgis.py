"""Paginated ArcGIS REST fetch + the schema-validation guard (SPEC §7.2).

Shared by every DC loader. Pure I/O against pinned endpoints — no transforms here.
"""
from __future__ import annotations

import time
from typing import Iterable

import geopandas as gpd
import pandas as pd
import requests

PAGE_SIZE = 1000          # DC caps FeatureServer pages at 1000-2000; 1000 is safe everywhere
REQUEST_TIMEOUT = 120
MAX_RETRIES = 4
WGS84 = "EPSG:4326"


class SchemaMismatch(RuntimeError):
    """A pinned dataset no longer exposes a field the loader depends on (SPEC §7.2).

    Raised instead of loading a partial/renamed schema silently. DC will rename fields
    eventually; this turns that into a loud 5-minute fix instead of silent garbage.
    """


def _get(url: str, params: dict) -> dict:
    """One GET with bounded retries; raises on persistent failure or an ArcGIS error body."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # network flake, truncated JSON, 5xx
            last_error = exc
            time.sleep(2 ** attempt)
            continue
        if isinstance(payload, dict) and "error" in payload:
            raise RuntimeError(f"ArcGIS error from {url}: {payload['error']}")
        return payload
    raise RuntimeError(f"failed after {MAX_RETRIES} attempts: {url}") from last_error


def assert_fields(layer_url: str, required: Iterable[str]) -> None:
    """Schema-validation guard: abort the load naming the missing field (SPEC §7.2)."""
    meta = _get(layer_url, {"f": "json"})
    present = {f["name"] for f in meta.get("fields") or []}
    if meta.get("geometryType"):
        present.add("geometry")
    missing = sorted(set(required) - present)
    if missing:
        raise SchemaMismatch(
            f"{layer_url} ({meta.get('name')!r}) is missing required field(s): "
            f"{', '.join(missing)}. The upstream schema changed — fix the loader field "
            f"mapping before loading. Fields now present: {', '.join(sorted(present))}"
        )


def fetch_table(layer_url: str, fields: list[str], where: str = "1=1") -> pd.DataFrame:
    """Page an attribute-only layer/table into a DataFrame."""
    assert_fields(layer_url, fields)
    rows: list[dict] = []
    offset = 0
    while True:
        payload = _get(
            f"{layer_url}/query",
            {
                "where": where,
                "outFields": ",".join(fields),
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
        )
        page = [f["attributes"] for f in payload.get("features", [])]
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return pd.DataFrame(rows, columns=fields)


def fetch_features(
    layer_url: str, fields: list[str], where: str = "1=1"
) -> gpd.GeoDataFrame:
    """Page a polygon layer into a GeoDataFrame in EPSG:4326.

    `fields` must NOT include "geometry"; geometry is always requested.
    """
    assert_fields(layer_url, [*fields, "geometry"])
    frames: list[gpd.GeoDataFrame] = []
    offset = 0
    while True:
        payload = _get(
            f"{layer_url}/query",
            {
                "where": where,
                "outFields": ",".join(fields),
                "outSR": 4326,
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "geojson",
            },
        )
        features = payload.get("features", [])
        if features:
            frames.append(gpd.GeoDataFrame.from_features(features, crs=WGS84))
        if len(features) < PAGE_SIZE:
            break
        offset += len(features)
        print(f"    ... {offset:,} features", flush=True)

    if not frames:
        return gpd.GeoDataFrame(columns=[*fields, "geometry"], geometry="geometry", crs=WGS84)
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=WGS84)
    return out[[*fields, "geometry"]]
