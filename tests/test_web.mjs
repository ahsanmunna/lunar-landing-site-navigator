/**
 * Node test runner for the static web app ES modules (requires Node >= 18).
 * Run: node tests/test_web.mjs
 */

import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  parseManifest,
  decodeEphemBuffer,
  decodeHorizonsBuffer,
  extractHorizonDeg,
  getTimeRangeBounds,
  getTimeWindow,
} from "../web/js/data.js";
import {
  forward,
  inverse,
  siteLocalFrame,
  angularRadiusDeg,
  computeSunEarthAzEl,
} from "../web/js/geometry.js";
import {
  discVisibleFraction,
  interpHorizon,
  longestRun,
  summarize,
} from "../web/js/visibility.js";
import {
  METRIC_DEFINITIONS,
  EARTH_VISIBILITY_NOTE,
  computePointIlluminationFraction,
  getColorMapTimeWindow,
  computeRegionIlluminationLazy,
} from "../web/js/metrics.js";
import {
  COMPARISON_TRADEOFF_NOTE,
  createComparisonStore,
  makeCompareKey,
} from "../web/js/compare.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const WEB_DATA = path.join(ROOT, "web", "data");
const FIXTURES_PATH = path.join(ROOT, "tests", "fixtures", "reference.json");

function circularDegDiff(a, b) {
  return Math.abs(((a - b + 540.0) % 360.0) - 180.0);
}

