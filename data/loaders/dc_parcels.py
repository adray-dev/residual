"""DC parcel loader — SPEC §7.2 steps 1-8.

Deterministic code against pinned ArcGIS endpoints (see `dc_sources.py`). Same inputs
always produce the same `parcels` table. Every step below is numbered to match the spec.

Run: `python -m data.loaders.dc_parcels`
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd

from data.loaders import dc_sources as src
from data.loaders.arcgis import fetch_features, fetch_table
from data.loaders.dc_addresses import derive_columns as derive_address_columns
from data.loaders.dc_zoning import fetch_zoning_polygons
from data.repositories import connection

# --- classification rule sets (SPEC §7.2 steps 3 and 5) ---------------------

# Step 3 — condos are excluded entirely in v1 (fix #6): one parcel, dozens of CAMA rows
# whose values don't aggregate, and never a redevelopment target (you'd have to buy out
# every unit owner). Codes from the DCGIS USECODE lookup (Property_and_Land layer 54).
CONDO_USE_CODES = {
    "016",  # Residential-Condo-Horizontal
    "017",  # Residential-Condo-Vertical
    "018",  # Residential-Condo-Garage
    "048",  # Commercial-Retail-Condo
    "056",  # Office-Condo-Horizontal
    "057",  # Office-Condo-Vertical
    "058",  # Commercial-Office-Condo
    "078",  # Warehouse-Condo
    "116",  # Condo-Horizontal-Combined
    "117",  # Condo-Vertical-Combined
    "216",  # Condo-Investment-Horizontal
    "217",  # Condo-Investment-Vertical
    "316",  # Condo-Duplex
    "416",  # Condo-Horizontal-Parking-Unid
}

# Step 5 — is_exempt. DC tax types (Property_and_Land layer 65 lookup) that mean
# "not taxable, not developable by a private buyer".
EXEMPT_TAX_TYPES = {
    "US",  # United States (federal)
    "DC",  # District of Columbia
    "RL",  # DC Redevelopment Land Agency
    "CE",  # cemetery
    "E1",  # religious
    "E2",  # educational
    "E3",  # charitable
    "E4",  # hospitals
    "E5",  # libraries
    "E6",  # foreign government / embassy / chancery
    "E7",  # cemeteries
    "E8",  # exempt by special act of Congress
    "E9",  # WMATA
}

# Institutional / public-realm use codes. Deliberately excludes 082 Medical and
# 088 Health Care Facility — privately held hospitals ARE redevelopment candidates.
EXEMPT_USE_CODES = {
    "081",  # Religious
    "084",  # Public Service
    "085",  # Embassy, Chancery
    "086",  # Museum, Library, Gallery
    "089",  # Special Purpose-Misc
    "189",  # Special Purpose-Memorial
}

# Owner-name patterns for the owner types SPEC §7.2 step 5 names explicitly. The tax-type
# field is only populated on mixed-use records, so ownership is the reliable signal.
EXEMPT_OWNER_PATTERN = (
    r"UNITED STATES OF AMERICA|^UNITED STATES|U\.?\s?S\.?\s?GOVERNMENT"
    r"|DISTRICT OF COLUMBIA|D\.?C\.? GOVERNMENT"
    r"|NATIONAL PARK SERVICE|NATIONAL PARK|NATIONAL CAPITAL PLANNING"
    r"|WASHINGTON METROPOLITAN AREA TRANSIT|WMATA"
    r"|CEMETERY|CHURCH|SYNAGOGUE|ARCHDIOCESE|ARCHBISHOP"
    r"|BOARD OF EDUCATION|SMITHSONIAN|ARCHITECT OF THE CAPITOL"
)

SPLIT_ZONE_COVERAGE_FLAG = 0.80   # step 6: flag lots the winning district covers <80% of


@dataclass
class LoadReport:
    """Everything the Stage B verification gate needs to print."""
    parcels_fetched: int = 0
    condos_excluded: int = 0
    parcels_loaded: int = 0
    median_lot_area_sf: float = 0.0
    zone_matched: int = 0
    zone_unmatched: int = 0
    zone_encoded: int = 0
    split_zoned_flagged: int = 0
    ward_matched: int = 0
    exempt: int = 0
    historic: int = 0
    with_cama: int = 0
    with_building: int = 0
    zone_breakdown: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# steps 1-2 — geometry and lot area
# ---------------------------------------------------------------------------
def fetch_parcels() -> gpd.GeoDataFrame:
    """Step 1: page the Common Ownership Layer into a GeoDataFrame (EPSG:4326)."""
    print("[1/8] fetching parcel polygons (Common Ownership Layer)...", flush=True)
    parcels = fetch_features(src.PARCELS_URL, src.PARCEL_FIELDS)
    parcels = parcels.rename(columns={"SSL": "ssl"})
    parcels["ssl"] = parcels["ssl"].astype("string").str.strip()
    parcels = parcels[parcels["ssl"].notna() & (parcels["ssl"] != "")]
    # One polygon per SSL; the layer carries retired/duplicate records for a few keys.
    parcels = parcels.drop_duplicates(subset="ssl", keep="first").reset_index(drop=True)
    print(f"      {len(parcels):,} parcels", flush=True)
    return parcels


def compute_lot_area(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Step 2: reproject to EPSG:26985 (MD State Plane metres) and derive lot_area_sf.

    Sanity assertion (fix #7): the MEDIAN lot area must land in [1_000, 50_000] SF.
    Outside that range means a swapped EPSG or a metres/feet mixup — fail loudly rather
    than load garbage.
    """
    print("[2/8] reprojecting to EPSG:26985 and computing lot_area_sf...", flush=True)
    projected = parcels.to_crs(src.MD_STATE_PLANE_METERS)
    parcels = parcels.copy()
    parcels["lot_area_sf"] = projected.geometry.area * src.SQM_TO_SQFT

    median = float(parcels["lot_area_sf"].median())
    if not (1_000 <= median <= 50_000):
        raise AssertionError(
            f"median lot_area_sf = {median:,.1f} SF is outside [1,000, 50,000] — the "
            f"projection or units are wrong (swapped EPSG, or metres/feet mixup). "
            f"Refusing to load."
        )
    print(f"      median lot_area_sf = {median:,.1f} SF  (sane)", flush=True)
    return parcels


