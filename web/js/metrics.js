/**
 * Metric definitions, plain-language labels, Viridis colour scale, and lazy
 * region-wide map metric calculation for the site picker map.
 */

import {
  RAD_TO_DEG,
  siteLocalFrame,
  sitePositionKm,
  computeSunEarthAzEl,
} from "./geometry.js";
import {
  isDiscVisibleAny,
  isDiscVisibleMostly,
  stepDiscVisibleFraction,
  summarize,
} from "./visibility.js";
import { extractHorizonDeg, getTimeWindow } from "./data.js";

export const EARTH_VISIBILITY_NOTE =
  "Earth visibility here is geometric (line of sight to any part of Earth's disc), not a radio link budget.";

export const DURATION_OPTIONS = [7, 14, 30, 90, 365];
export const MAP_COLOR_MIN_STEP_S = 3600;
export const MAP_COLOR_MAX_DAYS = 90;

export const DEFAULT_MAP_METRIC_ID = "sun_illumination";

/**
 * Site Picker map metric options; stepValue reuses visibility.js threshold functions
 * used by summarize() so map colours and period metrics match identically.
 */
export const MAP_METRICS = [
  {
    id: "sun_illumination",
    label: "Sun illumination",
    shortLabel: "Illum",
    bodyIdx: 0,
    radiusKey: "sun_radius_km",
    legendMin: "0% sunlit",
    legendMid: "50%",
    legendMax: "100% sunlit",
    ariaLabel: "Sun illumination availability colour scale",
    stepValue: (frac) => frac,
  },
  {
    id: "earth_any",
    label: "Earth visible (any part)",
    shortLabel: "Earth (any)",
    bodyIdx: 1,
    radiusKey: "earth_radius_km",
    legendMin: "0% Earth (any)",
    legendMid: "50%",
    legendMax: "100% of the time",
    ariaLabel: "Geometric Earth visibility (any part) colour scale",
    stepValue: (frac) => (isDiscVisibleAny(frac) ? 1.0 : 0.0),
  },
  {
    id: "earth_mostly",
    label: "Earth more than half visible",
    shortLabel: "Earth (>50%)",
    bodyIdx: 1,
    radiusKey: "earth_radius_km",
    legendMin: "0% Earth (>50%)",
    legendMid: "50%",
    legendMax: "100% of the time",
    ariaLabel: "Earth more than half visible colour scale",
    stepValue: (frac) => (isDiscVisibleMostly(frac) ? 1.0 : 0.0),
  },
];

export const MAP_METRICS_BY_ID = new Map(MAP_METRICS.map((m) => [m.id, m]));

export function getMapMetricDefinition(metricId) {
  const def = MAP_METRICS_BY_ID.get(metricId);
  if (!def) {
    throw new Error(`Unknown map metric: "${metricId}"`);
  }
  return def;
}

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

