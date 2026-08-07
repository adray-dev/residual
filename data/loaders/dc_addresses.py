"""DC address backfill — populates `parcels.address` and `parcels.neighborhood`.

Stage D needs a human-readable label: six of the seven handoff screens lead with a street
address rather than a parcel ID, and the search field accepts "address · parcel ID · ward".

Both fields already ride on the Common Ownership Layer that `dc_parcels.py` loads
(`PREMISEADD`, `NBHDNAME`, `SUBNBHD`), so this is an attribute-only pull against a pinned
endpoint we already depend on — no new dataset, no new spatial join, and no rewrite of
`parcel_geom`. `dc_parcels.py` carries the same fields, so a full re-pull produces the
same result; this module exists so an already-loaded database can be brought forward
without re-running the spatial joins.

Deterministic, like every other loader: same inputs always produce the same table.

Run: `python -m data.loaders.dc_addresses`
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

import pandas as pd

from data.loaders import dc_sources as src
from data.loaders.arcgis import fetch_table
from data.repositories import connection


@dataclass
class AddressReport:
    fetched: int = 0
    with_address: int = 0
    with_neighborhood: int = 0
    updated: int = 0
    unmatched: int = 0      # rows in the pull with no corresponding `parcels` row


# `PREMISEADD` is uppercase and fully qualified: "912 W ST NW WASHINGTON DC 20001".
# The UI wants the street line only, in the case a person would write it.
_CITY_SUFFIX = re.compile(r"\s+WASHINGTON\s+DC(\s+\d{5}(-\d{4})?)?\s*$", re.IGNORECASE)
_QUADRANTS = {"NW", "NE", "SW", "SE"}
_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)$", re.IGNORECASE)


def _titlecase_street(value: str) -> str:
    """"662 24TH ST NE # 31" -> "662 24th St NE # 31".

    Quadrants stay uppercase (they are directionals, not words); ordinal suffixes go
    lowercase; everything else is word-cased. Deliberately simple — this is a display
    label, and mangling an unusual street name is a cosmetic bug, not a data one.
    """
    words = []
    for word in value.split():
        upper = word.upper()
        if upper in _QUADRANTS:
            words.append(upper)
            continue
        ordinal = _ORDINAL.match(word)
        if ordinal:
            words.append(f"{ordinal.group(1)}{ordinal.group(2).lower()}")
            continue
        # Leave non-alphabetic tokens ("#", "1/2") exactly as they are.
        words.append(word.capitalize() if word.isalpha() else word)
    return " ".join(words)


def derive_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """PREMISEADD/NBHDNAME -> normalized (address, neighborhood), index-aligned.

    Shared with `dc_parcels.py` so a full re-pull and this backfill derive the two fields
    identically — one rule, one place.

    Address handling: strip the "WASHINGTON DC <zip>" suffix every row carries, collapse
    whitespace, and title-case. A row whose street line is empty or a bare quadrant
    ("NE WASHINGTON DC 00000" — a real value on unaddressed interior lots and ROW slivers)
    becomes None, because "NE" is not an address. Readers fall back to the parcel ID.

    `SUBNBHD` is deliberately NOT used: it is a single-letter sub-area code ("A", "B"),
    not a label. `NBHDNAME` carries the human-readable name ("Palisades", "Woodridge").
    """
    out = pd.DataFrame(index=frame.index)

    address = (
        frame["PREMISEADD"]
        .astype("string")
        .str.replace(_CITY_SUFFIX, "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    # A bare quadrant, or nothing at all, is not an address.
    address = address.where(address.notna() & (address != "") & ~address.str.upper().isin(_QUADRANTS))
    out["address"] = address.map(_titlecase_street, na_action="ignore").astype("string")

    nbhd = frame["NBHDNAME"].astype("string").str.strip()
    out["neighborhood"] = nbhd.where(nbhd.notna() & (nbhd != ""))
    return out


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """SSL -> (address, neighborhood), one row per SSL, blanks collapsed to None."""
    out = derive_columns(frame)
    out.insert(0, "ssl", frame["SSL"].astype("string").str.strip())

    out = out[out["ssl"].notna() & (out["ssl"] != "")]
    # The layer carries retired/duplicate records for a few keys; `dc_parcels.py` keeps
    # the first occurrence, so match that rule exactly.
    return out.drop_duplicates(subset="ssl", keep="first").reset_index(drop=True)


def write_addresses(conn, frame: pd.DataFrame, report: AddressReport) -> int:
    """UPDATE existing parcels in place through a staging table. Never inserts.

    An SSL present upstream but absent from `parcels` is counted, not created — this
    loader's job is labelling, and creating parcels here would bypass the condo exclusion
    and every flag `dc_parcels.py` derives.
    """
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TEMP TABLE address_stage (
                   ssl TEXT PRIMARY KEY, address TEXT, neighborhood TEXT
               ) ON COMMIT DROP"""
        )
        with cur.copy("COPY address_stage FROM STDIN") as copy:
            for ssl, address, neighborhood in frame.itertuples(index=False, name=None):
                copy.write_row(
                    (
                        str(ssl),
                        None if pd.isna(address) else str(address),
                        None if pd.isna(neighborhood) else str(neighborhood),
                    )
                )

        cur.execute(
            """SELECT count(*) AS n FROM address_stage s
               LEFT JOIN parcels p USING (ssl) WHERE p.ssl IS NULL"""
        )
        report.unmatched = int(cur.fetchone()["n"])

        cur.execute(
            """UPDATE parcels p
                  SET address = s.address, neighborhood = s.neighborhood
                 FROM address_stage s
                WHERE p.ssl = s.ssl"""
        )
        report.updated = cur.rowcount
    conn.commit()
    return report.updated


def run(database_url: str | None = None) -> AddressReport:
    report = AddressReport()

    print("[1/2] fetching addresses (Common Ownership Layer, attributes only)...", flush=True)
    raw = fetch_table(src.PARCELS_URL, src.ADDRESS_FIELDS)
    report.fetched = len(raw)
    print(f"      {report.fetched:,} rows", flush=True)

    frame = normalize(raw)
    report.with_address = int(frame["address"].notna().sum())
    report.with_neighborhood = int(frame["neighborhood"].notna().sum())

    print("[2/2] updating parcels...", flush=True)
    with connection(database_url) as conn:
        write_addresses(conn, frame, report)

    print(
        f"      updated {report.updated:,} parcels  "
        f"(address {report.with_address:,} · neighbourhood {report.with_neighborhood:,} · "
        f"upstream rows with no parcel {report.unmatched:,})",
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill parcel addresses (Stage D)")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    run(args.database_url)
