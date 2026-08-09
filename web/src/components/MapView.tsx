/** The map: real DC parcel geometry from the static PMTiles, coloured by the baked bin.
 *
 * There is no basemap. That is a choice, not an omission — the handoff's map base is a
 * flat `--canvas` field with a single teal accent, DC's 132,604 parcels are dense enough
 * to draw the city on their own, and adding a raster basemap would mean an external tile
 * service, an API key, and attribution for something the design does not ask for.
 *
 * Selection and hover run through MapLibre feature state rather than by re-filtering a
 * layer, so hovering does not rebuild the tile's paint properties on every mouse move.
 * That needs stable feature ids, which is why the source promotes the tile's `id`
 * attribute (the parcel identifier the build already writes in place of "SSL").
 */
import { useEffect, useRef } from "react";
import maplibregl, {
  type FilterSpecification,
  type MapGeoJSONFeature,
} from "maplibre-gl";
import { PMTiles, Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import { PARCEL_BORDER, STATUS_COLORS, hatchImage, valueRamp } from "../lib/mapStyle";

const SCORED: FilterSpecification = ["==", ["get", "status"], "scored"];
const HATCH = "exempt-hatch";

const SOURCE = "parcels";
const LAYER = "parcels"; // the tippecanoe layer name, from tiles/build_tiles.py

// Registered once for the lifetime of the module: MapLibre keys protocols globally, and
// re-adding on every mount would leak handlers across remounts.
const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

export interface MapViewProps {
  /** Absolute or root-relative URL from /meta. Never a tileset from a different bake. */
  tilesetUrl: string;
  objective: string;
  selectedId: string | null;
  /** Parcels NOT matching this are dimmed, not hidden. Null means no filter. */
  filter: FilterSpecification | null;
  /** A search pick: fly here and select. */
  flyTo: { lon: number; lat: number; parcelId: string } | null;
  /** Fires with the parcel id and its screen position, so a popup can anchor to it. */
  onSelect: (parcelId: string, at: { x: number; y: number }) => void;
  /** Clicking bare canvas dismisses the popup. */
  onSelectNothing: () => void;
}

export function MapView({
  tilesetUrl,
  objective,
  selectedId,
  filter,
  flyTo,
  onSelect,
  onSelectNothing,
}: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const hovered = useRef<string | null>(null);
  // Held in a ref so the click handler, which is bound once, always calls the current
  // callback instead of the one captured at mount.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onSelectNothingRef = useRef(onSelectNothing);
  onSelectNothingRef.current = onSelectNothing;

  useEffect(() => {
    if (!container.current) return;

    const url = new URL(tilesetUrl, window.location.origin).href;
    // Hand MapLibre the same PMTiles instance we read the header from, so the header and
    // directory fetches are shared rather than issued twice.
    const archive = new PMTiles(url);
    protocol.add(archive);

    const instance = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          [SOURCE]: {
            type: "vector",
            url: `pmtiles://${url}`,
            promoteId: { [LAYER]: "id" },
          },
        },
        layers: [
          { id: "canvas", type: "background", paint: { "background-color": "#f4f2ed" } },
        ],
      },
      center: [-77.02, 38.9],
      zoom: 10.5,
      attributionControl: false,
      // The design is a desktop tool with a north-up map; pitch and rotate only add ways
      // to end up somewhere confusing.
      pitchWithRotate: false,
      dragRotate: false,
    });
    map.current = instance;

    // MapLibre reports source and tile failures through an `error` event; with no listener
    // they are easy to miss entirely. Surfacing them is worth the four lines.
    instance.on("error", (event) => {
      console.error("[map]", event.error?.message ?? event);
    });
    if (import.meta.env.DEV) {
      (window as unknown as { map?: maplibregl.Map }).map = instance;
    }

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");

    instance.on("load", () => {
      instance.addImage(HATCH, hatchImage(), { pixelRatio: 2 });

      // Land the model cannot price is drawn first and in neutrals, so it reads as the
      // ground the priced parcels sit on rather than competing with the value ramp.
      instance.addLayer({
        id: "parcels-exempt",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "exempt"],
        paint: { "fill-pattern": HATCH },
      });
      instance.addLayer({
        id: "parcels-infeasible",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "infeasible"],
        paint: { "fill-color": STATUS_COLORS.infeasible },
      });
      instance.addLayer({
        id: "parcels-historic",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "historic"],
        paint: { "fill-color": STATUS_COLORS.historic },
      });
      instance.addLayer({
        id: "parcels-not-covered",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "zone_not_encoded"],
        paint: { "fill-color": STATUS_COLORS.zone_not_encoded },
      });
      // Zoning we have not encoded yet gets a dashed edge: visibly provisional, rather
      // than a solid shape that implies we looked and found nothing.
      instance.addLayer({
        id: "parcels-not-covered-edge",
        type: "line",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "zone_not_encoded"],
        paint: {
          "line-color": STATUS_COLORS.zone_not_encoded_border,
          "line-width": 1.5,
          "line-dasharray": [2, 2],
        },
      });

      instance.addLayer({
        id: "parcels-value",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: SCORED,
        paint: { "fill-color": valueRamp(objective) },
      });

      // The white hairline between lots. Fades out when zoomed far enough that every lot
      // is a few pixels wide and the borders would be most of what you see.
      instance.addLayer({
        id: "parcels-border",
        type: "line",
        source: SOURCE,
        "source-layer": LAYER,
        paint: {
          "line-color": PARCEL_BORDER,
          "line-width": 1,
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0, 13, 1],
        },
      });

      // Filtered-OUT parcels are veiled in canvas colour rather than removed. Hiding two
      // thirds of the city leaves the matches floating with no street grid to locate them
      // against; dimming keeps the context and still reads instantly as "not these".
      instance.addLayer({
        id: "parcels-dim",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["literal", false],
        paint: { "fill-color": "#f4f2ed", "fill-opacity": 0.76 },
      });

      // brightness(1.08) has no MapLibre equivalent, so hover composites white at 8% —
      // which is what that filter does to these fills.
      instance.addLayer({
        id: "parcels-hover",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        paint: {
          "fill-color": "#ffffff",
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            0.08,
            0,
          ],
        },
      });

      // The selection ring: 3px white glow under a 2.5px ink stroke, per the handoff.
      // Drawn via feature state rather than a filter so selecting does not invalidate the
      // layer and re-parse tiles.
      for (const [id, color, width] of [
        ["parcels-selected-glow", "#ffffff", 5.5],
        ["parcels-selected", "#1a1d1c", 2.5],
      ] as const) {
        instance.addLayer({
          id,
          type: "line",
          source: SOURCE,
          "source-layer": LAYER,
          paint: {
            "line-color": color,
            "line-width": width,
            "line-opacity": [
              "case",
              ["boolean", ["feature-state", "selected"], false],
              1,
              0,
            ],
          },
        });
      }

      // Fit to what the tileset actually covers, rather than a hardcoded DC bbox that
      // would quietly go wrong if the parcel extract ever changed.
      archive
        .getHeader()
        .then((header) => {
          instance.fitBounds(
            [
              [header.minLon, header.minLat],
              [header.maxLon, header.maxLat],
            ],
            { padding: 28, duration: 0 },
          );
        })
        .catch(() => {
          /* keep the initial center — a failed fit is not worth blanking the map */
        });
    });

    const pickable = ["parcels-value", "parcels-infeasible", "parcels-historic",
                      "parcels-exempt", "parcels-not-covered"];

    const featureId = (feature: MapGeoJSONFeature) =>
      feature.id != null ? String(feature.id) : null;

    const setHover = (id: string | null) => {
      if (hovered.current === id) return;
      if (hovered.current) {
        instance.setFeatureState(
          { source: SOURCE, sourceLayer: LAYER, id: hovered.current },
          { hover: false },
        );
      }
      hovered.current = id;
      if (id) {
        instance.setFeatureState(
          { source: SOURCE, sourceLayer: LAYER, id },
          { hover: true },
        );
      }
      instance.getCanvas().style.cursor = id ? "pointer" : "";
    };

    instance.on("mousemove", (event) => {
      const [feature] = instance.queryRenderedFeatures(event.point, { layers: pickable });
      setHover(feature ? featureId(feature) : null);
    });
    instance.on("mouseout", () => setHover(null));

    instance.on("click", (event) => {
      const [feature] = instance.queryRenderedFeatures(event.point, { layers: pickable });
      const id = feature ? featureId(feature) : null;
      if (id) onSelectRef.current(id, { x: event.point.x, y: event.point.y });
      else onSelectNothingRef.current();
    });

    return () => {
      // The archive is deliberately left registered on the protocol. It is keyed by URL,
      // so a remount reuses it (header and directory already fetched) instead of paying
      // for them again, and the only way to evict it is a field the library marks hidden.
      instance.remove();
      map.current = null;
      hovered.current = null;
    };
  }, [tilesetUrl]);

  // Switching objective repaints from an attribute already in the tile — no refetch.
  useEffect(() => {
    const instance = map.current;
    if (!instance?.isStyleLoaded() || !instance.getLayer("parcels-value")) return;
    instance.setPaintProperty("parcels-value", "fill-color", valueRamp(objective));
  }, [objective]);

  // Filtering is a layer filter, not a refetch — the attributes are already in the tile.
  // The dim layer takes the NEGATION, so it veils exactly what the filter excludes.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (!instance.getLayer("parcels-dim")) return;
      instance.setFilter(
        "parcels-dim",
        filter ? (["!", filter] as FilterSpecification) : (["literal", false] as FilterSpecification),
      );
    };
    if (instance.isStyleLoaded()) apply();
    else instance.once("load", apply);
  }, [filter]);

  // A search pick flies the camera to the parcel. z17 is close enough that a single lot
  // fills a useful part of the view without losing the block around it.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !flyTo) return;
    const go = () => instance.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: 17, duration: 900 });
    if (instance.isStyleLoaded()) go();
    else instance.once("load", go);
  }, [flyTo]);

  // Selection is owned by the app (the panel and the map must agree), so the map follows
  // the prop rather than holding its own copy.
  const previousSelection = useRef<string | null>(null);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (previousSelection.current) {
        instance.setFeatureState(
          { source: SOURCE, sourceLayer: LAYER, id: previousSelection.current },
          { selected: false },
        );
      }
      previousSelection.current = selectedId;
      if (selectedId) {
        instance.setFeatureState(
          { source: SOURCE, sourceLayer: LAYER, id: selectedId },
          { selected: true },
        );
      }
    };
    if (instance.isStyleLoaded()) apply();
    else instance.once("load", apply);
  }, [selectedId]);

  return <div ref={container} style={{ position: "absolute", inset: 0 }} />;
}