# ---------------------------------------------------------------------------
# steps 3-5 — CAMA join, values, flags
# ---------------------------------------------------------------------------
def fetch_cama() -> tuple[pd.DataFrame, set[str]]:
    """Steps 3-4: Residential + Commercial extracts only; Condominium is EXCLUDED.

    Returns (one row per SSL with `existing_building_sf`, the set of condo SSLs).
    """
    print("[3/8] fetching CAMA Residential + Commercial (Condominium excluded)...", flush=True)
    residential = fetch_table(src.CAMA_RESIDENTIAL_URL, src.CAMA_RESIDENTIAL_FIELDS)
    commercial = fetch_table(src.CAMA_COMMERCIAL_URL, src.CAMA_COMMERCIAL_FIELDS)
    condominium = fetch_table(src.CAMA_CONDOMINIUM_URL, src.CAMA_CONDOMINIUM_FIELDS)
    print(
        f"      residential={len(residential):,} commercial={len(commercial):,} "
        f"condominium={len(condominium):,} (excluded)",
        flush=True,
    )

    condo_ssls = set(condominium["SSL"].astype("string").str.strip().dropna())

    # Step 4: dedupe to one row per SSL. Residential takes BLDG_NUM = 1; commercial takes
    # the single assessment row per SSL. Where an SSL still carries several rows, keep the
    # largest building area — deterministic, and the representative structure on the lot.
    residential = residential.rename(columns={"GBA": "existing_building_sf"})
    residential = residential[residential["BLDG_NUM"].fillna(1) == 1]

    commercial = commercial.rename(columns={"LIVING_GBA": "existing_building_sf"})

    frames = []
    for frame, source in ((residential, "residential"), (commercial, "commercial")):
        frame = frame.copy()
        frame["ssl"] = frame["SSL"].astype("string").str.strip()
        frame["existing_building_sf"] = pd.to_numeric(
            frame["existing_building_sf"], errors="coerce"
        ).fillna(0.0)
        frame["cama_source"] = source
        frames.append(frame[["ssl", "existing_building_sf", "USECODE", "cama_source"]])

    cama = pd.concat(frames, ignore_index=True)
    cama = cama.sort_values("existing_building_sf", ascending=False)
    cama = cama.drop_duplicates(subset="ssl", keep="first").reset_index(drop=True)
    return cama, condo_ssls


