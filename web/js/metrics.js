/**
 * Metric definitions, plain-language labels, Viridis colour scale, and lazy
 * region-wide illumination calculation for the site picker map.
 */

import {
  siteLocalFrame,
  sitePositionKm,
  projectTopocentricInto,
  computeSunEarthAzEl,
} from "./geometry.js";
import {
  discVisibleFraction,
  interpHorizon,
  summarize,
} from "./visibility.js";
import { extractHorizonDeg, getTimeWindow } from "./data.js";

export const EARTH_VISIBILITY_NOTE =
  "Earth visibility here is geometric (line of sight to any part of Earth's disc), not a radio link budget.";

export const DURATION_OPTIONS = [7, 14, 30, 90, 365];
export const MAP_COLOR_MIN_STEP_S = 3600;
export const MAP_COLOR_MAX_DAYS = 90;

/**
 * Exact 6 metric cards and one-line plain-language help descriptions.
 */
export const METRIC_DEFINITIONS = [
  {
    key: "illumination_avg_fraction",
    label: "Illumination availability",
    help: "Average fraction of the solar disc visible over the selected period.",
    format: (v) => `${(v * 100).toFixed(1)}%`,
    subFormat: (v) => `${v.toFixed(3)} avg disc`,
    kind: "fraction",
    accent: "sun",
  },
  {
    key: "sun_any_pct",
    label: "Sun visible (any part)",
    help: "Share of time when at least part of the Sun rises above terrain.",
    format: (v) => `${v.toFixed(1)}%`,
    subFormat: () => "any sliver > 0%",
    kind: "percent",
    accent: "sun",
  },
  {
    key: "sun_longest_dark_h",
    label: "Longest continuous darkness",
    help: "Longest unbroken stretch with zero direct sunlight.",
    format: (v) => `${v.toFixed(1)} h`,
    subFormat: (v) => (v >= 24 ? `${(v / 24).toFixed(1)} Earth days` : "continuous shadow"),
    kind: "hours",
    accent: "neutral",
  },
  {
    key: "earth_any_pct",
    label: "Geometric Earth visibility (any part of the disc)",
    help: "Share of time when any part of Earth has line of sight above terrain.",
    format: (v) => `${v.toFixed(1)}%`,
    subFormat: () => "line of sight > 0%",
    kind: "percent",
    accent: "earth",
  },
  {
    key: "earth_mostly_pct",
    label: "Earth more than half visible",
    help: "Share of time when over half of Earth's disc clears the horizon.",
    format: (v) => `${v.toFixed(1)}%`,
    subFormat: () => "disc visible > 50%",
    kind: "percent",
    accent: "earth",
  },
  {
    key: "earth_longest_blackout_h",
    label: "Longest Earth-visibility blackout",
    help: "Longest unbroken period with zero geometric line of sight to Earth.",
    format: (v) => `${v.toFixed(1)} h`,
    subFormat: (v) => (v >= 24 ? `${(v / 24).toFixed(1)} Earth days` : "continuous blockage"),
    kind: "hours",
    accent: "neutral",
  },
];

// Colour-blind-safe Viridis stops for 0..1 illumination dots on grayscale hillshade
const VIRIDIS_STOPS = [
  [68, 1, 84],
  [72, 40, 120],
  [62, 74, 137],
  [49, 104, 142],
  [38, 130, 142],
  [31, 158, 137],
  [53, 183, 121],
  [109, 205, 89],
  [180, 222, 44],
  [253, 231, 37],
];

const VIRIDIS_LUT = Array.from({ length: 256 }, (_, k) => {
  const t = k / 255;
  const scaled = t * (VIRIDIS_STOPS.length - 1);
  const idx = Math.floor(scaled);
  const frac = scaled - idx;
  const c0 = VIRIDIS_STOPS[idx];
  const c1 = VIRIDIS_STOPS[Math.min(VIRIDIS_STOPS.length - 1, idx + 1)];
  const r = Math.round(c0[0] + frac * (c1[0] - c0[0]));
  const g = Math.round(c0[1] + frac * (c1[1] - c0[1]));
  const b = Math.round(c0[2] + frac * (c1[2] - c0[2]));
  return `rgb(${r}, ${g}, ${b})`;
});

/**
 * Map t in [0, 1] to a colour-blind-safe Viridis RGB CSS string.
 */
export function viridisColor(t) {
  const clamped = Math.max(0.0, Math.min(1.0, t));
  return VIRIDIS_LUT[Math.round(clamped * 255)];
}

/**
 * Resolve a coarse, capped time window for region colour-map computation:
 * time step at least 3600 s and duration at most 90 days.
 */
export function getColorMapTimeWindow(manifest, startDate, days) {
  const ephemStepS = Number(manifest.ephemeris.step_s);
  const stepS = Math.max(
    MAP_COLOR_MIN_STEP_S,
    Math.ceil(MAP_COLOR_MIN_STEP_S / ephemStepS) * ephemStepS,
  );
  const cappedDays = Math.min(Number(days), MAP_COLOR_MAX_DAYS);
  return getTimeWindow(manifest, startDate, cappedDays, stepS);
}

/**
 * Full evaluation for the currently selected site, height, and time window.
 */
