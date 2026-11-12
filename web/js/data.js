/**
 * Data pack loader, binary buffer decoders, and time-window index helpers.
 * Reads all array dimensions and physical constants dynamically from manifest.json.
 */

const IS_LITTLE_ENDIAN = (() => {
  const buf = new ArrayBuffer(2);
  new DataView(buf).setInt16(0, 1, true);
  return new Int16Array(buf)[0] === 1;
})();

export class DataLoadError extends Error {
  constructor(message, cause = null) {
    super(message);
    this.name = "DataLoadError";
    this.cause = cause;
  }
}

/**
 * Parse a UTC date or ISO timestamp string into UTC epoch milliseconds.
 */
export function parseUtcMs(str) {
  const trimmed = String(str).trim();
  let iso;
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    iso = `${trimmed}T00:00:00Z`;
  } else if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(trimmed)) {
    iso = `${trimmed.replace(" ", "T")}Z`;
  } else {
    iso = trimmed;
  }
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) {
    throw new Error(`Invalid UTC date/time string: "${str}"`);
  }
  return ms;
}

/**
 * Format UTC epoch milliseconds into human-readable UTC timestamp.
 */
export function formatUtc(ms, { includeSeconds = false, compact = false } = {}) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  const y = d.getUTCFullYear();
  const m = pad(d.getUTCMonth() + 1);
  const day = pad(d.getUTCDate());
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());
  const ss = pad(d.getUTCSeconds());
  if (compact) {
    return `${y}-${m}-${day} ${hh}:${mm}`;
  }
  return includeSeconds
    ? `${y}-${m}-${day}T${hh}:${mm}:${ss}Z`
    : `${y}-${m}-${day} ${hh}:${mm} UTC`;
}

/**
 * Format UTC epoch milliseconds as YYYY-MM-DD.
 */
