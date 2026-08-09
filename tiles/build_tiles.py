"""Static vector tiles, regenerated once per bake (SPEC §10).

SPEC pins static PMTiles over a live tile server, so this is a build step, not a service:
parcel geometry joined to the batch's best-per-parcel bake row, streamed as newline-
delimited GeoJSON into tippecanoe, written as `parcels-<batch>.pmtiles`.

Two things the tiles carry that the client would otherwise have to compute:

  * `bin` / `bin_sf` / `bin_gap` — the diverging quantile ramp index per objective. SPEC §9
    forbids the read path from dividing and §10 wants objective switching to happen
    client-side with no server call, so the bin is baked in and coloring is a lookup.
  * `status` — so non-scored parcels get their own quiet shade rather than reading as
    "low value" on the value ramp.

The filename carries the batch timestamp so a tileset can never be silently paired with a
different bake's numbers; `/meta` only advertises the file matching its own batch.

Run: `python -m tiles.build_tiles`
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime

from data import repositories as repo

LAYER = "parcels"
DEFAULT_OUT_DIR = os.environ.get("TILES_DIR", "tiles/build")

# Zoom range. z9 covers DC in one tile for the initial fit; z15 is enough to see individual
# lots. tippecanoe drops nothing at high zoom (see the flags below), so detail is exact
# where it matters and simplified only when zoomed out.
MIN_ZOOM = 9
MAX_ZOOM = 15

# Objectives -> the tile attribute holding that objective's ramp bin.
BIN_FIELDS = {
    "rlv_total": "bin",
    "rlv_per_buildable_sf": "bin_sf",
    "gap": "bin_gap",
}

# Parcels below this are omitted, explicitly and countably.
#
# DC's parcel layer carries surveying slivers — 28 records under 0.5 m², the smallest
# 0.0149 m² (0.16 SF). They collapse to zero area at every tile resolution, so tippecanoe
# discards them no matter what --drop-rate says. Skipping them here rather than letting
# the encoder do it silently means the omission is deterministic, counted, and reported,
# instead of a quiet gap between "132,632 parcels" and what the map actually draws.
#
# The threshold catches only geometry with no area to draw: 0.5 m² is 5.4 SF, far below
# any real lot. No `scored` parcel falls under it — `test_tiles.py` asserts that, so a
# future data change that starts dropping real parcels fails loudly.
MIN_RENDERABLE_AREA_M2 = 0.5


@dataclass
class TileReport:
    computed_at: datetime | None = None
    features: int = 0
    skipped_no_geom: int = 0
    skipped_too_small: int = 0
    skipped_ssls: list = field(default_factory=list)
    invalid_repaired: int = 0
    status_counts: dict = field(default_factory=dict)
    output: str = ""
    bytes: int = 0


def bin_index(
    value: float | None, negative_breaks: list[float], positive_breaks: list[float]
) -> int:
    """Diverging quantile bin. 0 = unscored, -N..-1 below zero, 1..N at or above.

    The handoff's 8-stop teal ramp assumes all-positive values, but 56% of scored DC
    parcels price negative and the tails run past ±$80M, so a single linear scale collapses
    the middle. Splitting at zero keeps "does this pencil?" as the primary read and puts
    the quantile detail inside each arm.

    With the default 3 breaks per arm this yields -4..-1 and 1..4 — the handoff's eight
    stops, redistributed around zero.

        negative_breaks = [-432641, -245716, -45951]
          -500,000 -> -4 (deepest)      -100,000 -> -2
          -300,000 -> -3                 -10,000 -> -1 (nearest zero)

        positive_breaks = [157357, 329605, 509676]
                0 ->  1 (weakest)        400,000 ->  3
          200,000 ->  2                  900,000 ->  4 (strongest)

    Bins are half-open `[lo, hi)`, so a value sitting exactly on a break belongs to the
    upper bin — hence `bisect_right`, not `bisect_left`.
    """
    if value is None:
        return 0
    if value < 0:
        # bisect_right over ascending breaks gives 0..len; shift so the deepest arm is -(len+1).
        return bisect_right(negative_breaks, value) - (len(negative_breaks) + 1)
    return bisect_right(positive_breaks, value) + 1


def build_features(conn, batch: datetime, report: TileReport):
    """Yield one GeoJSON Feature per parcel: geometry + the attributes the map needs."""
    ramps = {
        objective: repo.objective_ramp(conn, objective, batch)
        for objective in BIN_FIELDS
    }

    for row in repo.iter_map_geojson(conn, batch):
        geometry = row["geometry"]
        if not geometry:
            report.skipped_no_geom += 1
            report.skipped_ssls.append(row["ssl"])
            continue
        if (row["area_m2"] or 0.0) < MIN_RENDERABLE_AREA_M2:
            report.skipped_too_small += 1
            report.skipped_ssls.append(row["ssl"])
            continue
        if row["was_invalid"]:
            report.invalid_repaired += 1

        status = row["status"]
        report.status_counts[status] = report.status_counts.get(status, 0) + 1

        properties = {
            # `id` rather than `ssl`: the handoff's rule is that "SSL" never appears, and
            # tile attributes are visible in the client and in devtools.
            "id": row["ssl"],
            "status": status,
            # The geography filter is client-side over tile attributes (SPEC §10), so the
            # ward has to travel in the tile — there is no other way to grey out eight
            # wards' worth of parcels without a round trip. This is the raw
            # `submarket_id` ("ward_6"), matching what /meta's submarket list keys on;
            # the UI shows that list's `name`.
            "ward": row["submarket_id"],
            "proto": row["prototype_id"] if row["prototype_id"] != repo.NONE_PROTOTYPE else None,
            "rlv": row["rlv_total"],
            "rlv_sf": row["rlv_per_buildable_sf"],
            "gap": row["feasibility_gap"],
            "conf": row["confidence"],
        }
        for objective, field_name in BIN_FIELDS.items():
            ramp = ramps[objective]
            source = {"rlv_total": "rlv_total",
                      "rlv_per_buildable_sf": "rlv_per_buildable_sf",
                      "gap": "feasibility_gap"}[objective]
            properties[field_name] = bin_index(
                row[source] if status == "scored" else None,
                ramp["negative_breaks"],
                ramp["positive_breaks"],
            )

        report.features += 1
        yield {"type": "Feature", "geometry": json.loads(geometry), "properties": properties}


def write_geojsonseq(conn, batch: datetime, path: str, report: TileReport) -> None:
    with open(path, "w") as handle:
        for feature in build_features(conn, batch, report):
            handle.write(json.dumps(feature, separators=(",", ":")))
            handle.write("\n")
            if report.features % 20_000 == 0:
                print(f"  {report.features:,} features", flush=True)


def run_tippecanoe(src: str, dest: str) -> None:
    if shutil.which("tippecanoe") is None:
        raise RuntimeError(
            "tippecanoe is not installed. `brew install tippecanoe` (macOS) or build from "
            "github.com/felt/tippecanoe."
        )
    cmd = [
        "tippecanoe",
        "-o", dest,
        "--force",
        "-l", LAYER,
        f"--minimum-zoom={MIN_ZOOM}",
        f"--maximum-zoom={MAX_ZOOM}",
        # Parcels are the product: never drop one to hit a tile-size budget. Without these
        # tippecanoe silently thins dense blocks, and a parcel missing from the map is
        # indistinguishable to the user from a parcel that does not exist.
        "--no-feature-limit",
        "--no-tile-size-limit",
        "--drop-rate=0",
        # NOT --coalesce-densest-as-needed. It merges adjacent features that share
        # attributes into one, which silently destroys the identity of every feature but
        # the survivor — a parcel that no longer exists to be clicked. It cost 20 parcels
        # when this build first ran.
        #
        # Tiny-polygon reduction discards sub-pixel polygons; at maximum zoom that means
        # a handful of real (if minuscule) lots vanish entirely. Disabled at max zoom so
        # the deepest zoom is a complete record, and left on below it where a 20 m² lot is
        # genuinely smaller than a pixel and merging is the right call.
        "--no-tiny-polygon-reduction-at-maximum-zoom",
        # Simplify only below max zoom. At z15 a tile unit is ~0.23 m at DC's latitude, so
        # a 6 m² lot spans about 10 units and a tolerance of 4 collapses it outright — that
        # is what removed the last 5 parcels. The deepest zoom is the record the drill-down
        # and click targets depend on, so it stays geometrically exact; lower zooms keep
        # the tolerance, where it costs nothing visible and saves real bytes.
        "--simplification=4",
        "--simplify-only-low-zooms",
        src,
    ]
    print("  " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def run(out_dir: str = DEFAULT_OUT_DIR, database_url: str | None = None) -> TileReport:
    report = TileReport()
    os.makedirs(out_dir, exist_ok=True)

    with repo.connection(database_url) as conn:
        batch = repo.latest_batch_at(conn)
        if batch is None:
            raise RuntimeError("No bake results. Run `python -m bake.run_bake` first.")
        report.computed_at = batch

        stamp = batch.strftime("%Y%m%dT%H%M%S")
        dest = os.path.join(out_dir, f"parcels-{stamp}.pmtiles")
        print(f"[1/2] streaming features for batch {batch.isoformat()}...", flush=True)

        with tempfile.NamedTemporaryFile(
            "w", suffix=".geojsonl", delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            write_geojsonseq(conn, batch, tmp_path, report)
            print(f"      {report.features:,} features "
                  f"({report.invalid_repaired:,} geometries repaired, "
                  f"{report.skipped_too_small:,} below {MIN_RENDERABLE_AREA_M2:g} m², "
                  f"{report.skipped_no_geom:,} without geometry)", flush=True)
            print("[2/2] tippecanoe -> PMTiles...", flush=True)
            run_tippecanoe(tmp_path, dest)
        finally:
            os.unlink(tmp_path)

    report.output = dest
    report.bytes = os.path.getsize(dest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static parcel PMTiles (SPEC §10)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--keep", type=int, default=2,
                        help="tilesets to retain, matching bake retention (SPEC §9)")
    args = parser.parse_args()

    report = run(args.out_dir, args.database_url)

    # Retain as many tilesets as the bake retains batches, so a client holding a slightly
    # stale /meta can still fetch the tiles it was told about.
    tilesets = sorted(
        (f for f in os.listdir(args.out_dir) if f.endswith(".pmtiles")), reverse=True
    )
    for stale in tilesets[args.keep:]:
        os.unlink(os.path.join(args.out_dir, stale))

    print()
    print("=" * 68)
    print(f"TILES COMPLETE  {report.computed_at.isoformat()}")
    print("=" * 68)
    print(f"output         {report.output}")
    print(f"size           {report.bytes / 1e6:,.1f} MB")
    print(f"features       {report.features:,}")
    print(f"repaired       {report.invalid_repaired:,}")
    print(f"omitted        {len(report.skipped_ssls):,} "
          f"({report.skipped_too_small:,} below {MIN_RENDERABLE_AREA_M2:g} m², "
          f"{report.skipped_no_geom:,} without geometry)")
    print("status breakdown:")
    for status, count in sorted(report.status_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:<20} {count:>8,}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
