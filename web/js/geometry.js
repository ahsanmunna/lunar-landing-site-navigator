/**
 * Coordinate transformations, local topocentric frames, and Sun/Earth az/el computation.
 * Exact JavaScript port of lunar_engine/geometry.py and lunar_engine/ephemeris.py (sun_earth_azel).
 */

export const DEG_TO_RAD = Math.PI / 180.0;
export const RAD_TO_DEG = 180.0 / Math.PI;
export const DEFAULT_MOON_RADIUS_M = 1737400.0;

/**
 * Convert (lat, lon) in degrees to south polar stereographic (x, y) in metres.
 * Near side is up (+y direction, lon=0), east is right (+x direction, lon=90).
 */
export function forward(lat, lon, rMoonM = DEFAULT_MOON_RADIUS_M) {
  const colat = (90.0 + lat) * DEG_TO_RAD;
  const rho = 2.0 * rMoonM * Math.tan(colat / 2.0);
  const lonRad = lon * DEG_TO_RAD;
  return {
    x: rho * Math.sin(lonRad),
    y: rho * Math.cos(lonRad),
  };
}

/**
 * Convert south polar stereographic (x, y) in metres to (lat, lon) in degrees.
 * At (0, 0), returns { lat: -90.0, lon: 0.0 }.
 */
export function inverse(x, y, rMoonM = DEFAULT_MOON_RADIUS_M) {
  const rho = Math.hypot(x, y);
  if (rho === 0.0) {
    return { lat: -90.0, lon: 0.0 };
  }
  const colat = 2.0 * Math.atan(rho / (2.0 * rMoonM));
  const lat = colat * RAD_TO_DEG - 90.0;
  const lon = Math.atan2(x, y) * RAD_TO_DEG;
  return { lat, lon };
}

/**
 * Return 3D unit vectors (up, east, north) in the MOON_ME frame at (lat, lon).
 * Matches numpy.isclose(lat, -90.0) handling in lunar_engine/geometry.py.
 */
export function siteLocalFrame(lat, lon) {
  if (Math.abs(lat + 90.0) <= 1e-8 + 1e-5 * 90.0) {
    return {
      up: [0.0, 0.0, -1.0],
      east: [0.0, 1.0, 0.0],
      north: [1.0, 0.0, 0.0],
    };
  }
  const la = lat * DEG_TO_RAD;
  const lo = lon * DEG_TO_RAD;
  const cosLa = Math.cos(la);
  const sinLa = Math.sin(la);
  const cosLo = Math.cos(lo);
  const sinLo = Math.sin(lo);

  return {
    up: [cosLa * cosLo, cosLa * sinLo, sinLa],
    east: [-sinLo, cosLo, 0.0],
    north: [-sinLa * cosLo, -sinLa * sinLo, cosLa],
  };
}

/**
 * Return 3D position vector in km in MOON_ME for an observer at the site.
 */
export function sitePositionKm(
  lat,
  lon,
  groundHeightM,
  observerHeightM,
  moonRadiusM = DEFAULT_MOON_RADIUS_M,
) {
  const { up } = siteLocalFrame(lat, lon);
  const rKm = (moonRadiusM + groundHeightM + observerHeightM) / 1000.0;
  return [rKm * up[0], rKm * up[1], rKm * up[2]];
}

/**
 * Compute apparent angular radius in degrees: asin(R / distance).
 */
export function angularRadiusDeg(radiusKm, distanceKm) {
  const ratio = Math.max(-1.0, Math.min(1.0, radiusKm / distanceKm));
  return Math.asin(ratio) * RAD_TO_DEG;
}

/**
 * Project a Moon-centred body vector (bx, by, bz) km into the site's local (az, el, rDeg).
 * Writes [az, el, rDeg] into the pre-allocated `out` array to avoid per-step allocations.
 */
export function projectTopocentricInto(bx, by, bz, rSite, frame, radiusKm, out) {
  const vx = bx - rSite[0];
  const vy = by - rSite[1];
  const vz = bz - rSite[2];
  const distKm = Math.hypot(vx, vy, vz);
  const invD = 1.0 / distKm;
  const ux = vx * invD;
  const uy = vy * invD;
  const uz = vz * invD;

  const { up, east, north } = frame;
  const dotE = ux * east[0] + uy * east[1] + uz * east[2];
  const dotN = ux * north[0] + uy * north[1] + uz * north[2];
  const dotU = ux * up[0] + uy * up[1] + uz * up[2];

  let az = (Math.atan2(dotE, dotN) * RAD_TO_DEG) % 360.0;
  if (az < 0.0) az += 360.0;
  if (az >= 360.0) az -= 360.0;

  out[0] = az;
  out[1] = Math.asin(Math.max(-1.0, Math.min(1.0, dotU))) * RAD_TO_DEG;
  out[2] = Math.asin(Math.min(1.0, radiusKm * invD)) * RAD_TO_DEG;
}

/**
 * Compute topocentric az, el, and angular radius track for one body (0=SUN, 1=EARTH).
 */
function fillBodyTrack({
  vecs,
  bodyIdx,
  rSite,
  frame,
  radiusKm,
  startIdx,
  nSteps,
  stride,
  azOut,
  elOut,
  rOut,
}) {
  const bodyOffset = bodyIdx * 3;
  const tmp = new Float64Array(3);
  for (let k = 0; k < nSteps; k++) {
    const base = (startIdx + k * stride) * 6 + bodyOffset;
    projectTopocentricInto(
      vecs[base],
      vecs[base + 1],
      vecs[base + 2],
      rSite,
      frame,
      radiusKm,
      tmp,
    );
    azOut[k] = tmp[0];
    elOut[k] = tmp[1];
    rOut[k] = tmp[2];
  }
}

/**
 * Compute Sun and Earth azimuth, elevation, and angular radii over a time window
 * from precomputed Moon-centred vectors in ephem.bin (float32 km, MOON_ME frame).
 *
 * Matches lunar_engine/ephemeris.py sun_earth_azel().
 */
export function computeSunEarthAzEl({
  lat,
  lon,
  groundHeightM,
  observerHeightM,
  startIdx,
  nSteps,
  stride = 1,
  ephemData,
  constants,
}) {
  const moonRadiusM = constants.moon_radius_m;
  const sunRadiusKm = constants.sun_radius_km;
  const earthRadiusKm = constants.earth_radius_km;

  const frame = siteLocalFrame(lat, lon);
  const rSite = sitePositionKm(lat, lon, groundHeightM, observerHeightM, moonRadiusM);
  const vecs = ephemData.data;

  const sunAz = new Float64Array(nSteps);
  const sunEl = new Float64Array(nSteps);
  const sunR = new Float64Array(nSteps);
  const earthAz = new Float64Array(nSteps);
  const earthEl = new Float64Array(nSteps);
  const earthR = new Float64Array(nSteps);

  fillBodyTrack({
    vecs,
    bodyIdx: 0,
    rSite,
    frame,
    radiusKm: sunRadiusKm,
    startIdx,
    nSteps,
    stride,
    azOut: sunAz,
    elOut: sunEl,
    rOut: sunR,
  });
  fillBodyTrack({
    vecs,
    bodyIdx: 1,
    rSite,
    frame,
    radiusKm: earthRadiusKm,
    startIdx,
    nSteps,
    stride,
    azOut: earthAz,
    elOut: earthEl,
    rOut: earthR,
  });

  return {
    sunAz,
    sunEl,
    sunR,
    earthAz,
    earthEl,
    earthR,
    nSteps,
  };
}
