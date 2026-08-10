/** The map: real DC parcel geometry from the static PMTiles, colored by the baked bin.
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
import {
  DRAW_ACCENT,
  DRAW_MASK_COLOR,
  DRAW_MASK_OPACITY,
  FILL_OPACITY,
  PARCEL_BORDER,
  STATUS_COLORS,
  hatchImage,
  valueRamp,
} from "../lib/mapStyle";
import {
  closeRing,
  maskFor,
  withinHandle,
  type Position,
  type Ring,
} from "../lib/drawRing";

const SCORED: FilterSpecification = ["==", ["get", "status"], "scored"];
const HATCH = "exempt-hatch";

const SOURCE = "parcels";
const LAYER = "parcels"; // the tippecanoe layer name, from tiles/build_tiles.py

// The draw tool's own sources. Plain GeoJSON, rewritten with setData as the user clicks.
const MASK_SOURCE = "draw-mask";
const AREA_SOURCE = "draw-area";
const SKETCH_SOURCE = "draw-sketch";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** One feature wrapping a geometry, for a setData call. */
function only(geometry: GeoJSON.Geometry | null): GeoJSON.FeatureCollection {
  return geometry
    ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry }] }
    : EMPTY;
}

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
  /** Draw mode: clicks place corners instead of selecting parcels. */
  drawing: boolean;
  /** The committed area, drawn as an outline with everything outside it veiled. */
  drawnPolygon: Ring | null;
  /** A closed ring. The app decides what to do with it — the map does not filter itself. */
  onDrawComplete: (ring: Ring) => void;
  /** Escape, or a click that cannot become an area. */
  onDrawCancel: () => void;
  /** Corner count while drawing, so the toolbar can say "3 corners — click the first to
   * close" without the map owning any copy. */
  onDrawProgress: (corners: number) => void;
}

