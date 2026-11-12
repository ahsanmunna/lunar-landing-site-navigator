/**
 * Visibility fraction and summary metric calculations.
 * Exact JavaScript port of lunar_engine/visibility.py (disc_visible_fraction,
 * visible_fraction, longest_run, summarize).
 */

/**
 * Compute visible area fraction of a circular disc given normalized offset t in [-1, 1].
 * t = -1 -> 0.0 (completely below horizon)
 * t =  0 -> 0.5 (centre on horizon)
 * t = +1 -> 1.0 (completely above horizon)
 */
export function discVisibleFraction(t) {
  if (t <= -1.0) return 0.0;
  if (t >= 1.0) return 1.0;
  return (Math.acos(-t) + t * Math.sqrt(1.0 - t * t)) / Math.PI;
}

/**
 * Linearly interpolate terrain horizon elevation at azimuth azDeg (periodic over 360 deg).
 * Matches numpy.interp(az, np.arange(360), hor, period=360).
 */
export function interpHorizon(hor, azDeg, azStepDeg = 1.0) {
  const n = hor.length;
  const period = n * azStepDeg;
  let az = azDeg % period;
  if (az < 0.0) az += period;
  if (az >= period) az -= period;

  const fIdx = az / azStepDeg;
  const i0 = Math.floor(fIdx) % n;
  const i1 = (i0 + 1) % n;
  const frac = fIdx - Math.floor(fIdx);
  return hor[i0] + frac * (hor[i1] - hor[i0]);
}

/**
 * Threshold predicates shared by summarize() and site-picker map metrics.
 */
export function isDiscVisibleAny(fraction) {
  return fraction > 0.0;
}

export function isDiscVisibleMostly(fraction) {
  return fraction > 0.5;
}

/**
 * Compute single-step visible disc fraction for a celestial body against a horizon profile.
 */
export function stepDiscVisibleFraction(azDeg, elDeg, rDeg, hor, azStepDeg = 1.0) {
  const hz = interpHorizon(hor, azDeg, azStepDeg);
  return discVisibleFraction((elDeg - hz) / rDeg);
}

/**
 * Compute visible disc fraction time series for a celestial body against a horizon profile.
 */
export function visibleFraction(azArray, elArray, rArray, hor, azStepDeg = 1.0) {
  const n = azArray.length;
  const out = new Float64Array(n);
  const isScalarR = typeof rArray === "number";

  for (let i = 0; i < n; i++) {
    const r = isScalarR ? rArray : rArray[i];
    out[i] = stepDiscVisibleFraction(azArray[i], elArray[i], r, hor, azStepDeg);
  }
  return out;
}

/**
 * Return the length of the longest consecutive sequence of elements satisfying predicate.
 * Matches lunar_engine/visibility.py longest_run().
 */
export function longestRun(arr, predicate = (v) => Boolean(v)) {
  let best = 0;
  let cur = 0;
  for (let i = 0; i < arr.length; i++) {
    if (predicate(arr[i], i)) {
      cur += 1;
      if (cur > best) best = cur;
    } else {
      cur = 0;
    }
  }
  return best;
}

/**
 * Summarize illumination and Earth communication visibility metrics over a time window.
 * Matches lunar_engine/visibility.py summarize().
 */
export function summarize({
  hor,
  groundHeightM,
  sunAz,
  sunEl,
  sunR,
  earthAz,
  earthEl,
  earthR,
  lat,
  lon,
  start,
  days,
  observerHeightM,
  stepS,
  azStepDeg = 1.0,
}) {
  const sv = visibleFraction(sunAz, sunEl, sunR, hor, azStepDeg);
  const ev = visibleFraction(earthAz, earthEl, earthR, hor, azStepDeg);
  const n = sv.length;

  let svSum = 0.0;
  let sunAnyCount = 0;
  let earthAnyCount = 0;
  let earthMostlyCount = 0;
  let sunLongestDarkSteps = 0;
  let sunCurDark = 0;
  let earthLongestBlackoutSteps = 0;
  let earthCurBlackout = 0;

  for (let i = 0; i < n; i++) {
    const s = sv[i];
    const e = ev[i];
    svSum += s;
    if (isDiscVisibleAny(s)) sunAnyCount += 1;
    if (s === 0.0) {
      sunCurDark += 1;
      if (sunCurDark > sunLongestDarkSteps) sunLongestDarkSteps = sunCurDark;
    } else {
      sunCurDark = 0;
    }
    if (isDiscVisibleAny(e)) earthAnyCount += 1;
    if (isDiscVisibleMostly(e)) earthMostlyCount += 1;
    if (e === 0.0) {
      earthCurBlackout += 1;
      if (earthCurBlackout > earthLongestBlackoutSteps) earthLongestBlackoutSteps = earthCurBlackout;
    } else {
      earthCurBlackout = 0;
    }
  }

  let horMin = Infinity;
  let horMax = -Infinity;
  for (let i = 0; i < hor.length; i++) {
    const h = hor[i];
    if (h < horMin) horMin = h;
    if (h > horMax) horMax = h;
  }

  const invN = n > 0 ? 1.0 / n : 0.0;

  return {
    illumination_avg_fraction: svSum * invN,
    sun_any_pct: sunAnyCount * invN * 100.0,
    sun_longest_dark_h: (sunLongestDarkSteps * stepS) / 3600.0,
    earth_any_pct: earthAnyCount * invN * 100.0,
    earth_mostly_pct: earthMostlyCount * invN * 100.0,
    earth_longest_blackout_h: (earthLongestBlackoutSteps * stepS) / 3600.0,
    horizon_min: horMin,
    horizon_max: horMax,
    ground_height_m: groundHeightM,
    lat,
    lon,
    start: String(start),
    days,
    observer_height_m: observerHeightM,
    step_s: stepS,
    sv,
    ev,
  };
}
