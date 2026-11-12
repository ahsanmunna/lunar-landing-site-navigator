# Frontend Guide for Backend Developers

This document explains how the static web app in `web/` works without a build tool, framework, or backend API. Everything runs directly in the browser using native ES Modules (`<script type="module">`), Typed Arrays (similar to NumPy arrays), and HTML5 `<canvas>` 2D drawing.

---

## 1. Quick Mental Model (Python → Browser)

If you are used to Python (`numpy`, `matplotlib`, CLI scripts):

- **No bundler or server-side templates**: `web/index.html` loads `web/js/main.js` directly as an ES module. Browsers block `fetch()` over `file://` for security, which is why you serve `web/` over HTTP (`python -m http.server 8000`).
- **Binary buffers ≈ NumPy `.fromfile()`**: `fetch()` downloads `ephem.bin` and `horizons.bin` as raw `ArrayBuffer` byte blocks. We wrap them in `Float32Array` and `Int16Array` views (just like `np.fromfile(..., dtype="<f4")` and `dtype="<i2"`).
- **DOM ≈ `print()` / HTML output**: Instead of printing text, `main.js` and `compare.js` update HTML elements (`document.getElementById(...)`) by setting `.textContent` or building table rows.
- **Canvas 2D ≈ `matplotlib` figure**: `<canvas>` is a blank pixel surface. In `panorama.js` and `charts.js`, we clear the canvas and draw polygons, circles, and text onto `ctx = canvas.getContext("2d")`.
- **Event loop & non-blocking chunks**: JavaScript runs UI rendering and computation on one main thread. Computing a map metric (`Sun illumination`, `Earth visible (any part)`, or `Earth more than half visible`) for hundreds or thousands of grid sites over up to 90 days (`>= 3600 s` step) in a single loop would freeze button clicks, so `metrics.js` processes sites in timed chunks (`5 ms` budget) scheduled with `requestAnimationFrame` (falling back to `setTimeout(..., 0)` when RAF is unavailable) so the browser stays responsive, and `charts.js` batches site markers by colour bucket.

---

## 2. Data Flow: `manifest` + `ephem.bin` + `horizons.bin` → Screen

```text
web/data/manifest.json  ──┐
web/data/ephem.bin      ──┼─▶ data.js (loadDataPack, parseManifest, decode*Buffer)
web/data/horizons.bin   ──┘        │
                                   ▼
                        extractHorizonDeg(point, heightIdx)
                        getTimeWindow(startDate, days)
                                   │
                                   ▼
                        geometry.js (computeSunEarthAzEl)
                          • siteLocalFrame(lat, lon) -> up, east, north
                          • sitePositionKm(...)      -> MOON_ME site vector
                          • ephem vector - r_site    -> az, el, angular radius asin(R/d)
                                   │
                                   ▼
                        visibility.js (visibleFraction, summarize)
                          • interpHorizon(hor, az)   -> periodic 360° linear interp
                          • discVisibleFraction(t)   -> clipped circular cap area
                          • longestRun(...)          -> darkness & blackout hours
                                   │
          ┌────────────────────────┼─────────────────────────┐
          ▼                        ▼                         ▼
    metrics.js               panorama.js                 charts.js
    • 6 metric cards         • terrain silhouette        • SitePickerMap (PNG + Viridis dots)
    • lazy region grid       • Sun & Earth tracks        • Sun/Earth TimelineStrips
      illumination             • horizon-clipped discs
                                                             │
                                                             ▼
                                                        compare.js
                                                        • up to 3 pinned configs
                                                        • side-by-side table & bars
```

### Step-by-Step Lifecycle When the User Changes a Control

1. **Initial boot (`main.js` → `init()`)**:
   - `loadDataPack("data", onProgress)` fetches `manifest.json`, streams `ephem.bin` (`Float32Array` `[n_times][2][3]`), and streams `horizons.bin` (`Int16Array` `[n_points][n_heights][360]`).
   - All dimensions (`nPoints`, `nHeights`, `nAz`, `observer_heights_m`, `regions`) come dynamically from `manifest.json`.
   - `getDefaultRegionId(manifest)` selects Malapert Massif (`malapert-massif`) and its centre (`malapert-massif-c`) on initial load if present, or falls back to the first region.