export function MapView({
  tilesetUrl,
  objective,
  selectedId,
  filter,
  flyTo,
  onSelect,
  onSelectNothing,
  drawing,
  drawnPolygon,
  onDrawComplete,
  onDrawCancel,
  onDrawProgress,
}: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const hovered = useRef<string | null>(null);
  // Held in refs so the click handler, bound once at mount, always calls the CURRENT
  // callback rather than the one captured then. Assigned in an effect, not during render —
  // mutating a ref while rendering is a React rule violation, and effects still run before
  // any click can arrive.
  const onSelectRef = useRef(onSelect);
  const onSelectNothingRef = useRef(onSelectNothing);
  const onDrawCompleteRef = useRef(onDrawComplete);
  const onDrawCancelRef = useRef(onDrawCancel);
  const onDrawProgressRef = useRef(onDrawProgress);
  // Draw state lives in refs, not React state: the handlers are bound once at mount, and a
  // re-render per placed corner would rebuild them for no benefit. The app is told the
  // corner count through `onDrawProgress` and owns nothing else.
  const drawingRef = useRef(drawing);
  const cornersRef = useRef<Position[]>([]);
  // Set by the mount effect so the `drawing` prop effect can discard a half-drawn ring.
  const clearSketchRef = useRef<(() => void) | null>(null);
  // The objective is read once when the layers are created; the effect below repaints on
  // every later change, so this only has to be right at mount.
  const objectiveRef = useRef(objective);
  useEffect(() => {
    onSelectRef.current = onSelect;
    onSelectNothingRef.current = onSelectNothing;
    onDrawCompleteRef.current = onDrawComplete;
    onDrawCancelRef.current = onDrawCancel;
    onDrawProgressRef.current = onDrawProgress;
    objectiveRef.current = objective;
  });

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
        paint: { "fill-pattern": HATCH, "fill-opacity": FILL_OPACITY },
      });
      instance.addLayer({
        id: "parcels-infeasible",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "infeasible"],
        paint: { "fill-color": STATUS_COLORS.infeasible, "fill-opacity": FILL_OPACITY },
      });
      instance.addLayer({
        id: "parcels-historic",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "historic"],
        paint: { "fill-color": STATUS_COLORS.historic, "fill-opacity": FILL_OPACITY },
      });
      instance.addLayer({
        id: "parcels-not-covered",
        type: "fill",
        source: SOURCE,
        "source-layer": LAYER,
        filter: ["==", ["get", "status"], "zone_not_encoded"],
        paint: { "fill-color": STATUS_COLORS.zone_not_encoded, "fill-opacity": FILL_OPACITY },
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
        paint: {
          "fill-color": valueRamp(objectiveRef.current),
          "fill-opacity": FILL_OPACITY,
        },
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

      // Filtered-OUT parcels are veiled in canvas color rather than removed. Hiding two
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

      // The selection ring. A white glow under an ink stroke, both heavier than the
      // handoff's 3px/2.5px: at city zoom a single lot is a few pixels across, and a
      // hairline ring around it was indistinguishable from the parcel borders around it.
      // The ring also does NOT fade with zoom, unlike those borders — the whole point is
      // that you can still find the parcel you are assessing after panning away.
      //
      // Drawn via feature state rather than a filter so selecting does not invalidate the
      // layer and re-parse tiles.
      for (const [id, color, width] of [
        ["parcels-selected-glow", "#ffffff", 8],
        ["parcels-selected", "#1a1d1c", 3.5],
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

      // --- the draw-an-area tool ------------------------------------------
      for (const id of [MASK_SOURCE, AREA_SOURCE, SKETCH_SOURCE]) {
        instance.addSource(id, { type: "geojson", data: EMPTY });
      }

      // The veil. A drawn area cannot be a MapLibre filter — point-in-polygon is not
      // expressible over tile attributes — so instead of hiding the parcels outside it,
      // this covers the world and leaves a hole where the selection is. Same grammar as
      // `parcels-dim`, and it sits directly on top of it for the same reason: hover and
      // the selection ring are added after, so they stay legible through the veil.
      instance.addLayer(
        {
          id: "draw-mask",
          type: "fill",
          source: MASK_SOURCE,
          paint: { "fill-color": DRAW_MASK_COLOR, "fill-opacity": DRAW_MASK_OPACITY },
        },
        "parcels-hover",
      );

      // The committed outline. Dashed, so it reads as an annotation over the city rather
      // than as another parcel boundary.
      instance.addLayer({
        id: "draw-area-line",
        type: "line",
        source: AREA_SOURCE,
        paint: {
          "line-color": DRAW_ACCENT,
          "line-width": 2,
          "line-dasharray": [3, 2],
        },
      });

      // The rubber band, while drawing: placed corners, plus a segment to the cursor.
      instance.addLayer({
        id: "draw-sketch-fill",
        type: "fill",
        source: SKETCH_SOURCE,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": DRAW_ACCENT, "fill-opacity": 0.1 },
      });
      instance.addLayer({
        id: "draw-sketch-line",
        type: "line",
        source: SKETCH_SOURCE,
        filter: ["!=", ["geometry-type"], "Point"],
        paint: { "line-color": DRAW_ACCENT, "line-width": 2 },
      });
      instance.addLayer({
        id: "draw-sketch-vertices",
        type: "circle",
        source: SKETCH_SOURCE,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          // The first corner is the close handle, so it is drawn larger than the rest —
          // the target has to look like a target before you can be asked to hit it.
          "circle-radius": ["case", ["get", "first"], 6, 4],
          "circle-color": "#ffffff",
          "circle-stroke-color": DRAW_ACCENT,
          "circle-stroke-width": 2,
        },
      });

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

    // --- draw mode ---------------------------------------------------------
    /** Repaint the in-progress sketch: the placed corners, the line through them, and a
     * rubber band out to wherever the cursor is. `null` cursor means "not hovering", which
     * happens between a click and the next mouse move. */
    const paintSketch = (cursor: Position | null) => {
      const source = instance.getSource(SKETCH_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (!source) return;
      const corners = cornersRef.current;
      if (!corners.length) {
        source.setData(EMPTY);
        return;
      }
      const path = cursor ? [...corners, cursor] : corners;
      const features: GeoJSON.Feature[] = corners.map((position, index) => ({
        type: "Feature",
        properties: { first: index === 0 },
        geometry: { type: "Point", coordinates: position },
      }));
      if (path.length > 1) {
        features.push({
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: path },
        });
      }
      // Three corners is the first point at which there is an area to preview, so the
      // translucent fill appears exactly when the shape becomes a shape.
      if (path.length > 2) {
        features.push({
          type: "Feature",
          properties: {},
          geometry: { type: "Polygon", coordinates: [[...path, path[0] as Position]] },
        });
      }
      source.setData({ type: "FeatureCollection", features });
    };

    const clearSketch = () => {
      cornersRef.current = [];
      paintSketch(null);
      onDrawProgressRef.current(0);
    };

    /** Try to close. Refuses silently if the ring is not one — `closeRing` returns null for
     * a bow tie, a collinear run, or fewer than three corners — because the alternative is
     * scolding the user for a shape they can simply keep drawing out of. */
    const finish = () => {
      const ring = closeRing(cornersRef.current);
      if (!ring) return;
      clearSketch();
      onDrawCompleteRef.current(ring);
    };

    instance.on("mousemove", (event) => {
      if (drawingRef.current) {
        paintSketch([event.lngLat.lng, event.lngLat.lat]);
        return;
      }
      const [feature] = instance.queryRenderedFeatures(event.point, { layers: pickable });
      setHover(feature ? featureId(feature) : null);
    });
    instance.on("mouseout", () => {
      if (drawingRef.current) paintSketch(null);
      else setHover(null);
    });

    instance.on("click", (event) => {
      if (drawingRef.current) {
        const first = cornersRef.current.at(0);
        // Clicking the first corner closes the ring. Tested in screen space, not degrees:
        // "within ten pixels of that dot" is what the user is actually aiming at, and it
        // has to mean the same thing at every zoom.
        if (first && cornersRef.current.length >= 3) {
          const handle = instance.project(first);
          if (withinHandle(event.point, handle)) {
            finish();
            return;
          }
        }
        cornersRef.current = [...cornersRef.current, [event.lngLat.lng, event.lngLat.lat]];
        paintSketch(null);
        onDrawProgressRef.current(cornersRef.current.length);
        return;
      }
      const [feature] = instance.queryRenderedFeatures(event.point, { layers: pickable });
      const id = feature ? featureId(feature) : null;
      if (id) onSelectRef.current(id, { x: event.point.x, y: event.point.y });
      else onSelectNothingRef.current();
    });

    // Double-click closes. MapLibre's own double-click zoom is disabled for the duration
    // in the effect below, or the closing gesture would also zoom the map in.
    instance.on("dblclick", (event) => {
      if (!drawingRef.current) return;
      event.preventDefault();
      finish();
    });

    // Escape cancels, Enter closes, Backspace takes back the last corner. Bound to the
    // window rather than the canvas because the canvas is not focusable and the user's
    // focus is wherever they last clicked in the surrounding UI.
    const onKey = (event: KeyboardEvent) => {
      if (!drawingRef.current) return;
      if (event.key === "Escape") {
        clearSketch();
        onDrawCancelRef.current();
      } else if (event.key === "Enter") {
        finish();
      } else if (event.key === "Backspace" || event.key === "Delete") {
        event.preventDefault();
        cornersRef.current = cornersRef.current.slice(0, -1);
        paintSketch(null);
        onDrawProgressRef.current(cornersRef.current.length);
      }
    };
    window.addEventListener("keydown", onKey);
    // Exposed so the effect that reacts to the `drawing` prop can wipe a half-drawn ring
    // when the mode is turned off from the toolbar.
    clearSketchRef.current = clearSketch;

    return () => {
      window.removeEventListener("keydown", onKey);
      clearSketchRef.current = null;
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

  // Draw mode. The cursor, MapLibre's double-click zoom, and any half-drawn ring all
  // follow the prop — the toolbar button owns the mode, the map only obeys it.
  useEffect(() => {
    drawingRef.current = drawing;
    const instance = map.current;
    if (!instance) return;
    instance.getCanvas().style.cursor = drawing ? "crosshair" : "";
    if (drawing) instance.doubleClickZoom.disable();
    else {
      instance.doubleClickZoom.enable();
      // Leaving draw mode with corners on screen would strand an outline that no longer
      // responds to clicks.
      clearSketchRef.current?.();
    }
  }, [drawing]);

  // The committed area: its outline, and the veil over everything outside it.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      const mask = instance.getSource(MASK_SOURCE) as maplibregl.GeoJSONSource | undefined;
      const area = instance.getSource(AREA_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (!mask || !area) return;
      mask.setData(only(drawnPolygon ? maskFor(drawnPolygon) : null));
      area.setData(only(drawnPolygon));
    };
    if (instance.isStyleLoaded() && instance.getSource(MASK_SOURCE)) apply();
    else instance.once("idle", apply);
  }, [drawnPolygon]);

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