def apply_cama(
    parcels: gpd.GeoDataFrame, cama: pd.DataFrame, condo_ssls: set[str], report: LoadReport
) -> gpd.GeoDataFrame:
    """Step 3 (exclusion) + step 5 (values, building area, is_exempt)."""
    print("[4/8] excluding condos, joining CAMA, deriving values and flags...", flush=True)

    use_code = parcels["USECODE"].astype("string").str.strip()
    is_condo = (
        parcels["ssl"].isin(condo_ssls)
        | use_code.isin(CONDO_USE_CODES)
        | (parcels["CONDOLOT"].astype("string").str.strip().str.upper() == "Y")
    )
    report.condos_excluded = int(is_condo.sum())
    parcels = parcels[~is_condo].copy()
    print(f"      condos excluded: {report.condos_excluded:,}", flush=True)

    # `merge` returns a fresh RangeIndex, so every derived column below must be computed
    # from the merged frame — never from a Series built before the merge.
    # Address and neighborhood come off the same layer (Stage D). Derived before the
    # CAMA merge, via the shared rule in `dc_addresses`, so a full re-pull and the
    # standalone backfill produce identical values.
    parcels[["address", "neighborhood"]] = derive_address_columns(parcels)

    parcels = parcels.merge(cama, on="ssl", how="left", suffixes=("", "_cama"))
    parcels["existing_building_sf"] = parcels["existing_building_sf"].fillna(0.0)
    report.with_cama = int(parcels["cama_source"].notna().sum())
    report.with_building = int((parcels["existing_building_sf"] > 0).sum())

    # Assessed values live on the Common Ownership Layer (NEWLAND/NEWIMPR), not in the
    # CAMA extracts. 0 means "no assessed value on record" -> None, not a real $0.
    land = pd.to_numeric(parcels["NEWLAND"], errors="coerce")
    improvement = pd.to_numeric(parcels["NEWIMPR"], errors="coerce")
    total = land.fillna(0) + improvement.fillna(0)
    parcels["land_value"] = land.where(land > 0)
    parcels["improvement_value"] = improvement.where(total > 0)
    # Guard divide-by-zero: land + improvement == 0 -> improvement_ratio is None.
    parcels["improvement_ratio"] = (improvement / total).where(total > 0)

    # Prefer the parcel layer's USECODE; fall back to the CAMA extract's where absent.
    parcel_use = parcels["USECODE"].astype("string").str.strip()
    cama_use = parcels["USECODE_cama"].astype("string").str.strip()
    parcels["land_use_code"] = (
        parcel_use.where(parcel_use.notna() & (parcel_use != ""), cama_use).fillna("")
    )

    owner = parcels["OWNERNAME"].astype("string").fillna("").str.upper()
    tax_type = parcels["MIX1TXTYPE"].astype("string").str.strip().str.upper()
    parcels["is_exempt"] = (
        tax_type.isin(EXEMPT_TAX_TYPES).fillna(False)
        | parcels["land_use_code"].isin(EXEMPT_USE_CODES)
        | owner.str.contains(EXEMPT_OWNER_PATTERN, regex=True, na=False)
    ).fillna(False).astype(bool)
    report.exempt = int(parcels["is_exempt"].sum())
    print(f"      exempt: {report.exempt:,}   with CAMA row: {report.with_cama:,}", flush=True)
    return parcels


# ---------------------------------------------------------------------------
# steps 6-7 — spatial joins
# ---------------------------------------------------------------------------
def _largest_intersection(
    parcels_m: gpd.GeoDataFrame, polygons_m: gpd.GeoDataFrame, value_col: str
) -> pd.DataFrame:
    """Split-zoned rule (v1.2): assign the polygon with the largest intersection area.

    Returns one row per intersecting SSL: (ssl, value_col, coverage), where `coverage`
    is the winning polygon's share of the lot.
    """
    pairs = gpd.sjoin(
        parcels_m[["ssl", "geometry"]],
        polygons_m[[value_col, "geometry"]],
        how="inner",
        predicate="intersects",
    )
    if pairs.empty:
        return pd.DataFrame(columns=["ssl", value_col, "coverage"])

    left = gpd.GeoSeries(pairs.geometry.values, crs=parcels_m.crs)
    right = gpd.GeoSeries(
        polygons_m.geometry.loc[pairs["index_right"]].values, crs=polygons_m.crs
    )
    intersection_area = left.intersection(right).area.values
    lot_area = left.area.values

    out = pd.DataFrame(
        {
            "ssl": pairs["ssl"].values,
            value_col: pairs[value_col].values,
            "intersection_area": intersection_area,
            "lot_area": lot_area,
        }
    )
    out = out.sort_values("intersection_area", ascending=False)
    out = out.drop_duplicates(subset="ssl", keep="first")
    out["coverage"] = out["intersection_area"] / out["lot_area"].where(out["lot_area"] > 0)
    return out[["ssl", value_col, "coverage"]].reset_index(drop=True)


