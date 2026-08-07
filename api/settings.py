"""Runtime configuration, read from the environment once at import."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    # Where `tiles/build_tiles.py` writes its PMTiles. Served as flat files (SPEC §10:
    # static tiles regenerated once per bake, no live tile server).
    tiles_dir: str = field(default_factory=lambda: os.environ.get("TILES_DIR", "tiles/build"))
    tiles_url_prefix: str = field(
        default_factory=lambda: os.environ.get("TILES_URL_PREFIX", "/tiles")
    )
    cors_origins: list[str] = field(default_factory=_origins)

    # The IRR filter runs the full model per parcel (~20ms each), so it is bounded rather
    # than allowed to fan out across the whole scored set (79k parcels would be ~26 min).
    # Narrow with the other filters first; above this the API refuses with a plain message.
    max_irr_filter_parcels: int = field(
        default_factory=lambda: int(os.environ.get("MAX_IRR_FILTER_PARCELS", "2000"))
    )
    # Page ceiling for /map/query. The table view pages; the map reads tiles, not this.
    max_page_size: int = 5_000


settings = Settings()
