"""Pinned DC / DCGIS ArcGIS REST endpoints (SPEC §7.2).

One place to repull-check on the 1st of every month. Each entry records the layer
that was verified against the spec's source table, plus the fields the loader reads
(the schema-validation guard asserts these before any transform).

Two pins deserve a note, because the obvious-looking layer is the wrong one:
  * ZONING — DCOZ/Zoning_MapServices/9 ("Zones") is the RETIRED 1958 zoning (R-5-B,
    C-2-A, ...). The current 2016 ZR districts (RA-1, MU-4, D-5, ...) live in
    Planning_Landuse_and_Zoning/32.
  * ASSESSED VALUES — the CAMA Residential/Commercial extracts carry building
    characteristics (GBA, use code) but NOT assessed land/improvement dollars. Those
    live on the Common Ownership Layer itself as NEWLAND / NEWIMPR.
"""
from __future__ import annotations

PROPERTY = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Property_and_Land_WebMercator/FeatureServer"
)
PLANNING = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Planning_Landuse_and_Zoning_WebMercator/MapServer"
)
ADMIN = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Administrative_Other_Boundaries_WebMercator/MapServer"
)
HISTORIC = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
    "Historic_WebMercator/MapServer"
)

# --- layers -----------------------------------------------------------------
PARCELS_URL = f"{PROPERTY}/40"        # Owner Polygons (Common Ownership Layer)
CAMA_RESIDENTIAL_URL = f"{PROPERTY}/25"   # RESIDENTIAL (CAMA)
CAMA_COMMERCIAL_URL = f"{PROPERTY}/23"    # COMMERCIAL (CAMA)
CAMA_CONDOMINIUM_URL = f"{PROPERTY}/24"   # CONDOMINIUM (CAMA) — EXCLUDED in v1 (fix #6)
ZONING_URL = f"{PLANNING}/32"         # Zoning Boundaries (Zoning Regulations of 2016)
WARDS_URL = f"{ADMIN}/53"             # Ward - 2022
HISTORIC_DISTRICTS_URL = f"{HISTORIC}/6"  # Historic Districts

# --- fields the loaders read (schema-validation guard, SPEC §7.2) ------------
PARCEL_FIELDS = [
    "SSL",          # Square-Suffix-Lot — the universal key
    "PREMISEADD",   # premise address        -> address       (Stage D: UI is address-forward)
    "NBHDNAME",     # assessment nbhd name   -> neighborhood  (SUBNBHD is a letter code, unused)
    "USECODE",      # -> land_use_code
    "PROPTYPE",
    "NEWLAND",      # assessed land value    -> land_value
    "NEWIMPR",      # assessed improvement   -> improvement_value
    "OWNERNAME",    # -> is_exempt (owner type)
    "MIX1TXTYPE",   # -> is_exempt (tax type: US/DC/E1..E9/CE)
    "TAXRATE",
    "CONDOLOT",     # 'Y' on condo lots      -> condo exclusion
    "UNDERLIES_CONDO",
]
CAMA_RESIDENTIAL_FIELDS = ["SSL", "GBA", "BLDG_NUM", "USECODE", "NUM_UNITS"]
CAMA_COMMERCIAL_FIELDS = ["SSL", "LIVING_GBA", "BLDG_NUM", "USECODE", "NUM_UNITS"]
CAMA_CONDOMINIUM_FIELDS = ["SSL", "LIVING_GBA", "USECODE"]
ZONING_FIELDS = ["ZONING", "ZONING_LABEL"]
WARD_FIELDS = ["WARD", "NAME"]
HISTORIC_FIELDS = ["NAME", "LABEL"]

# Attribute-only pull for the address backfill (`dc_addresses.py`). Same pinned layer as
# PARCELS_URL, no geometry — so refreshing addresses never rewrites parcel_geom or
# re-runs the spatial joins.
ADDRESS_FIELDS = ["SSL", "PREMISEADD", "NBHDNAME"]

# --- projections ------------------------------------------------------------
WGS84 = "EPSG:4326"
MD_STATE_PLANE_METERS = "EPSG:26985"   # NAD83 / Maryland — the DC standard, metres
SQM_TO_SQFT = 10.7639