2. **Control changes (`region`, `observer height`, `start date`, `duration`, `map metric`)**:
   - `syncDateBounds()` enforces `<input type="date">` `min`/`max` so the chosen duration never runs past the end of `ephem.bin`.
   - `evaluateCurrentSite()` calls `evaluateSite()` (`metrics.js`), which runs `computeSunEarthAzEl()` (`geometry.js`) and `summarize()` (`visibility.js`) for the currently selected point.
   - `startLazyRegionMap()` schedules chunked background computation for the active map metric (`sun_illumination`, `earth_any`, or `earth_mostly`) across every grid point in the current region so the site-picker map dots progressively fill with Viridis colours (cached in `mapValueCache` per `region + height + window + metric`) and enables `"Select brightest site"` / `"Select site with most Earth view"` once finished.
3. **Time slider / timeline scrubbing (`tIdx`)**:
   - Moving `<input id="time-slider">` or dragging on either timeline strip calls `setTimeIndex(idx)`.
   - `updateTimeUI()` updates the **"Now" card** (`now-sun-pct`, `now-earth-pct`, az/el/radius), redraws the moving cursor on both timeline strips (`charts.js`), and updates `panorama.js` (blitting its cached static background and drawing only the clipped Sun and Earth discs at `tIdx`).

---

## 3. Per-File Guide & Main Functions

### `web/index.html`
- **What it does**: Semantic single-page structure containing loading/error banners, control bar, site picker panel (with map metric selector, colourbar legend + window/step caption, and max-site picker buttons), horizon panorama panel + time slider + "Now" card, timeline strips, 6 summary metric cards, comparison section, `"How this works"` panel, and NASA credits footer.
- **Note**: Uses relative paths (`css/style.css`, `js/main.js`) so it works both via `python -m http.server 8000` inside `web/` and on GitHub Pages. Includes `<link rel="icon" href="data:,">` to prevent `/favicon.ico` 404 console errors.

### `web/tests.html`
- **What it does**: Browser verification runner. Loads `web/data/*` and `../tests/fixtures/reference.json`, executes JS unit checks (including default-region and max-site tie-breaking) and all 12 Python-vs-JS reference cases (plus map Earth metrics vs summary), and prints a PASS/FAIL table with max errors. Includes a manual file-picker fallback if served from inside `web/` (where `../tests/` is above the HTTP root).

### `web/css/style.css`
- **What it does**: Responsive layout (grid down to `360 px` mobile width, with `align-items: start` on `.workspace-grid` so the Site Picker panel does not stretch vertically beside the timeline strips), dark theme by default in `:root`, automatic light theme via `@media (prefers-color-scheme: light)`, colour-blind-safe domain variables (`--sun-color`, `--earth-color`, `--terrain-fill`), and focus outlines.

### `web/js/data.js`
- **What it does**: Fetches and validates `manifest.json`, decodes little-endian `ephem.bin` and `horizons.bin`, parses UTC dates, computes safe date-window indices, and caches `regions/<id>.png` images.
- **Main functions**:
  - `parseManifest(raw)`: Builds `regionsById`, `pointsById`, `pointsByRegion`, and dynamic counts (`nPoints`, `nHeights`, `nAz`).
  - `getDefaultRegionId(manifest)`: Selects `malapert-massif` if present in the manifest, otherwise `regions[0].id`.
  - `decodeEphemBuffer(buffer, manifest)` / `decodeHorizonsBuffer(buffer, manifest)`: Validates byte sizes and creates `Float32Array` / `Int16Array` views (little-endian safe).
  - `extractHorizonDeg(horizons, pointIndex, heightIndex)`: Returns a `Float64Array(nAz)` in degrees (`raw / 100`, handling `nodata = -32768`).
  - `getTimeRangeBounds(manifest, durationDays)` & `getTimeWindow(manifest, startStr, durationDays, stepSOverride)`: Maps UTC dates to `ephem.bin` slice indices.
  - `loadDataPack(basePath, onProgress)`: Streams data with progress reporting and raises `DataLoadError` with `"serve this folder over http, not file://"` on protocol or network failure.
  - `loadRegionImage(relPath, basePath)`: Loads and caches regional hillshade PNGs.