def join_zoning_and_wards(
    parcels: gpd.GeoDataFrame,
    report: LoadReport,
    zoning: gpd.GeoDataFrame | None = None,
    wards: gpd.GeoDataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Step 6: largest-intersection joins for zone_code and submarket_id."""
    print("[5/8] fetching zoning (2016 ZR) and ward polygons...", flush=True)
    zoning = fetch_zoning_polygons() if zoning is None else zoning
    wards = fetch_features(src.WARDS_URL, src.WARD_FIELDS) if wards is None else wards
    wards["submarket_id"] = "ward_" + wards["WARD"].astype("string").str.strip()
    print(f"      {len(zoning):,} zoning polygons, {len(wards):,} wards", flush=True)

    print("[6/8] largest-intersection spatial joins (zoning, wards)...", flush=True)
    parcels_m = parcels[["ssl", "geometry"]].to_crs(src.MD_STATE_PLANE_METERS)
    parcels_m["geometry"] = parcels_m.geometry.make_valid()
    zoning_m = zoning.to_crs(src.MD_STATE_PLANE_METERS)
    zoning_m["geometry"] = zoning_m.geometry.make_valid()
    wards_m = wards[["submarket_id", "geometry"]].to_crs(src.MD_STATE_PLANE_METERS)
    wards_m["geometry"] = wards_m.geometry.make_valid()

    zone_match = _largest_intersection(parcels_m, zoning_m, "zone_code")
    ward_match = _largest_intersection(parcels_m, wards_m, "submarket_id")

    report.split_zoned_flagged = int((zone_match["coverage"] < SPLIT_ZONE_COVERAGE_FLAG).sum())

    parcels = parcels.merge(zone_match[["ssl", "zone_code"]], on="ssl", how="left")
    parcels = parcels.merge(ward_match[["ssl", "submarket_id"]], on="ssl", how="left")

    report.zone_matched = int(parcels["zone_code"].notna().sum())
    report.zone_unmatched = int(parcels["zone_code"].isna().sum())
    report.ward_matched = int(parcels["submarket_id"].notna().sum())
    print(
        f"      zone matched: {report.zone_matched:,}  unmatched: {report.zone_unmatched:,}  "
        f"split-zoned (<80% coverage): {report.split_zoned_flagged:,}",
        flush=True,
    )
    return parcels, wards


def join_historic(
    parcels: gpd.GeoDataFrame,
    report: LoadReport,
    districts: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Step 7: any intersection with a historic district sets is_historic."""
    print("[7/8] joining historic districts...", flush=True)
    districts = (
        fetch_features(src.HISTORIC_DISTRICTS_URL, src.HISTORIC_FIELDS)
        if districts is None
        else districts
    )
    districts_m = districts[["geometry"]].to_crs(src.MD_STATE_PLANE_METERS)
    districts_m["geometry"] = districts_m.geometry.make_valid()

    parcels_m = parcels[["ssl", "geometry"]].to_crs(src.MD_STATE_PLANE_METERS)
    parcels_m["geometry"] = parcels_m.geometry.make_valid()
    hits = gpd.sjoin(parcels_m, districts_m, how="inner", predicate="intersects")
    historic_ssls = set(hits["ssl"].unique())

    parcels = parcels.copy()
    parcels["is_historic"] = parcels["ssl"].isin(historic_ssls)
    report.historic = int(parcels["is_historic"].sum())
    print(
        f"      {len(districts):,} historic districts -> {report.historic:,} parcels flagged",
        flush=True,
    )
    return parcels


# ---------------------------------------------------------------------------
# step 8 — load
# ---------------------------------------------------------------------------
_STAGE_DDL = """
CREATE TEMP TABLE parcels_stage (
    ssl TEXT, geom_wkt TEXT, address TEXT, neighborhood TEXT,
    lot_area_sf DOUBLE PRECISION, zone_code TEXT,
    submarket_id TEXT, land_value DOUBLE PRECISION, improvement_value DOUBLE PRECISION,
    improvement_ratio DOUBLE PRECISION, land_use_code TEXT,
    existing_building_sf DOUBLE PRECISION, is_exempt BOOLEAN, is_historic BOOLEAN
) ON COMMIT DROP
"""

_STAGE_TO_PARCELS = """
INSERT INTO parcels (
    ssl, parcel_geom, address, neighborhood, lot_area_sf, zone_code, submarket_id,
    land_value, improvement_value, improvement_ratio, land_use_code,
    existing_building_sf, is_exempt, is_historic
)
SELECT ssl, ST_Multi(ST_GeomFromText(geom_wkt, 4326)), address, neighborhood,
       lot_area_sf, zone_code, submarket_id, land_value, improvement_value,
       improvement_ratio, land_use_code, existing_building_sf, is_exempt, is_historic
FROM parcels_stage
ON CONFLICT (ssl) DO UPDATE SET
    parcel_geom = EXCLUDED.parcel_geom,
    address = EXCLUDED.address,
    neighborhood = EXCLUDED.neighborhood,
    lot_area_sf = EXCLUDED.lot_area_sf,
    zone_code = EXCLUDED.zone_code,
    submarket_id = EXCLUDED.submarket_id,
    land_value = EXCLUDED.land_value,
    improvement_value = EXCLUDED.improvement_value,
    improvement_ratio = EXCLUDED.improvement_ratio,
    land_use_code = EXCLUDED.land_use_code,
    existing_building_sf = EXCLUDED.existing_building_sf,
    is_exempt = EXCLUDED.is_exempt,
    is_historic = EXCLUDED.is_historic
"""

_COPY_COLUMNS = [
    "ssl", "geom_wkt", "address", "neighborhood", "lot_area_sf", "zone_code",
    "submarket_id", "land_value", "improvement_value", "improvement_ratio",
    "land_use_code", "existing_building_sf", "is_exempt", "is_historic",
]


def write_submarkets(conn, wards: gpd.GeoDataFrame) -> int:
    """Wards are the v1 submarkets; parcels.submarket_id references them."""
    rows = [
        (r["submarket_id"], r["NAME"], r["geometry"].wkt)
        for _, r in wards.iterrows()
        if r["geometry"] is not None
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO submarkets (submarket_id, name, boundary)
               VALUES (%s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
               ON CONFLICT (submarket_id) DO UPDATE SET
                   name = EXCLUDED.name, boundary = EXCLUDED.boundary""",
            rows,
        )
    conn.commit()
    return len(rows)


def write_parcels(conn, parcels: gpd.GeoDataFrame) -> int:
    """Step 8: bulk COPY through a staging table (WKT -> geometry in one pass)."""
    print("[8/8] loading parcels into Postgres...", flush=True)
    frame = parcels.copy()
    frame["geom_wkt"] = frame.geometry.apply(lambda g: g.wkt if g is not None else None)
    frame = frame[frame["geom_wkt"].notna()]

    # psycopg adapts Python natives, not numpy/pandas scalars — coerce on the way out.
    casts = {
        "lot_area_sf": float, "land_value": float, "improvement_value": float,
        "improvement_ratio": float, "existing_building_sf": float,
        "is_exempt": bool, "is_historic": bool,
    }

    def _native(column: str, value):
        if value is None or (not isinstance(value, (list, tuple)) and pd.isna(value)):
            return None
        return casts.get(column, str)(value)

    with conn.cursor() as cur:
        cur.execute(_STAGE_DDL)
        with cur.copy("COPY parcels_stage FROM STDIN") as copy:
            for row in frame[_COPY_COLUMNS].itertuples(index=False, name=None):
                copy.write_row(
                    tuple(_native(col, val) for col, val in zip(_COPY_COLUMNS, row))
                )
        cur.execute(_STAGE_TO_PARCELS)
        written = cur.rowcount
    conn.commit()
    print(f"      {written:,} parcel rows written", flush=True)
    return written


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def build_parcels() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, LoadReport]:
    """Steps 1-7: everything up to (but not including) the database write."""
    report = LoadReport()

    parcels = fetch_parcels()
    report.parcels_fetched = len(parcels)

    parcels = compute_lot_area(parcels)

    cama, condo_ssls = fetch_cama()
    parcels = apply_cama(parcels, cama, condo_ssls, report)

    parcels, wards = join_zoning_and_wards(parcels, report)
    parcels = join_historic(parcels, report)

    report.median_lot_area_sf = float(parcels["lot_area_sf"].median())
    report.zone_breakdown = (
        parcels["zone_code"].value_counts(dropna=False).to_dict()
    )

    keep = [
        "ssl", "geometry", "address", "neighborhood", "lot_area_sf", "zone_code",
        "submarket_id", "land_value", "improvement_value", "improvement_ratio",
        "land_use_code", "existing_building_sf", "is_exempt", "is_historic",
    ]
    return parcels[keep], wards, report


def run(database_url: str | None = None) -> LoadReport:
    parcels, wards, report = build_parcels()
    with connection(database_url) as conn:
        write_submarkets(conn, wards)
        report.parcels_loaded = write_parcels(conn, parcels)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load DC parcels (SPEC §7.2)")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    run(args.database_url)