export function evaluateSite({
  point,
  heightIdx,
  observerHeightM,
  timeWindow,
  manifest,
  ephem,
  horizons,
}) {
  const hor = extractHorizonDeg(horizons, point.index, heightIdx);
  const azel = computeSunEarthAzEl({
    lat: point.lat,
    lon: point.lon,
    groundHeightM: point.ground_height_m,
    observerHeightM,
    startIdx: timeWindow.startIdx,
    nSteps: timeWindow.nSteps,
    stride: timeWindow.stride,
    ephemData: ephem,
    constants: manifest.constants,
  });

  const summary = summarize({
    hor,
    groundHeightM: point.ground_height_m,
    sunAz: azel.sunAz,
    sunEl: azel.sunEl,
    sunR: azel.sunR,
    earthAz: azel.earthAz,
    earthEl: azel.earthEl,
    earthR: azel.earthR,
    lat: point.lat,
    lon: point.lon,
    start: timeWindow.startDateStr,
    days: (timeWindow.nSteps * timeWindow.stepS) / 86400.0,
    observerHeightM,
    stepS: timeWindow.stepS,
    azStepDeg: manifest.azStepDeg,
  });

  return {
    point,
    hor,
    azel,
    summary,
  };
}

/**
 * Compute only illumination_avg_fraction for a single grid point without allocating
 * per-step output arrays (shares geometry.js & visibility.js exact formulas).
 */
export function computePointIlluminationFraction({
  point,
  heightIdx,
  observerHeightM,
  timeWindow,
  manifest,
  ephem,
  horizons,
}) {
  const hor = extractHorizonDeg(horizons, point.index, heightIdx);
  const moonRadiusM = manifest.constants.moon_radius_m;
  const sunRadiusKm = manifest.constants.sun_radius_km;
  const azStepDeg = manifest.azStepDeg;

  const frame = siteLocalFrame(point.lat, point.lon);
  const rSite = sitePositionKm(
    point.lat,
    point.lon,
    point.ground_height_m,
    observerHeightM,
    moonRadiusM,
  );

  const vecs = ephem.data;
  const { startIdx, nSteps, stride } = timeWindow;
  const tmp = new Float64Array(3);

  let svSum = 0.0;
  for (let k = 0; k < nSteps; k++) {
    const base = (startIdx + k * stride) * 6;
    projectTopocentricInto(
      vecs[base],
      vecs[base + 1],
      vecs[base + 2],
      rSite,
      frame,
      sunRadiusKm,
      tmp,
    );
    const hz = interpHorizon(hor, tmp[0], azStepDeg);
    const t = (tmp[1] - hz) / tmp[2];
    svSum += discVisibleFraction(t);
  }

  return nSteps > 0 ? svSum / nSteps : 0.0;
}

/**
 * Compute illumination_avg_fraction lazily across all grid points in a region in small
 * time-budgeted chunks, yielding to the browser between chunks and caching results per
 * (regionId, heightIdx, startIdx, nSteps, stride).
 */
export function computeRegionIlluminationLazy({
  regionId,
  regionPoints,
  heightIdx,
  observerHeightM,
  timeWindow,
  manifest,
  ephem,
  horizons,
  cache,
  onBatch,
  onDone,
  chunkBudgetMs = 6.0,
  maxBatchSize = 48,
}) {
  const cacheKey = `${regionId}|${heightIdx}|${timeWindow.startIdx}|${timeWindow.nSteps}|${timeWindow.stride}`;
  if (cache.has(cacheKey)) {
    const cached = cache.get(cacheKey);
    if (onDone) onDone(cached, regionPoints.length);
    return () => {};
  }

  const resultMap = new Map();
  if (regionPoints.length === 0) {
    cache.set(cacheKey, resultMap);
    if (onDone) onDone(resultMap, 0);
    return () => {};
  }

  let cancelled = false;
  let scheduledHandle = null;
  let cursor = 0;
  const nowMs = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

  function scheduleNext(fn) {
    if (cancelled) return;
    const useRaf =
      typeof requestAnimationFrame === "function" &&
      (typeof document === "undefined" || !document.hidden);
    if (useRaf) {
      scheduledHandle = { kind: "raf", id: requestAnimationFrame(fn) };
    } else {
      scheduledHandle = { kind: "timeout", id: setTimeout(fn, 0) };
    }
  }

  function step() {
    scheduledHandle = null;
    if (cancelled) return;

    const chunkStart = nowMs();
    let processedInChunk = 0;
    while (cursor < regionPoints.length) {
      const pt = regionPoints[cursor];
      const frac = computePointIlluminationFraction({
        point: pt,
        heightIdx,
        observerHeightM,
        timeWindow,
        manifest,
        ephem,
        horizons,
      });
      resultMap.set(pt.id, frac);
      cursor += 1;
      processedInChunk += 1;

      if (processedInChunk >= maxBatchSize || nowMs() - chunkStart >= chunkBudgetMs) {
        break;
      }
    }

    if (cancelled) return;

    if (cursor < regionPoints.length) {
      if (onBatch) onBatch(resultMap, cursor, regionPoints.length);
      if (!cancelled) scheduleNext(step);
    } else {
      cache.set(cacheKey, resultMap);
      if (onDone) onDone(resultMap, regionPoints.length);
    }
  }

  scheduleNext(step);
  return () => {
    cancelled = true;
    if (scheduledHandle) {
      if (scheduledHandle.kind === "raf" && typeof cancelAnimationFrame === "function") {
        cancelAnimationFrame(scheduledHandle.id);
      } else {
        clearTimeout(scheduledHandle.id);
      }
      scheduledHandle = null;
    }
  };
}