export function formatUtcDate(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * Validate and index manifest.json without hardcoding point counts, region counts, or heights.
 */
export function parseManifest(raw) {
  if (!raw || !raw.constants || !raw.ephemeris || !raw.horizons || !Array.isArray(raw.regions) || !Array.isArray(raw.points)) {
    throw new DataLoadError("manifest.json is missing required layout fields.");
  }

  const regionsById = new Map();
  const pointsByRegion = new Map();
  for (const reg of raw.regions) {
    regionsById.set(reg.id, reg);
    pointsByRegion.set(reg.id, []);
  }

  const pointsById = new Map();
  for (const pt of raw.points) {
    pointsById.set(pt.id, pt);
    if (!pointsByRegion.has(pt.region)) {
      pointsByRegion.set(pt.region, []);
    }
    pointsByRegion.get(pt.region).push(pt);
  }

  const azStepDeg = Number(raw.constants.horizon_az_step_deg ?? 1);
  const nAz = Math.round(360 / azStepDeg);

  return {
    ...raw,
    nPoints: raw.points.length,
    nHeights: raw.observer_heights_m.length,
    azStepDeg,
    nAz,
    ephemStartMs: parseUtcMs(raw.ephemeris.start_utc),
    regionsById,
    pointsById,
    pointsByRegion,
  };
}

/**
 * Choose the default region ID on load: Malapert Massif if present, otherwise the first region.
 */
export function getDefaultRegionId(manifest) {
  if (!manifest || !Array.isArray(manifest.regions) || manifest.regions.length === 0) {
    return null;
  }
  const malapert = manifest.regions.find(
    (r) => r.id === "malapert-massif" || r.name === "Malapert Massif",
  );
  return malapert ? malapert.id : manifest.regions[0].id;
}

/**
 * Find the default center point for a region (prefers `<id>-c`, otherwise closest point to center).
 */
export function getRegionCenterPoint(manifest, regionId) {
  const pts = manifest.pointsByRegion.get(regionId) ?? [];
  if (pts.length === 0) return null;
  const centerById = manifest.pointsById.get(`${regionId}-c`);
  if (centerById) return centerById;

  const reg = manifest.regionsById.get(regionId);
  if (!reg) return pts[0];

  let best = pts[0];
  let bestD2 = Infinity;
  for (const pt of pts) {
    const dx = pt.x_m - reg.center_x_m;
    const dy = pt.y_m - reg.center_y_m;
    const d2 = dx * dx + dy * dy;
    if (d2 < bestD2) {
      bestD2 = d2;
      best = pt;
    }
  }
  return best;
}

/**
 * Decode ephem.bin ArrayBuffer into [n_times][2][3] little-endian float32 view.
 */
export function decodeEphemBuffer(buffer, manifest) {
  const nTimes = manifest.ephemeris.n_times;
  const expectedBytes = nTimes * 2 * 3 * 4;
  if (buffer.byteLength !== expectedBytes) {
    throw new DataLoadError(
      `ephem.bin byte size mismatch: expected ${expectedBytes} bytes from manifest, got ${buffer.byteLength}.`,
    );
  }

  let data;
  if (IS_LITTLE_ENDIAN) {
    data = new Float32Array(buffer);
  } else {
    const count = nTimes * 2 * 3;
    data = new Float32Array(count);
    const view = new DataView(buffer);
    for (let i = 0; i < count; i++) {
      data[i] = view.getFloat32(i * 4, true);
    }
  }

  return {
    data,
    nTimes,
    startUtcMs: manifest.ephemStartMs,
    stepS: Number(manifest.ephemeris.step_s),
  };
}

/**
 * Decode horizons.bin ArrayBuffer into [n_points][n_heights][n_az] little-endian int16 view.
 */
export function decodeHorizonsBuffer(buffer, manifest) {
  const { nPoints, nHeights, nAz } = manifest;
  const expectedBytes = nPoints * nHeights * nAz * 2;
  if (buffer.byteLength !== expectedBytes) {
    throw new DataLoadError(
      `horizons.bin byte size mismatch: expected ${expectedBytes} bytes from manifest, got ${buffer.byteLength}.`,
    );
  }

  let data;
  if (IS_LITTLE_ENDIAN) {
    data = new Int16Array(buffer);
  } else {
    const count = nPoints * nHeights * nAz;
    data = new Int16Array(count);
    const view = new DataView(buffer);
    for (let i = 0; i < count; i++) {
      data[i] = view.getInt16(i * 2, true);
    }
  }

  const scale = Number(manifest.horizons.scale ?? 0.01);
  const nodata = Number(manifest.horizons.nodata ?? -32768);
  const invScale = Math.round(1.0 / scale);
  const useExactDiv = Math.abs(scale * invScale - 1.0) < 1e-12;

  return {
    data,
    nPoints,
    nHeights,
    nAz,
    scale,
    invScale,
    useExactDiv,
    nodata,
  };
}

/**
 * Extract 1D Float64Array horizon profile (deg) for a point index and height index.
 */
export function extractHorizonDeg(horizons, pointIndex, heightIndex) {
  const { data, nHeights, nAz, scale, invScale, useExactDiv, nodata } = horizons;
  const offset = (pointIndex * nHeights + heightIndex) * nAz;
  const out = new Float64Array(nAz);
  for (let i = 0; i < nAz; i++) {
    const raw = data[offset + i];
    if (raw === nodata) {
      out[i] = -90.0;
    } else {
      out[i] = useExactDiv ? raw / invScale : raw * scale;
    }
  }
  return out;
}

/**
 * Compute allowed [minDateStr, maxDateStr] for a given durationDays within ephemeris range.
 */
export function getTimeRangeBounds(manifest, durationDays) {
  const stepS = Number(manifest.ephemeris.step_s);
  const nTimes = manifest.ephemeris.n_times;
  const startMs = manifest.ephemStartMs;
  const nSteps = Math.max(1, Math.round((durationDays * 86400.0) / stepS));
  const maxStartIdx = Math.max(0, nTimes - nSteps);
  const maxStartMs = startMs + maxStartIdx * stepS * 1000.0;
  // Floor to UTC midnight so <input type="date"> remains wholly within ephemeris bounds
  const maxDate = new Date(maxStartMs);
  const maxDateMidnightMs = Date.UTC(maxDate.getUTCFullYear(), maxDate.getUTCMonth(), maxDate.getUTCDate());
  const clampedMaxMs = Math.max(startMs, maxDateMidnightMs);

  return {
    minDateStr: formatUtcDate(startMs),
    maxDateStr: formatUtcDate(clampedMaxMs),
    maxDaysAvailable: Math.floor((nTimes * stepS) / 86400.0),
  };
}

/**
 * Resolve a start date + duration + optional step override into ephem.bin slice indices.
 */
export function getTimeWindow(manifest, startStr, durationDays, stepSOverride = null) {
  const ephemStepS = Number(manifest.ephemeris.step_s);
  const nTimes = manifest.ephemeris.n_times;
  const stepS = stepSOverride !== null ? Number(stepSOverride) : ephemStepS;
  const stride = Math.max(1, Math.round(stepS / ephemStepS));

  const reqStartMs = parseUtcMs(startStr);
  const rawStartIdx = Math.round((reqStartMs - manifest.ephemStartMs) / (ephemStepS * 1000.0));
  const nSteps = Math.max(1, Math.round((Number(durationDays) * 86400.0) / stepS));

  const maxStartIdx = Math.max(0, nTimes - 1 - (nSteps - 1) * stride);
  const startIdx = Math.max(0, Math.min(maxStartIdx, rawStartIdx));
  const clamped = startIdx !== rawStartIdx;
  const actualStartMs = manifest.ephemStartMs + startIdx * ephemStepS * 1000.0;

  return {
    startIdx,
    nSteps,
    stride,
    stepS,
    startMs: actualStartMs,
    startDateStr: formatUtcDate(actualStartMs),
    clamped,
  };
}

/**
 * Fetch a binary file while reporting byte progress.
 */
async function fetchBinaryWithProgress(url, onProgress) {
  let response;
  try {
    response = await fetch(url);
  } catch (err) {
    throw new DataLoadError(
      `Could not fetch "${url}". Please serve this folder over http, not file:// (for example: run "python -m http.server 8000" inside web/).`,
      err,
    );
  }

  if (!response.ok) {
    throw new DataLoadError(
      `HTTP ${response.status} while loading "${url}". Please serve this folder over http, not file://.`,
    );
  }

  const contentLength = Number(response.headers.get("content-length") || 0);
  if (!response.body || typeof response.body.getReader !== "function") {
    const buf = await response.arrayBuffer();
    if (onProgress) onProgress(buf.byteLength, buf.byteLength);
    return buf;
  }

  const reader = response.body.getReader();
  const chunks = [];
  let loaded = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    if (onProgress) onProgress(loaded, contentLength || loaded);
  }

  const out = new Uint8Array(loaded);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out.buffer;
}

