"""Zoning loader (SPEC §7.2).

Two jobs:
  1. write the hand-encoded `zoning_rules` rows (the §8 seed);
  2. load the 2016 zoning polygon layer used ONLY for the parcel spatial join.

The polygons are not persisted to a table of their own — `parcels.zone_code` is the
product of the join, and the encoded rules live in `zoning_rules` keyed by district code.
"""
from __future__ import annotations

import geopandas as gpd

from data.loaders import dc_sources as src
from data.loaders.arcgis import fetch_features
from data.loaders.seed_zoning import write_seed

__all__ = ["fetch_zoning_polygons", "write_seed"]


def fetch_zoning_polygons() -> gpd.GeoDataFrame:
    """Current (2016 ZR) zoning districts as `zone_code` + geometry, EPSG:4326."""
    zoning = fetch_features(src.ZONING_URL, src.ZONING_FIELDS)
    zoning = zoning.rename(columns={"ZONING": "zone_code"})
    zoning["zone_code"] = zoning["zone_code"].astype("string").str.strip()
    zoning = zoning[zoning["zone_code"].notna() & (zoning["zone_code"] != "")]
    return zoning[["zone_code", "geometry"]].reset_index(drop=True)