### `web/js/geometry.js`
- **What it does**: Exact JavaScript port of `lunar_engine/geometry.py` and `sun_earth_azel()` from `lunar_engine/ephemeris.py`.
- **Main functions**:
  - `forward(lat, lon, rMoonM)` / `inverse(x, y, rMoonM)`: South polar stereographic transforms.
  - `siteLocalFrame(lat, lon)`: Returns `{ up, east, north }` unit vectors in `MOON_ME`, including exact `lat = -90` pole handling.
  - `sitePositionKm(...)`: Computes observer 3D position vector in km.
  - `projectTopocentricInto(...)`: Reused zero-allocation helper computing `(az, el, angularRadiusDeg)` from a Moon-centred vector.
  - `computeSunEarthAzEl(...)`: Loops over the time window and fills `Float64Array` tracks (`sunAz`, `sunEl`, `sunR`, `earthAz`, `earthEl`, `earthR`).

### `web/js/visibility.js`
- **What it does**: Exact JavaScript port of `lunar_engine/visibility.py`.
- **Main functions**:
  - `discVisibleFraction(t)`: Exact clipped circular disc area formula for normalized offset `t = (el - hz) / r`.
  - `interpHorizon(hor, azDeg, azStepDeg)`: Periodic linear interpolation across `0°–360°`.
  - `stepDiscVisibleFraction(azDeg, elDeg, rDeg, hor, azStepDeg)`: Single-step visible fraction helper shared by `visibleFraction()`, `summarize()`, and the map metric evaluator.
  - `isDiscVisibleAny(fraction)` (`fraction > 0.0`) & `isDiscVisibleMostly(fraction)` (`fraction > 0.5`): Exact threshold predicates shared by `summarize()` and the Site Picker map Earth metrics.
  - `visibleFraction(azArray, elArray, rArray, hor, azStepDeg)`: Computes `Float64Array` visible fractions over time.
  - `longestRun(arr, predicate)`: Counts longest consecutive run (used for continuous darkness and Earth blackout).
  - `summarize(...)`: Computes all 6 period metrics plus `horizon_min`, `horizon_max`, `sv`, and `ev`.

### `web/js/metrics.js`
- **What it does**: Defines the 6 metric cards, the 3 Site Picker map metrics (`Sun illumination`, `Earth visible (any part)`, `Earth more than half visible`), the colour-blind-safe Viridis colour ramp, lazy region-wide map computation, and the max-value site picker.
- **Main exports & functions**:
  - `METRIC_DEFINITIONS`, `MAP_METRICS`, `EARTH_VISIBILITY_NOTE`, `DURATION_OPTIONS`.
  - `viridisColor(t)`: Maps `0..1` fraction to a perceptual colour-blind-safe RGB colour.
  - `evaluateSite(...)`: Runs `geometry.js` + `visibility.js` for the active site.
  - `computePointMapMetric(...)` (and `computePointIlluminationFraction` wrapper): Allocation-free single-point calculation using `stepDiscVisibleFraction`, `isDiscVisibleAny`, and `isDiscVisibleMostly`.
  - `computeRegionMapMetricLazy(...)` (and `computeRegionIlluminationLazy` wrapper): Computes the selected map metric asynchronously in `requestAnimationFrame`-paced chunks (`chunkBudgetMs = 5.0`), caching by `(region, height, start, steps, stride, metric)`.
  - `pickMaxMetricPoint(points, valueMap, region)` & `formatMaxSelectedNote({ nSites, metric, mapTimeWindow, observerHeightM, days })`: Finds the maximum computed site (breaking ties by closest distance to region centre) and formats the non-recommendation note from the active metric, the real window returned by `getColorMapTimeWindow`, observer height, and whether the full selected period exceeds the map window.