/**
 * Load manifest.json, ephem.bin, and horizons.bin from relative data path.
 */
export async function loadDataPack(basePath = "data", onProgress = null) {
  if (typeof window !== "undefined" && window.location && window.location.protocol === "file:") {
    throw new DataLoadError(
      'This app cannot fetch data over file://. Please serve this folder over http, not file:// (for example: run "python -m http.server 8000" inside web/ and open http://localhost:8000/).',
    );
  }

  if (onProgress) {
    onProgress({ phase: "manifest", message: "Loading manifest metadata…", fraction: 0.05 });
  }

  let manifestResp;
  try {
    manifestResp = await fetch(`${basePath}/manifest.json`);
  } catch (err) {
    throw new DataLoadError(
      'Unable to fetch data/manifest.json. Please serve this folder over http, not file://.',
      err,
    );
  }
  if (!manifestResp.ok) {
    throw new DataLoadError(
      `Failed to load data/manifest.json (HTTP ${manifestResp.status}). Please serve this folder over http, not file://.`,
    );
  }

  const rawManifest = await manifestResp.json();
  const manifest = parseManifest(rawManifest);

  if (onProgress) {
    onProgress({ phase: "ephem", message: "Loading Sun/Earth ephemeris (ephem.bin)…", fraction: 0.15 });
  }
  const ephemBuf = await fetchBinaryWithProgress(`${basePath}/${manifest.ephemeris.file}`, (loaded, total) => {
    if (onProgress) {
      const frac = total > 0 ? loaded / total : 0.5;
      onProgress({
        phase: "ephem",
        message: `Loading ephem.bin (${(loaded / 1048576).toFixed(2)} MB)…`,
        fraction: 0.15 + 0.30 * frac,
      });
    }
  });
  const ephem = decodeEphemBuffer(ephemBuf, manifest);

  if (onProgress) {
    onProgress({ phase: "horizons", message: "Loading terrain horizons (horizons.bin)…", fraction: 0.45 });
  }
  const horizonsBuf = await fetchBinaryWithProgress(`${basePath}/${manifest.horizons.file}`, (loaded, total) => {
    if (onProgress) {
      const frac = total > 0 ? loaded / total : 0.5;
      onProgress({
        phase: "horizons",
        message: `Loading horizons.bin (${(loaded / 1048576).toFixed(2)} / ${(total / 1048576).toFixed(2)} MB)…`,
        fraction: 0.45 + 0.52 * frac,
      });
    }
  });
  const horizons = decodeHorizonsBuffer(horizonsBuf, manifest);

  if (onProgress) {
    onProgress({ phase: "ready", message: "Ready", fraction: 1.0 });
  }

  return { manifest, ephem, horizons };
}

const imageCache = new Map();

/**
 * Load and cache a regional hillshade PNG image.
 */
export function loadRegionImage(relPath, basePath = "data") {
  const url = `${basePath}/${relPath}`;
  if (imageCache.has(url)) {
    return imageCache.get(url);
  }
  const promise = new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new DataLoadError(`Failed to load region hillshade image "${url}".`));
    img.src = url;
  });
  imageCache.set(url, promise);
  return promise;
}