export const VIRIDIS_LUT = Array.from({ length: 256 }, (_, k) => {
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
 * Map t in [0, 1] to a Viridis LUT index [0..255].
 */
export function viridisIndex(t) {
  const clamped = Math.max(0.0, Math.min(1.0, t));
  return Math.round(clamped * 255);
}

/**
 * Map t in [0, 1] to a colour-blind-safe Viridis RGB CSS string.
 */
export function viridisColor(t) {
  return VIRIDIS_LUT[viridisIndex(t)];
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
 * Compute a single site-picker map metric (fraction in [0, 1]) for one grid point
 * without allocating per-step output arrays (reuses visibility.js exact step and
 * threshold functions used by summarize()).
 */
export function computePointMapMetric({
  point,
  heightIdx,
  observerHeightM,
  timeWindow,
  manifest,
  ephem,
  horizons,
  metric = DEFAULT_MAP_METRIC_ID,
}) {
  const metricDef = getMapMetricDefinition(metric);
  const hor = extractHorizonDeg(horizons, point.index, heightIdx);
  const moonRadiusM = manifest.constants.moon_radius_m;
  const bodyRadiusKm = manifest.constants[metricDef.radiusKey];
  const bodyOffset = metricDef.bodyIdx * 3;
  const stepValue = metricDef.stepValue;
  const azStepDeg = manifest.azStepDeg;

  const { up, east, north } = siteLocalFrame(point.lat, point.lon);
  const rSite = sitePositionKm(
    point.lat,
    point.lon,
    point.ground_height_m,
    observerHeightM,
    moonRadiusM,
  );

  const rx = rSite[0], ry = rSite[1], rz = rSite[2];
  const u0 = up[0], u1 = up[1], u2 = up[2];
  const e0 = east[0], e1 = east[1], e2 = east[2];
  const n0 = north[0], n1 = north[1], n2 = north[2];

  const vecs = ephem.data;
  const { startIdx, nSteps, stride } = timeWindow;

  let sum = 0.0;
  for (let k = 0; k < nSteps; k++) {
    const base = (startIdx + k * stride) * 6 + bodyOffset;
    const vx = vecs[base] - rx;
    const vy = vecs[base + 1] - ry;
    const vz = vecs[base + 2] - rz;
    const invD = 1.0 / Math.sqrt(vx * vx + vy * vy + vz * vz);
    const ux = vx * invD;
    const uy = vy * invD;
    const uz = vz * invD;

    const dotE = ux * e0 + uy * e1 + uz * e2;
    const dotN = ux * n0 + uy * n1 + uz * n2;
    const dotU = ux * u0 + uy * u1 + uz * u2;

    let az = (Math.atan2(dotE, dotN) * RAD_TO_DEG) % 360.0;
    if (az < 0.0) az += 360.0;
    if (az >= 360.0) az -= 360.0;

    const el = Math.asin(Math.max(-1.0, Math.min(1.0, dotU))) * RAD_TO_DEG;
    const rDeg = Math.asin(Math.min(1.0, bodyRadiusKm * invD)) * RAD_TO_DEG;
    const frac = stepDiscVisibleFraction(az, el, rDeg, hor, azStepDeg);
    sum += stepValue(frac);
  }

  return nSteps > 0 ? sum / nSteps : 0.0;
}

/**
 * Compute only illumination_avg_fraction for a single grid point without allocating
 * per-step output arrays.
 */
export function computePointIlluminationFraction(opts) {
  return computePointMapMetric({ ...opts, metric: DEFAULT_MAP_METRIC_ID });
}

/**
 * Build cache key per region + height + window + metric.
 */
export function makeMapCacheKey({ regionId, heightIdx, timeWindow, metric = DEFAULT_MAP_METRIC_ID }) {
  return `${regionId}|${heightIdx}|${timeWindow.startIdx}|${timeWindow.nSteps}|${timeWindow.stride}|${metric}`;
}

/**
 * Compute the selected map metric lazily across all grid points in a region in small
 * time-budgeted chunks, yielding to the browser between chunks and caching results per
 * (regionId, heightIdx, startIdx, nSteps, stride, metric).
 */
export function computeRegionMapMetricLazy({
  regionId,
  regionPoints,
  heightIdx,
  observerHeightM,
  timeWindow,
  manifest,
  ephem,
  horizons,
  cache,
  metric = DEFAULT_MAP_METRIC_ID,
  onBatch,
  onDone,
  chunkBudgetMs = 5.0,
  maxBatchSize = 48,
}) {
  getMapMetricDefinition(metric);
  const cacheKey = makeMapCacheKey({ regionId, heightIdx, timeWindow, metric });
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
      const frac = computePointMapMetric({
        point: pt,
        heightIdx,
        observerHeightM,
        timeWindow,
        manifest,
        ephem,
        horizons,
        metric,
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

/**
 * Backward-compatible alias for lazy Sun illumination map calculation.
 */
export function computeRegionIlluminationLazy(opts) {
  return computeRegionMapMetricLazy({ metric: DEFAULT_MAP_METRIC_ID, ...opts });
}

/**
 * Choose the grid point with the maximum computed value in `valueMap`,
 * breaking ties by smallest squared distance to the region centre.
 */
export function pickMaxMetricPoint(points, valueMap, region) {
  if (!points || points.length === 0 || !valueMap) return null;
  const cx = region ? Number(region.center_x_m) : 0;
  const cy = region ? Number(region.center_y_m) : 0;
  let bestPt = null;
  let bestVal = -Infinity;
  let bestDist2 = Infinity;

  for (const pt of points) {
    const val = valueMap.get(pt.id);
    if (val === undefined || !Number.isFinite(val)) continue;
    const dx = pt.x_m - cx;
    const dy = pt.y_m - cy;
    const dist2 = dx * dx + dy * dy;
    if (val > bestVal || (val === bestVal && dist2 < bestDist2)) {
      bestVal = val;
      bestDist2 = dist2;
      bestPt = pt;
    }
  }
  return bestPt;
}

function formatStepInterval(stepS) {
  const s = Number(stepS);
  if (s >= 3600 && s % 3600 === 0) {
    return `${s / 3600} h`;
  }
  if (s >= 60 && s % 60 === 0) {
    return `${s / 60} min`;
  }
  return `${s} s`;
}

function formatWindowDays(mapTimeWindow) {
  const daysRaw = (mapTimeWindow.nSteps * mapTimeWindow.stepS) / 86400.0;
  const days =
    Math.abs(daysRaw - Math.round(daysRaw)) < 1e-6
      ? Math.round(daysRaw)
      : Number(daysRaw.toFixed(1));
  return { days, label: `${days} ${days === 1 ? "day" : "days"}` };
}

/**
 * Format the non-recommendation note shown when a max-metric site button is used,
 * naming the active map metric, real map time window, and observer height, plus
 * noting when the full period extends beyond the map window.
 */
export function formatMaxSelectedNote({
  nSites,
  metric = DEFAULT_MAP_METRIC_ID,
  mapTimeWindow,
  observerHeightM,
  days,
}) {
  if (!mapTimeWindow || !Number.isFinite(mapTimeWindow.nSteps) || !Number.isFinite(mapTimeWindow.stepS)) {
    throw new Error("formatMaxSelectedNote requires a valid mapTimeWindow");
  }
  const metricDef = getMapMetricDefinition(metric);
  const { days: mapDays, label: mapDaysLabel } = formatWindowDays(mapTimeWindow);
  const stepLabel = formatStepInterval(mapTimeWindow.stepS);
  const siteNoun = nSites === 1 ? "grid site" : "grid sites";
  const base =
    `Selected: highest '${metricDef.label}' among ${nSites} ${siteNoun} in this region ` +
    `(map window: first ${mapDaysLabel} at ${stepLabel} steps, ${observerHeightM} m observer height). ` +
    "This is not a recommendation.";
  const chosenDays = days !== undefined ? Number(days) : mapDays;
  if (chosenDays > mapDays + 1e-9) {
    return `${base} The cards below use your full period.`;
  }
  return base;
}