### `web/js/panorama.js`
- **What it does**: Canvas 2D horizon panorama renderer.
- **Main functions**:
  - `getCanvasPalette()`: Reads active dark/light colours from `style.css` CSS variables.
  - `createPanoramaRenderer(canvas)` → `.render({ hor, azel, sv, ev, tIdx, viewMode, azStepDeg })`:
    - Supports `"full"` (`0°–360°`) and 1:1 equal-angle `"zoom-sun"` / `"zoom-earth"` (`±10°`).
    - Caches the static background (sky, grid, faint dotted tracks, terrain silhouette) onto an offscreen canvas in `"full"` mode so scrubbing the slider is instantaneous.
    - Clips the solid Sun and Earth discs strictly to the sky polygon above the terrain horizon so partly hidden discs are physically cut off at the ridge.

### `web/js/charts.js`
- **What it does**: Renders the interactive Site Picker map and the Sun/Earth timeline strip charts.
- **Main functions**:
  - `createSitePicker({ canvas, tooltipEl, onSelectPoint })`: Draws `regions/<id>.png` using `region.extent`, overlays grid dots coloured by the active map metric, updates hover tooltips with the metric's short label, handles click/hover/keyboard arrow selection, and renders a km scale bar.
  - `createTimelineStrip({ canvas, colorVar, fallbackColor, showHalfLine, onScrub })`: Aggregates high-resolution time series into `[min, mean, max]` pixel columns (preventing short eclipses from disappearing on 365-day views), draws the time cursor, and handles pointer scrubbing.

### `web/js/compare.js`
- **What it does**: Manages up to 3 pinned `(site + height + date range)` configurations and renders the side-by-side table with inline bars (with no overall score or "best" ranking).
- **Main functions**:
  - `makeCompareKey(...)`, `createComparisonStore()`, `renderComparisonTable(...)`, `COMPARISON_TRADEOFF_NOTE`.

### `web/js/main.js`
- **What it does**: Application coordinator wiring DOM controls, default Malapert Massif selection, map metric segmented control and legend updates, `"Select brightest site"` / `"Select site with most Earth view"` actions, `ResizeObserver`, `prefers-color-scheme` theme updates, lazy map batches, playback timer, and comparison state.

---

## 4. Common Customization Recipes

### How to Change a Metric Label, Format, or Help Line
Open `web/js/metrics.js` and edit the `METRIC_DEFINITIONS` array:
- `label`: Card title and comparison table row heading.
- `help`: One-line plain-language description shown below the metric and in the comparison table.
- `format(v)` / `subFormat(v)`: How numbers are printed (e.g., decimal places or units).

Note that `tests/test_web.mjs` asserts the 6 exact metric labels, so update the test if you intentionally change a label.

### How to Change Static Text Notes or Headings
- **Earth visibility note**: Edit `EARTH_VISIBILITY_NOTE` in `web/js/metrics.js`.
- **Comparison tradeoff note**: Edit `COMPARISON_TRADEOFF_NOTE` in `web/js/compare.js`.
- **"How this works" steps, limitations, or GitHub footer link**: Edit HTML directly in `web/index.html`.

### How to Change Colours or Themes
All UI and Canvas colours live in one place: **`web/css/style.css`**.
1. Edit dark-mode defaults inside `:root { ... }` (lines 3–45).
2. Edit light-mode overrides inside `@media (prefers-color-scheme: light) { :root { ... } }`.
3. Key domain colour variables used by both CSS and Canvas 2D (`panorama.js` and `charts.js` read them live via `getComputedStyle`):
   - `--sun-color`, `--sun-glow`, `--sun-track`, `--sun-track-hidden`
   - `--earth-color`, `--earth-glow`, `--earth-track`, `--earth-track-hidden`
   - `--terrain-fill`, `--terrain-bottom`, `--terrain-stroke`
   - `--pano-sky-top`, `--pano-sky-bottom`, `--pano-grid`, `--pano-zero`, `--pano-cursor`
4. To change the site-picker dot colour scale, update `VIRIDIS_STOPS` in `web/js/metrics.js` and the matching `.colorbar-gradient` CSS gradient in `web/css/style.css`.