function toArrayBuffer(buf) {
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

async function main() {
  const rawManifest = JSON.parse(await fs.readFile(path.join(WEB_DATA, "manifest.json"), "utf8"));
  const manifest = parseManifest(rawManifest);

  const ephemBuf = toArrayBuffer(
    await fs.readFile(path.join(WEB_DATA, manifest.ephemeris.file)),
  );
  const horizonsBuf = toArrayBuffer(
    await fs.readFile(path.join(WEB_DATA, manifest.horizons.file)),
  );
  const ephem = decodeEphemBuffer(ephemBuf, manifest);
  const horizons = decodeHorizonsBuffer(horizonsBuf, manifest);
  const fixtures = JSON.parse(await fs.readFile(FIXTURES_PATH, "utf8"));

  let failures = 0;
  function check(name, fn) {
    try {
      const detail = fn();
      console.log(`PASS  ${name}${detail ? ` — ${detail}` : ""}`);
    } catch (err) {
      failures += 1;
      console.error(`FAIL  ${name} — ${err.message}`);
    }
  }

  // Unit checks
  check("visible_fraction at t = -1, 0, 1", () => {
    assert.ok(Math.abs(discVisibleFraction(-1) - 0.0) < 1e-12);
    assert.ok(Math.abs(discVisibleFraction(0) - 0.5) < 1e-12);
    assert.ok(Math.abs(discVisibleFraction(1) - 1.0) < 1e-12);
    assert.equal(discVisibleFraction(-5), 0.0);
    assert.equal(discVisibleFraction(5), 1.0);
  });

  check("geometry forward/inverse round-trip within 1e-6 deg", () => {
    for (const [lat, lon] of [[-86, 2], [-87.3, 77], [-89.999999, -120]]) {
      const { x, y } = forward(lat, lon, manifest.constants.moon_radius_m);
      const rec = inverse(x, y, manifest.constants.moon_radius_m);
      assert.ok(Math.abs(rec.lat - lat) < 1e-6);
      assert.ok(circularDegDiff(rec.lon, lon) < 1e-6);
    }
  });

  check("south pole lat = -90 singularity handling", () => {
    const f = siteLocalFrame(-90.0, 0.0);
    assert.deepEqual(f.up, [0, 0, -1]);
    assert.deepEqual(f.east, [0, 1, 0]);
    assert.deepEqual(f.north, [1, 0, 0]);
    assert.deepEqual(inverse(0, 0), { lat: -90.0, lon: 0.0 });
  });

  check("periodic horizon interpolation across 359->0 seam", () => {
    const h = new Float64Array(360);
    h[359] = 2.0;
    h[0] = 4.0;
    assert.ok(Math.abs(interpHorizon(h, 359.5, 1.0) - 3.0) < 1e-12);
    assert.ok(Math.abs(interpHorizon(h, -0.5, 1.0) - 3.0) < 1e-12);
  });

  check("longestRun and angularRadiusDeg", () => {
    assert.equal(longestRun([true, false, true, true, true, false], Boolean), 3);
    const r = angularRadiusDeg(6371, 384400);
    assert.ok(Math.abs(r - (Math.asin(6371 / 384400) * 180) / Math.PI) < 1e-12);
  });

  check("time bounds for 30d and 365d inside ephemeris range", () => {
    const b30 = getTimeRangeBounds(manifest, 30);
    const b365 = getTimeRangeBounds(manifest, 365);
    assert.equal(b30.minDateStr, "2027-01-01");
    assert.equal(b30.maxDateStr, "2028-12-02");
    assert.equal(b365.maxDateStr, "2028-01-02");
  });

  check("required UI labels, Earth note, and comparison rules", () => {
    const labels = METRIC_DEFINITIONS.map((d) => d.label);
    assert.deepEqual(labels, [
      "Illumination availability",
      "Sun visible (any part)",
      "Longest continuous darkness",
      "Geometric Earth visibility (any part of the disc)",
      "Earth more than half visible",
      "Longest Earth-visibility blackout",
    ]);
    assert.equal(
      EARTH_VISIBILITY_NOTE,
      "Earth visibility here is geometric (line of sight to any part of Earth's disc), not a radio link budget.",
    );
    assert.equal(
      COMPARISON_TRADEOFF_NOTE,
      "Which site is better depends on mission needs: power, communications and terrain safety trade off.",
    );

    const store = createComparisonStore();
    for (let i = 0; i < 3; i++) {
      const key = makeCompareKey({ pointId: `p${i}`, observerHeightM: 1, startDate: "2027-01-01", days: 30 });
      assert.equal(store.add({ key }).ok, true);
    }
    assert.equal(store.add({ key: "p0|1|2027-01-01|30" }).reason, "already-added");
    assert.equal(store.add({ key: "p3|1|2027-01-01|30" }).reason, "full");
    store.remove("p1|1|2027-01-01|30");
    assert.equal(store.getEntries().length, 2);
  });

  check("colour-map time window (>= 3600 s step, <= 90 days)", () => {
    const w30 = getColorMapTimeWindow(manifest, "2027-01-01", 30);
    assert.ok(w30.stepS >= 3600);
    assert.equal((w30.nSteps * w30.stepS) / 86400, 30);

    const w365 = getColorMapTimeWindow(manifest, "2027-01-01", 365);
    assert.ok(w365.stepS >= 3600);
    assert.equal((w365.nSteps * w365.stepS) / 86400, 90);
    assert.equal(w365.stride, Math.round(w365.stepS / manifest.ephemeris.step_s));
  });

  // Async check for chunked lazy colour map, progress callbacks, and cancellation
  {
    const firstReg = manifest.regions[0];
    const regPts = manifest.pointsByRegion.get(firstReg.id);
    const mapTw = getColorMapTimeWindow(manifest, "2027-01-01", 365);
    const cache = new Map();
    let batchCount = 0;
    let lastDone = 0;
    const completed = await new Promise((resolve) => {
      computeRegionIlluminationLazy({
        regionId: firstReg.id,
        regionPoints: regPts,
        heightIdx: 0,
        observerHeightM: manifest.observer_heights_m[0],
        timeWindow: mapTw,
        manifest,
        ephem,
        horizons,
        cache,
        maxBatchSize: 48,
        onBatch: (_m, done, total) => {
          batchCount += 1;
          assert.ok(done > lastDone && done < total);
          lastDone = done;
        },
        onDone: (fullMap) => resolve(fullMap),
      });
    });
    assert.ok(batchCount >= 1, "Expected chunked progress callbacks");
    assert.equal(completed.size, regPts.length);

    // Cancellation prevents further batches or completion
    const cancelCache = new Map();
    let afterCancelCalls = 0;
    const cancelFn = computeRegionIlluminationLazy({
      regionId: firstReg.id,
      regionPoints: regPts,
      heightIdx: 0,
      observerHeightM: manifest.observer_heights_m[0],
      timeWindow: mapTw,
      manifest,
      ephem,
      horizons,
      cache: cancelCache,
      maxBatchSize: 10,
      onBatch: () => {
        afterCancelCalls += 1;
      },
      onDone: () => {
        afterCancelCalls += 1;
      },
    });
    cancelFn();
    await new Promise((r) => setTimeout(r, 40));
    assert.equal(afterCancelCalls, 0);
    assert.equal(cancelCache.size, 0);
    console.log(`PASS  lazy colour map chunking (${batchCount} batches), progress, and cancel`);
  }

  // Reference fixtures (12 cases)
  console.log("\n--- Reference Fixture Verification (12 cases) ---");
  let worstIllum = 0;
  let worstPct = 0;
  let worstHours = 0;
  let worstAz = 0;
  let worstEl = 0;
  let worstVis = 0;

  for (const c of fixtures) {
    check(`${c.point_id} @ ${c.observer_height_m}m (${c.days}d)`, () => {
      assert.equal(c.horizon_source, "packed int16");
      const pt = manifest.pointsById.get(c.point_id);
      assert.ok(pt, `Point ${c.point_id} missing from manifest`);
      const hIdx = manifest.observer_heights_m.findIndex(
        (h) => Math.abs(h - c.observer_height_m) < 1e-6,
      );
      assert.ok(hIdx >= 0, `Height ${c.observer_height_m} missing from manifest`);

      const hor = extractHorizonDeg(horizons, pt.index, hIdx);
      const tw = getTimeWindow(manifest, c.start, c.days, c.step_s);
      const azel = computeSunEarthAzEl({
        lat: pt.lat,
        lon: pt.lon,
        groundHeightM: pt.ground_height_m,
        observerHeightM: c.observer_height_m,
        startIdx: tw.startIdx,
        nSteps: tw.nSteps,
        stride: tw.stride,
        ephemData: ephem,
        constants: manifest.constants,
      });

      const summary = summarize({
        hor,
        groundHeightM: pt.ground_height_m,
        sunAz: azel.sunAz,
        sunEl: azel.sunEl,
        sunR: azel.sunR,
        earthAz: azel.earthAz,
        earthEl: azel.earthEl,
        earthR: azel.earthR,
        lat: pt.lat,
        lon: pt.lon,
        start: c.start,
        days: c.days,
        observerHeightM: c.observer_height_m,
        stepS: c.step_s,
        azStepDeg: manifest.azStepDeg,
      });

      // Verify zero-GC lazy point illumination helper matches summarize() identically
      const lazyIllum = computePointIlluminationFraction({
        point: pt,
        heightIdx: hIdx,
        observerHeightM: c.observer_height_m,
        timeWindow: tw,
        manifest,
        ephem,
        horizons,
      });
      assert.ok(
        Math.abs(lazyIllum - summary.illumination_avg_fraction) < 1e-12,
        `lazyIllum mismatch: ${lazyIllum} vs ${summary.illumination_avg_fraction}`,
      );

      const ref = c.summary;
      const dIllum = Math.abs(summary.illumination_avg_fraction - ref.illumination_avg_fraction);
      const dPct = Math.max(
        Math.abs(summary.sun_any_pct - ref.sun_any_pct),
        Math.abs(summary.earth_any_pct - ref.earth_any_pct),
        Math.abs(summary.earth_mostly_pct - ref.earth_mostly_pct),
      );
      const stepHours = c.step_s / 3600.0;
      const dHours = Math.max(
        Math.abs(summary.sun_longest_dark_h - ref.sun_longest_dark_h),
        Math.abs(summary.earth_longest_blackout_h - ref.earth_longest_blackout_h),
      );

      let maxAzErr = 0;
      let maxElErr = 0;
      let maxVisErr = 0;
      for (const s of c.sample_times) {
        const i = s.index;
        maxAzErr = Math.max(
          maxAzErr,
          circularDegDiff(azel.sunAz[i], s.sun_az_deg),
          circularDegDiff(azel.earthAz[i], s.earth_az_deg),
        );
        maxElErr = Math.max(
          maxElErr,
          Math.abs(azel.sunEl[i] - s.sun_el_deg),
          Math.abs(azel.earthEl[i] - s.earth_el_deg),
        );
        maxVisErr = Math.max(
          maxVisErr,
          Math.abs(summary.sv[i] - s.sun_visible_fraction),
          Math.abs(summary.ev[i] - s.earth_visible_fraction),
        );
      }

      worstIllum = Math.max(worstIllum, dIllum);
      worstPct = Math.max(worstPct, dPct);
      worstHours = Math.max(worstHours, dHours);
      worstAz = Math.max(worstAz, maxAzErr);
      worstEl = Math.max(worstEl, maxElErr);
      worstVis = Math.max(worstVis, maxVisErr);

      assert.ok(dIllum <= 0.005, `dIllum=${dIllum} > 0.005`);
      assert.ok(dPct <= 0.5, `dPct=${dPct} > 0.5`);
      assert.ok(dHours <= stepHours + 1e-9, `dHours=${dHours} > ${stepHours}`);
      assert.ok(maxAzErr <= 0.01, `maxAzErr=${maxAzErr} > 0.01`);
      assert.ok(maxElErr <= 0.01, `maxElErr=${maxElErr} > 0.01`);
      assert.ok(maxVisErr <= 0.002, `maxVisErr=${maxVisErr} > 0.002`);

      return `Δillum=${dIllum.toFixed(6)}, Δpct=${dPct.toFixed(4)}, Δh=${dHours.toFixed(2)}, Δaz=${maxAzErr.toFixed(5)}°, Δel=${maxElErr.toFixed(5)}°, Δvis=${maxVisErr.toFixed(6)}`;
    });
  }

  console.log(
    `\nMax errors across all 12 cases: Δillum=${worstIllum.toFixed(6)}, Δpct=${worstPct.toFixed(4)}, Δh=${worstHours.toFixed(2)}h, Δaz=${worstAz.toFixed(5)}°, Δel=${worstEl.toFixed(5)}°, Δvis=${worstVis.toFixed(6)}`,
  );

  if (failures > 0) {
    console.error(`\nFAILED: ${failures} check(s) failed at strict ±0.002 sample visible-fraction tolerance.`);
    process.exit(1);
  }
  console.log("\nALL WEB JS TESTS PASSED.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
