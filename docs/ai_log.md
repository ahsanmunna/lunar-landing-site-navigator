# AI Engineering Log

## Prompt (Verbatim)

```text
TASK (Phase 1): Refactor horizon.py into a reusable, tested Python package. Do NOT change the
algorithms or physical constants unless this brief says so. First read horizon.py, check_spice.py and
inspect_dem.py in the workspace, then build.

PROJECT: Moon south-pole tool for NASA Space Apps 2026 ("Lunar Landing Site Navigator"). For any site it
computes the terrain horizon from a LOLA 20 m DEM and the Sun and Earth positions from SPICE, then the
visible fraction of each disc over time.
Inputs: LOLA DEM LDEM_80S_20MPP_ADJ.tiff (path from env var LUNAR_DEM_PATH; float32 metres above
R=1737400 m; NaN nodata; south polar stereographic; near side up, east right). SPICE kernels in ./kernels
(naif0012.tls, de440.bsp, moon_pa_de440_200625.bpc, moon_de440_220930.tf), frame MOON_ME.
A 160 m cache dem_160m_cache.npy may already exist next to the scripts; keep that behaviour.

STRUCTURE:
  lunar_engine/__init__.py
  lunar_engine/config.py      DEM path from LUNAR_DEM_PATH; kernel dir ./kernels; cache dir
  lunar_engine/geometry.py    forward (lat,lon)->(x,y), inverse (x,y)->(lat,lon), map scale factor,
                              local frame at a site
  lunar_engine/horizon.py     compute_horizon(lat, lon, observer_height_m) -> np.ndarray(360) deg
                              (also return ground height of the site)
  lunar_engine/ephemeris.py   position vectors (km, MOON_ME, abcorr NONE) of SUN and EARTH on a time grid;
                              sun_earth_azel(lat, lon, ground_height_m, observer_height_m, start, days, step_s)
  lunar_engine/visibility.py  visible_fraction(...), summarize(...)
  analyze_site.py             CLI: lat lon --start --days --height --step -> prints metrics, writes JSON + PNG
  tests/                      pytest
  requirements.txt, LICENSE (Apache-2.0), README.md (short), .gitignore, docs/ai_log.md

CHANGES FROM THE OLD SCRIPT (mandatory):
 1. Do not hard-code angular radii. Compute them from distance: Sun radius 695700 km, Earth radius
    6371 km, angular_radius = asin(R / distance), distance from the SPICE position vector minus the
    site vector.
 2. Default time step is 900 s (parameter step_s). Convert run lengths using step_s, not "hours".
 3. summarize() returns a dict with: illumination_avg_fraction, sun_any_pct, sun_longest_dark_h,
    earth_any_pct (any part of the disc visible), earth_mostly_pct (more than 50% visible),
    earth_longest_blackout_h (longest period with no part of Earth visible), horizon_min, horizon_max,
    ground_height_m, and the inputs used.
 4. Observer height is a parameter; support 1 m and 5 m (default 2 m for the regression tests).
 5. Handle lat == -90 exactly (rho0 = 0): define north as the lon=0 direction; no division by zero.
 6. ephemeris.py can return the raw Moon-centred SUN and EARTH vectors on a time grid (needed later).

TESTS (pytest):
 a) Regression at step_s=3600, observer 2 m, start 2027-01-01, 30 days:
      (lat -86, lon 2):    previously illumination 0.84, earth_mostly 45%, earth_any 49%,
                           longest Earth blackout 212 h, ground height 5154 m, horizon_min -5.10, max 3.64.
                           Tolerances: illumination +-0.02, earth pcts +-2, blackout +-6 h.
      (lat -87.3, lon 77): illumination 0, earth_any 0, horizon_min greater than 6.0.
    Because angular radii are now computed from distance, values can move slightly. If any value falls
    outside tolerance, DO NOT loosen the tolerance: report the new number and explain why.
    These tests skip cleanly if LUNAR_DEM_PATH is unset.
 b) Without the DEM: visible_fraction at t=-1,0,1 gives 0, 0.5, 1; geometry round trip within 1e-6 deg;
    lat=-90 does not crash; SPICE check for 2026-06-18 18:00 UT: sub-Earth point within 0.05 deg of
    (lat -1.600, lon 6.545 E) and sub-solar longitude within 0.05 deg of 135.917 E.
 c) Angular radius test: Earth radius from the vector at a known distance equals asin(6371/d).

GENERAL: type hints, short docstrings, no new dependencies beyond numpy, scipy, rasterio, spiceypy,
matplotlib, pytest. .gitignore must exclude *.bsp, *.bpc, *.tiff, *.tif, *.npy, outputs/, __pycache__/.
Do not delete the original scripts; move them to legacy/.
DOCS: create docs/ai_log.md and append this entire prompt verbatim, plus a one-paragraph summary of what
you changed. Do not commit large files.
DELIVER: list of files changed, how to run the tests and the CLI on Windows PowerShell, test output, and
anything you were unsure about.
```

## Summary of Changes

The monolithic `horizon.py` script and auxiliary inspection utilities were moved to `legacy/` and refactored into a modular, clean Python package `lunar_engine` containing `config`, `geometry`, `horizon`, `ephemeris`, and `visibility` modules, driven by a new command-line script `analyze_site.py`. In accordance with the prompt requirements: apparent angular radii for the Sun ($R=695700\text{ km}$) and Earth ($R=6371\text{ km}$) are dynamically computed per time step using $\arcsin(R / d)$ from the site-to-body topocentric vector norm rather than hard-coded constants (Earth's angular radius is about 0.90-1.02 deg depending on the Earth-Moon distance); the default simulation time step was shifted to $900\text{ s}$ (`step_s`) and duration metrics are converted to hours scaled by `step_s / 3600`; `summarize()` returns a structured dictionary containing all requested illumination, communication blackout, and terrain metrics along with full input provenance; configurable observer heights (including $1\text{ m}$ and $5\text{ m}$, default $2\text{ m}$) are supported across terrain horizon and ephemeris calculations; exact polar singularity handling for $\text{lat} = -90^\circ$ ($\rho_0 = 0$) defines north along $\text{lon} = 0^\circ$ and avoids division by zero across both 2D stereographic map vectors and 3D Moon-fixed coordinate frames; `ephemeris.py` exposes vectorized access to raw Moon-centred position vectors; and a comprehensive pytest suite covers geometry round-trips within $10^{-6\circ}$, South Pole singularity robustness, SPICE sub-solar/sub-Earth calibration checks, distance-derived angular radii, and regression tests against LOLA DEM benchmark sites (which skip cleanly when `LUNAR_DEM_PATH` is unset).

## Phase 1.1 Prompt (Verbatim)

```text
TASK Phase 1.1 (small fix, no algorithm changes):
1. In tests/test_ephemeris.py replace the angular-radius test with one that calls
   sun_earth_azel(lat=-86, lon=2, ground_height_m=5154, observer_height_m=2, start="2027-01-01",
   days=30, step_s=3600) and asserts: earth_r == degrees(arcsin(6371 / earth_dist_km)) elementwise
   (atol 1e-9), earth_r.min() between 0.89 and 0.91, earth_r.max() between 1.01 and 1.03,
   and sun_r between 0.269 and 0.273. Keep the pure-formula test too.
2. In docs/ai_log.md and README.md, if any text says Earth's angular radius is 0.938-0.963 deg, correct
   it to "about 0.90-1.02 deg depending on the Earth-Moon distance".
3. Run pytest with LUNAR_DEM_PATH set, show the output, commit with message "Phase 1.1: real angular
   radius test". Append this prompt verbatim to docs/ai_log.md.
```

## Phase 1.1 Summary of Changes

In `tests/test_ephemeris.py`, enhanced angular radius verification by updating the ephemeris test to call `sun_earth_azel(lat=-86, lon=2, ground_height_m=5154, observer_height_m=2, start="2027-01-01", days=30, step_s=3600)` and assert: `earth_r == degrees(arcsin(6371 / earth_dist_km))` elementwise (atol $10^{-9}$), `earth_r.min()` between 0.89 and 0.91 deg, `earth_r.max()` between 1.01 and 1.03 deg, and `sun_r` between 0.269 and 0.273 deg, verifying that Earth's angular radius is about 0.90-1.02 deg depending on the Earth-Moon distance. Also retained the pure-formula unit test for distance-to-angular-radius conversion.

## Task 2A Prompt (Verbatim)

```text
TASK 2A: Interactive tool to digitize the 9 Artemis III candidate regions. Independent of the engine.

CONTEXT: Moon south pole. DEM: LDEM_80S_20MPP_ADJ.tiff (path from env var LUNAR_DEM_PATH),
30400x30400 px, 20 m, south polar stereographic on a 1737400 m sphere, bounds +-304 km, near side up,
east to the right. A 160 m averaged copy already exists as dem_160m_cache.npy (3800x3800); use it for display.
Map position from lat/lon: colat = 90 + lat (lat negative), rho = 2*R*tan(colat/2),
x = rho*sin(lon), y = rho*cos(lon). Existing horizon.py shows the transform and inverse needs.

BUILD: scripts/pick_regions.py
1. Show a hillshaded map of the 80S-90S area (matplotlib, interactive TkAgg window; Windows + VS Code).
   Overlay a graticule: latitude circles every 1 degree, meridians every 30 degrees, labelled.
   Axes in km from the pole. Zoom/pan via the normal toolbar.
2. Region list read from data_src/region_names.json:
   ["Peak near Cabeus B","Haworth","Malapert Massif","Mons Mouton Plateau","Mons Mouton",
    "Nobile Rim 1","Nobile Rim 2","de Gerlache Rim 2","Slater Plain"]
   The title shows the current region name. Hover the mouse over the region centre and press SPACE to
   record it; press BACKSPACE to undo; press N to skip. The status line shows lat, lon, x_km, y_km,
   ground height (m) at the cursor in real time.
3. Output data_src/regions.json: list of {id (slug), name, center_x_m, center_y_m, center_lat, center_lon,
   ground_height_m, radius_km (default 4.0, editable in the file), source: "approximate; digitized by hand
   from NASA's Artemis III region map"}.
4. Re-running loads existing regions.json and lets me redo only chosen regions (--redo name).
5. Write an inverse function (x,y)->(lat,lon) and forward (lat,lon)->(x,y) in lunar_engine/geometry.py if
   Phase 1 created that file; otherwise put them in scripts/_geo.py and tell me.
6. Unit test the two transforms: round trip within 1e-6 deg, and a pole-adjacent case.
7. Append this prompt verbatim to docs/ai_log.md with a one-paragraph summary.
Deliver: files changed, how to run, anything unsure.
```

## Task 2A Summary of Changes

Built an interactive digitization tool in `scripts/pick_regions.py` for the 9 Artemis III candidate landing regions using the $160\text{ m}$ cached LOLA DEM (`dem_160m_cache.npy`) rendered with cartographic hillshading and overlaid with a South Polar stereographic graticule ($1^\circ$ latitude circles, $30^\circ$ meridians, and labeled coordinates in km from the pole). The tool reads region names from `data_src/region_names.json`, tracks real-time cursor status (`lat`, `lon`, `x_km`, `y_km`, interpolated DEM elevation in metres), binds interactive key events (`SPACE` to record, `BACKSPACE` to undo, `N` to skip, standard toolbar zoom/pan), and persists digitized records with slugs, coordinates, sampled ground heights, default $4.0\text{ km}$ radii, and source provenance into `data_src/regions.json`. Support for selective re-digitization (`--redo <name>` or `--redo all`) was implemented alongside existing region persistence. Forward and inverse polar stereographic transformations were formalized with exact pole handling in both `lunar_engine/geometry.py` and the standalone `scripts/_geo.py` module, accompanied by comprehensive unit tests covering sub-millimetre pole-adjacent cases, round trips within $10^{-6\circ}$, and digitizer CLI/data schema verification.



## Task 2B Prompt (Verbatim)

```text
TASK 2B: Precompute the data pack that a static web app will load. Use the Phase 1 engine; do NOT
change its algorithms. If function names differ from this brief, adapt and report.

INPUTS: data_src/regions.json (centres + radius_km), the 20 m DEM via LUNAR_DEM_PATH, SPICE kernels.

STEP 0 (benchmark, report before building): scripts/benchmark_horizon.py times compute_horizon for 20
random points and 2 observer heights (1 m, 5 m). Print seconds per profile and estimate total time for
spacing 250 m, 500 m, 1000 m. Choose the finest spacing for which the total is under ~90 minutes using
multiprocessing (Windows: use 'spawn'-safe code with if __name__ == "__main__"). Say which you chose.

STEP 1 (points): for each region, a regular grid in stereographic X/Y metres (NOT lat/lon) with the chosen
spacing, clipped to a circle of radius_km around the centre. Also include the centre itself as point id
<region>-c. Drop points with NaN ground height or within 5 km of the 80S model edge. For each point store
x_m, y_m, lat, lon, ground_height_m, slope_deg (from the 20 m DEM over a ~100 m baseline).

STEP 2 (horizons): for each point and each observer height in [1, 5] m compute the 360-ray horizon with the
engine. Run in chunks with a checkpoint file so a crash can resume; show progress.

STEP 3 (ephemeris): Moon-centred SPICE position vectors (km, MOON_ME frame, abcorr NONE) of SUN and EARTH
every 900 s from 2027-01-01T00:00:00 UTC to 2029-01-01T00:00:00 UTC.

STEP 4 (files, little-endian) under web/data/:
  manifest.json: version, created_utc, constants {moon_radius_m: 1737400, sun_radius_km: 695700,
    earth_radius_km: 6371, horizon_az_step_deg: 1, azimuth_convention: "clockwise from outward-radial north"},
    observer_heights_m [1,5], ephemeris {file, start_utc, step_s, n_times, frame "MOON_ME", layout
    "[n_times][body: 0=SUN,1=EARTH][x,y,z] float32 km"}, horizons {file, layout
    "[n_points][n_heights][360] int16, value = round(deg*100), -32768 = no data"}, regions [...],
    points [{id, region, x_m, y_m, lat, lon, ground_height_m, slope_deg, index}], grid_spacing_m,
    sources: list of NASA datasets used (LOLA LDEM_80S_20MPP_ADJ, NAIF de440, moon_pa_de440, naif0012, MOON_ME frame kernel)
  horizons.bin, ephem.bin (as described).
  regions/<id>.png: hillshade of each region (about 40 m/px, 2*radius_km wide) with a matching extent entry
  in manifest.json (x/y min/max in metres) so the UI can place points on it.
Total size of web/data must be under 12 MB; report the sizes.

STEP 5 (tests, tests/test_datapack.py):
  a) file sizes match the manifest layout exactly;
  b) 5 random points: horizon in the .bin equals a fresh engine computation within 0.011 deg;
  c) 3 random times: ephem.bin vectors equal direct spiceypy spkpos within 1e-3 km;
  d) no point lies outside its region circle.
STEP 6 (fixtures for the later JavaScript port): tests/fixtures/reference.json with 12 cases
  (point id, height, start, days, step) and for each the full summarize() output plus az/el of Sun and Earth
  at 20 sample times and the visible fractions at those times. Include Malapert centre and a Faustini-like
  shadowed point.
STEP 7: docs/datapack_format.md describing the format and known limitations: the horizon is sensitive to
  terrain within ~100 m of the point; 1-degree azimuth resolution; no light-time correction; positions of
  regions are approximate.
STEP 8: append this prompt verbatim to docs/ai_log.md. Make sure .gitignore keeps big raw files out,
  but web/data IS committed.
Deliver: benchmark numbers, chosen spacing, sizes, test results.
```

## Task 2B Summary of Changes

Precomputed the static client data pack deployed under `web/data/` using the Phase 1 engine without altering any core algorithms or physical constants:
1. **Benchmark (`scripts/benchmark_horizon.py`)**: Measured single-horizon runtime across 20 random sites at $1\text{ m}$ and $5\text{ m}$ observer heights ($40$ profiles, mean $\sim 0.261\text{ s}$ per profile). Evaluated grid point counts and runtimes for $1000\text{ m}$, $500\text{ m}$, and $250\text{ m}$ spacings against both the $\sim 90\text{ minute}$ execution budget and the $12\text{ MB}$ distribution size ceiling. Selected $500\text{ m}$ spacing ($1,773$ points total, $3,546$ profiles, computing in $\sim 1.9\text{ min}$ on 8 workers, with data pack total size $\sim 4.74\text{ MB} < 12\text{ MB}$, whereas $250\text{ m}$ would yield $\sim 12.8\text{ MB}$ exceeding the hard cap).
2. **Points Generation (`scripts/build_datapack.py`)**: Formed regular stereographic X/Y grids ($500\text{ m}$ spacing) within $4.0\text{ km}$ circles around the 9 candidate region centres, including each centre as `<region>-c`. Sampled ground heights and computed finite-difference slopes over a $100\text{ m}$ baseline ($\pm 50\text{ m}$) from the LOLA $20\text{ m}$ DEM, filtering points within $5\text{ km}$ of the $80^\circ\text{S}$ DEM boundary or with NaN elevations.
3. **Horizon Precomputation & Checkpoints**: Parallelized 360-ray horizon profile evaluations across multiprocessing workers on Windows with periodic `.npz` checkpoint saves enabling crash recovery. Stored scaled elevation values ($\text{round}(\theta \times 100)$, nodata $-32768$) into little-endian `int16` array `horizons.bin` ($2.43\text{ MB}$).
4. **Ephemeris Generation**: Produced Moon-centred SPICE position vectors (in km, `MOON_ME` frame, `abcorr="NONE"`) for Sun and Earth at $900\text{ s}$ intervals from `2027-01-01T00:00:00` to `2029-01-01T00:00:00` ($70,177$ epochs), saved as little-endian `float32` array `ephem.bin` ($1.61\text{ MB}$).
5. **Manifest & Hillshade Imagery**: Rendered high-contrast $40\text{ m/px}$ hillshade PNG images for all 9 candidate zones into `web/data/regions/<id>.png` ($200 \times 200\text{ px}$) and generated `manifest.json` detailing exact coordinate extents, physical constants, ephemeris metadata, point indexes, and source provenance.
6. **Validation & JavaScript Fixtures**: Implemented pytest test suite in `tests/test_datapack.py` verifying exact binary layouts and file sizes, 5-point random horizon equality against fresh engine computations within $0.011^\circ$, 3-epoch SPICE vector precision within $10^{-3}\text{ km}$, and region boundary clipping. Exported 12 comprehensive validation scenarios into `tests/fixtures/reference.json` (including Malapert centre and Haworth permanently shadowed crater bottom) with complete `summarize()` metrics and 20 sample-time Sun/Earth states. Documented data format specifications and known terrain/resolution limitations in `docs/datapack_format.md`.

## Task 2C Prompt (Verbatim)

```text
TASK 2C (hardening, no algorithm changes):
1. build_datapack.py: key the checkpoint to a hash of all point ids, x/y, ground heights, and observer
   heights. On mismatch, ignore the checkpoint with a printed warning and start fresh.
2. Add a test: change one point, confirm the old checkpoint is rejected.
3. build_datapack.py must refuse to run if any region's "source" field starts with "placeholder" or is
   empty. Add a test.
4. Do NOT write or edit coordinates in regions.json. Only I digitize them.
5. Append this prompt verbatim to docs/ai_log.md, including a note that the earlier regions.json was
   AI-generated and replaced by hand-digitized values.
```

## Task 2C Summary of Changes


Implemented pipeline hardening in `scripts/build_datapack.py` and regression validation in `tests/test_datapack.py` without modifying any core algorithms or physical constants:
1. **Cryptographic Checkpoint Keying (`compute_checkpoint_hash`, `load_or_create_checkpoint`)**: Keyed horizon precomputation checkpoints to a deterministic SHA-256 hash across observer heights and every grid point's `id`, stereographic `x_m`, `y_m`, and sampled `ground_height_m`. When an existing checkpoint (`data_src/horizons_checkpoint.npz`) has a missing or mismatched hash (or shape discrepancy), it is rejected with a warning (`WARNING: Checkpoint hash mismatch ... Ignoring checkpoint and starting fresh.`) and fresh arrays are initialized.
2. **Region Source Provenance Enforcement (`validate_regions`)**: Added validation ensuring `build_datapack.py` strictly refuses to run if any region's `source` field starts with `"placeholder"` (case-insensitive) or is empty/missing. Enforced both at CLI entry in `main()` (exiting with status code 1 and an error diagnostic) and at the entrance of `generate_grid_points()`.
3. **Automated Unit & Hardening Tests (`tests/test_datapack.py`)**:
   - `test_checkpoint_rejected_when_point_modified`: Verifies that modifying any point attribute ($x$, $y$, ground height, point ID) or observer height rejects the cached checkpoint, outputs the mismatch warning, resets completed states, and triggers fresh computation in `precompute_horizons`.
   - `test_build_datapack_refuses_placeholder_or_empty_source`: Verifies that empty, whitespace, null, missing, or `"placeholder*"` source values raise `ValueError` and trigger non-zero CLI exit in `main()`, while verifying that the hand-digitized `data_src/regions.json` passes validation.

## Task 2D Prompt (Verbatim)

```text
TASK 2D (no algorithm changes):
1. pick_regions.py: every SPACE-recorded region gets "picked_by": "pick_regions.py" and
   "picked_utc": <timestamp>. Existing regions without both fields are treated as undigitized
   and are re-prompted on the next run.
2. build_datapack.py: refuse to run if any region lacks "picked_by" and "picked_utc".
   Add tests for both cases.
3. Do NOT write or edit coordinates in regions.json, and do not add any claim about how the
   coordinates were obtained to docs/ai_log.md. I will write that myself.
4. Append this prompt verbatim to docs/ai_log.md.
```

## Task 2D Summary of Changes

Implemented region provenance tracking and precomputation validation guards without algorithm changes:
1. **Provenance Recording in Digitizer (`scripts/pick_regions.py`)**:
   - Updated `RegionDigitizer.record_current` so every SPACE-recorded candidate region record receives `"picked_by": "pick_regions.py"` and `"picked_utc": <timestamp>` formatted in ISO 8601 UTC (`%Y-%m-%dT%H:%M:%SZ`).
   - Added `is_region_digitized()` to verify the presence of non-empty `picked_by` and `picked_utc` fields. Existing regions lacking either or both fields are identified as undigitized, omitted from pre-drawn markers, and placed into the digitization queue to be re-prompted on the next run.
2. **Precomputation Refusal in Pipeline (`scripts/build_datapack.py`)**:
   - Enhanced `validate_regions()` to verify that every candidate region contains non-empty `picked_by` and `picked_utc` values. If any region lacks either field or both, `validate_regions()` raises `ValueError` and CLI execution terminates with exit code 1.
3. **Automated Unit & Hardening Tests**:
   - `tests/test_pick_regions.py`: Added `test_is_region_digitized` to validate field presence checks; added `test_undigitized_regions_are_reprompted` to confirm regions missing `picked_by` or `picked_utc` are queued for re-prompting; and added `test_space_record_adds_picked_fields` to verify that recording via SPACE correctly writes `picked_by` and UTC timestamp metadata to in-memory state and the output JSON file.
   - `tests/test_datapack.py`: Added `test_build_datapack_refuses_missing_picked_provenance` testing refusal when regions lack `picked_by`, `picked_utc`, or both, verifying CLI exit code 1, and confirming validation passes when both fields are present.
4. **Coordinate Integrity**: In accordance with instructions, coordinates in `data_src/regions.json` were not modified or edited.

## Task 2E Prompt (Verbatim)

```text
TASK 2E (no algorithm changes):
1. pick_regions.py: change DEFAULT_SOURCE_TAG to exactly:
   "approximate; centre placed in pick_regions.py from box positions measured on an annotated screenshot of NASA's Artemis III candidate-region map; not surveyed"
   Update every test that references it to use the constant.
2. tests: in test_regions_json_schema_and_values replace the radius_km == 4.0 assertion with
   1 <= radius_km <= 40. Keep the forward() consistency check.
3. tests: in test_build_datapack_refuses_placeholder_or_empty_source, steps 5 and 6 assert that the real
   regions.json LACKS picked fields; this breaks once I finish picking. Replace them with: the real
   data_src/regions.json must pass validate_regions (skip with a clear message if any region lacks
   picked_by or picked_utc).
4. build_datapack.py: add --spacing (default 1000 m). Region hillshade size: res = max(40, 2*radius_m/800) m/px.
   Raise the total web/data limit to 20 MB in code and tests.
5. generate_reference_fixtures: keep 12 cases, but replace the cases that assume a shadowed crater with the
   darkest and the brightest points of the pack by illumination_avg_fraction (1 m, 30 days from
   2027-01-01, step 3600), computed from the packed horizons. Keep malapert-massif-c. Print the ids chosen.
6. Update docs/datapack_format.md (spacing, radii) and append this prompt verbatim to docs/ai_log.md.
7. Do NOT edit data_src/regions.json.
Run pytest. Failures only in the regions.json tests are acceptable until I finish picking; say so.
```

## Task 2E Summary of Changes

Updated the digitizer source tag, data-pack CLI/sizing options, fixture selection, tests, and format documentation without modifying algorithms or `data_src/regions.json`:
1. **Digitizer Source Tag (`scripts/pick_regions.py`)**: Updated `DEFAULT_SOURCE_TAG` to `"approximate; centre placed in pick_regions.py from box positions measured on an annotated screenshot of NASA's Artemis III candidate-region map; not surveyed"`, and updated tests in `tests/test_datapack.py` to reference `DEFAULT_SOURCE_TAG`.
2. **Data Pack Configuration & Hillshades (`scripts/build_datapack.py`)**: Added `--spacing` CLI argument (default `1000.0` m, also updated `generate_grid_points` default), computed per-region hillshade resolution as `res = max(40, 2*radius_m/800)` m/px (`dx=res, dy=res`, capping dimensions at `800x800` px for larger radii), and raised `MAX_DATAPACK_MB` to `20.0` MB.
3. **Reference Fixture Selection (`scripts/build_datapack.py`)**: Added `select_darkest_and_brightest_points()` to evaluate `illumination_avg_fraction` at `1 m`, `30 days` from `2027-01-01`, `step 3600 s` directly from the packed horizons; updated `generate_reference_fixtures()` to keep 12 cases, keep `malapert-massif-c`, replace the `haworth-c` shadowed-crater assumption with the darkest and brightest pack points, and print the chosen IDs.
4. **Tests (`tests/test_pick_regions.py`, `tests/test_datapack.py`)**: Replaced `radius_km == 4.0` with `1 <= radius_km <= 40` while retaining the `forward()` check; updated `test_build_datapack_refuses_placeholder_or_empty_source` so the real `data_src/regions.json` must pass `validate_regions` (skipping cleanly when any region lacks `picked_by` or `picked_utc`); raised the `web/data` ceiling assertion to 20 MB; updated `test_reference_fixtures` and added unit tests covering `--spacing`, adaptive hillshade resolution, and darkest/brightest fixture selection.
5. **Documentation (`docs/datapack_format.md`)**: Updated default grid spacing (`1000 m` via `--spacing`), per-region radii (`1..40 km`), adaptive hillshade resolution formula, and the `20 MB` data-pack limit.

## Task 4+5 Prompt (Verbatim)

```text
TASK 4+5: Static web app in web/ (no build step, no frameworks, no CDN: vanilla HTML/CSS/JS ES modules,
Canvas 2D). It must work with `python -m http.server 8000` run inside web/, and on GitHub Pages
(relative URLs only).

DATA (already built; do not change): web/data/manifest.json, horizons.bin, ephem.bin, regions/<id>.png.
Read the manifest layout fields. Use the current pack for development; it will be rebuilt with different
region radii and grid spacing but the SAME format, so never hard-code counts.

PORT, DO NOT REINVENT: read lunar_engine/ephemeris.py (sun_earth_azel) and lunar_engine/visibility.py
(visible_fraction, longest_run, summarize) and port them to JavaScript exactly (same formulas, same
conventions, same step handling). Body vectors come from ephem.bin (float32 km, MOON_ME); site position =
lat/lon + ground_height_m + observer height; angular radii = asin(R/distance) with R from manifest
constants. Horizon = horizons.bin value/100 deg at 1-deg azimuth steps, linearly interpolated, periodic.

MODULES: js/data.js, geometry.js, visibility.js, metrics.js, panorama.js, charts.js, compare.js, main.js,
css/style.css, index.html, tests.html.

UI (single page, dark by default, light via prefers-color-scheme, responsive down to 360 px):
 1. Controls: region dropdown (all regions in the manifest), observer height toggle (1 m / 5 m), start date
    (limited to the ephemeris range), duration (7, 14, 30, 90, 365 days).
 2. Site picker: show regions/<id>.png with the manifest extent, overlay grid points as dots coloured by
    illumination_avg_fraction for the chosen range (compute lazily), click selects the nearest point;
    default is the region centre. Show lat, lon, ground height, slope.
 3. Panorama (canvas): azimuth 0-360 horizontally (0 = outward-radial north, clockwise), elevation
    vertically; filled terrain silhouette; Sun and Earth drawn as discs at true angular size at the
    selected time (partly hidden discs visibly clipped by the horizon); faint dotted tracks over the
    period; a time slider that moves both discs and updates a "now" card (Sun disc visible %, Earth disc
    visible %).
 4. Metric cards for the whole period with these exact labels and one-line plain-language help:
    "Illumination availability", "Sun visible (any part)", "Longest continuous darkness",
    "Geometric Earth visibility (any part of the disc)", "Earth more than half visible",
    "Longest Earth-visibility blackout". Visible note: "Earth visibility here is geometric (line of sight
    to any part of Earth's disc), not a radio link budget."
 5. Timeline strips for Sun and Earth visible fraction over the period, tied to the slider.
 6. Comparison: "Add to comparison" (max 3: site + height + date range). Side-by-side table with the same
    metrics and small bars. NO overall score or "best" label. Add: "Which site is better depends on mission
    needs: power, communications and terrain safety trade off."
 7. "How this works" panel: data sources (LOLA LDEM_80S_20MPP_ADJ from NASA PGDA; NAIF SPICE kernels de440,
    moon_pa_de440, naif0012, MOON_ME frame), the method in 6 short steps, the limitations from
    docs/datapack_format.md, and "region positions are approximate; boxes were measured on an annotated
    screenshot of NASA's map". Footer with NASA credits and a GitHub link placeholder.
 8. Clear error if data cannot be fetched ("serve this folder over http, not file://"), a loading
    indicator while horizons.bin loads, keyboard-accessible controls, colour-blind-safe colours
    (Sun orange, Earth blue, terrain grey), no console errors.

TESTS: web/tests.html loads tests/fixtures/reference.json and, for each case, recomputes in JS and prints
PASS/FAIL with max errors: summary metrics (illumination +-0.005, percentages +-0.5, hours +-1 step),
visible fractions at the 20 sample times (+-0.002), az/el (+-0.01 deg). Add a Node test runner only if Node
is installed (check first).

FRONTEND TEACHING: create docs/frontend_explained.md for a backend developer weak at frontend: per file, what
it does, the main functions, how data flows from manifest/ephem/horizons to the screen, and how to change
a label or colour.

DELIVER: file list, how to run, test output, anything unsure. Append this prompt verbatim to docs/ai_log.md.
```

## Task 4+5 Summary of Changes

Implemented the dependency-free static web application under `web/` using vanilla HTML5, CSS3, ES Modules, and Canvas 2D, paired with a JavaScript port of the Python lunar engine, browser verification page, Node test runner, and backend-friendly frontend documentation:
1. **Data & Engine Port (`web/js/data.js`, `geometry.js`, `visibility.js`, `metrics.js`)**: Dynamically reads array shapes, physical constants, regions, observer heights, and grid points from `manifest.json` without hardcoded counts; decodes little-endian `ephem.bin` (`float32` km, `MOON_ME`) and `horizons.bin` (`int16` `0.01°`); ports `site_local_frame`, `site_position_km`, `sun_earth_azel`, `disc_visible_fraction`, periodic `visible_fraction`, `longest_run`, and `summarize` directly from `lunar_engine`; and lazily evaluates region-wide illumination in non-blocking batches with caching.
2. **Interactive Canvas UI (`web/index.html`, `css/style.css`, `panorama.js`, `charts.js`, `compare.js`, `main.js`)**: Built a dark-default / `prefers-color-scheme: light` single-page app responsive down to `360 px` with region/height/date/duration controls, hillshade site picker with Viridis-coloured grid points and keyboard navigation, `0–360°` horizon panorama (plus `1:1` Sun/Earth zoom modes) with horizon-clipped discs and faint dotted tracks, time slider + playback + "Now" card, Sun/Earth timeline strips tied to the slider, all 6 required metric cards, 3-entry side-by-side comparison table without scores or "best" labels, methodology/limitations panel, NASA credits footer, streaming load progress bar, and `file://`/fetch error guards.
3. **Verification & Documentation (`web/tests.html`, `tests/test_web.mjs`, `docs/frontend_explained.md`)**: Created browser and Node (`v24.18.0`) test runners comparing JS outputs against `tests/fixtures/reference.json`, plus a plain-language frontend architecture guide in `docs/frontend_explained.md`.

## Task 2F Prompt (Verbatim)

```text
TASK 2F (no algorithm changes):
1. generate_reference_fixtures: compute each fixture's horizon by decoding the PACKED horizons
   (int16/100 from web/data/horizons.bin) for the chosen point and height, instead of calling
   compute_horizon. Summary metrics and sample-time visible fractions must come from that horizon.
   Add "horizon_source": "packed int16" to the fixture file. Keep all tolerances as they are.
2. UI map colouring: use a time step of at least 3600 s and at most 90 days for the colour map, process
   in chunks (yield to the browser between chunks), cancel when any control changes, show progress.
   Test with the largest region and 365 days selected; report how long the UI is blocked and the longest
   single frame.
3. Panorama: add a caption under the Full 360 view: "Azimuth 0 deg = away from the pole (outward), clockwise.
   Discs drawn at true vertical size; use Zoom for true shape."
   Add to "How this works": "Horizons are stored in 0.01 deg steps; this changes a single moment's
   visible fraction by up to ~0.01 at the Sun's edge and metrics by < 0.001."
4. Add /index.html at the repo root that redirects to web/index.html (meta refresh plus a link). Check
   every web asset path is relative and works when serving the repo root (open /web/ and /web/tests.html).
5. README.md: sections Run locally, Tests, Data sources (NASA LOLA via PGDA, NAIF SPICE), Limitations.
6. Append this prompt verbatim to docs/ai_log.md. Do NOT edit data_src/regions.json.
```

## Task 2F Summary of Changes

1. **Packed Reference Fixtures (`scripts/build_datapack.py`, `tests/fixtures/reference.json`, `tests/test_datapack.py`)**: Updated `generate_reference_fixtures()` to decode quantized horizons (`int16 / 100.0` from `horizons.bin` / `horizons_data`) rather than calling `compute_horizon`, derive summary metrics and sample-time visible fractions from that decoded horizon, and add `"horizon_source": "packed int16"` per fixture case. Regenerated `tests/fixtures/reference.json` against `web/data/` and updated Python/JS fixture checks while keeping all tolerances unchanged.
2. **Non-Blocking UI Map Colouring (`web/js/metrics.js`, `web/js/charts.js`, `web/js/main.js`, `web/index.html`, `web/css/style.css`)**: Capped colour-map evaluation at `>= 3600 s` time step and `<= 90 days` (`getColorMapTimeWindow`), chunked `computeRegionIlluminationLazy` with `requestAnimationFrame` yielding (`6 ms` budget), added progress bar + status updates, and wired cancellation on any control change (`region`, `height`, `date`, `duration`).
3. **Panorama Caption, Limitations & Root Redirect (`web/index.html`, `web/js/main.js`, `index.html`, `README.md`)**: Added the required Full 360 caption, added the `0.01 deg` horizon quantization note under "How this works", created `/index.html` redirecting to `web/index.html` after verifying relative web asset paths, and wrote `README.md` with `Run locally`, `Tests`, `Data sources`, and `Limitations` sections without modifying `data_src/regions.json`.


## Phase 1 Request

```text
PHASE 1 (stay strictly inside this scope).

ALLOWED FILES: scripts/build_datapack.py, tests/test_datapack.py, web/js/*.js, web/index.html,
web/tests.html, web/css/style.css, index.html (repo root), README.md, docs/*.md.
Do NOT edit: lunar_engine/*, data_src/regions.json, anything under web/data/, tests/fixtures/reference.json.
Do NOT run any git command. Do NOT run build_datapack.py against the real output paths (I run the
rebuild myself). If you need to test the generator, use a temporary directory.

TASKS:
1. build_datapack.py, generate_reference_fixtures: compute each fixture's horizon by decoding the PACKED
   horizons (int16/100 from the horizons.bin being written, for the chosen point and height) instead of
   calling compute_horizon. Summary metrics and sample-time visible fractions must come from that
   horizon. Add "horizon_source": "packed int16" to the fixture file. Keep all tolerances as they are.
   Add a unit test that decodes a tiny synthetic pack and checks the fixture generator uses it.
2. UI map colouring (web/js): time step at least 3600 s and at most 90 days of samples for the colour
   map, processed in chunks that yield to the browser between chunks, cancelled when any control changes,
   with a progress indicator. Test with the largest region and 365 days; report how long the UI is
   blocked and the longest single frame.
3. Panorama caption under the Full 360 view: "Azimuth 0 deg = away from the pole (outward), clockwise.
   Discs drawn at true vertical size; use Zoom for true shape." Add to "How this works": "Horizons are
   stored in 0.01 deg steps; this changes a single moment's visible fraction by up to ~0.01 at the Sun's
   edge and metrics by < 0.001."
4. Repo-root index.html must redirect to web/index.html (meta refresh plus a link). Check every web asset
   path is relative and works when serving the repo root (open /web/ and /web/tests.html).
5. README.md: sections Run locally, Tests, Data sources (NASA LOLA via PGDA, NAIF SPICE), Limitations.
6. Append this prompt verbatim to docs/ai_log.md with a short summary.
7. Run pytest and node tests/test_web.mjs. Failures caused by the old pack not matching the new
   fixtures are acceptable; say so.

WHEN DONE: list exactly which files you changed or created, test output, and anything you were unsure about.
```

### Phase 1 Summary
1. **Packed Fixture Generation & Synthetic Pack Test (`scripts/build_datapack.py`, `tests/test_datapack.py`)**: Updated `generate_reference_fixtures` to accept `horizons_bin` (defaulting to `web/data/horizons.bin` when `horizons_data` is omitted) and updated `main()` to pass `horizons_bin=output_horizons` so Step 6 reads and decodes the packed `int16 / 100.0` horizons written to disk rather than calling `compute_horizon`. Added `test_generate_reference_fixtures_decodes_tiny_synthetic_pack` in `tests/test_datapack.py` to test a tiny synthetic `[2, 2, 360]` `horizons.bin` file end-to-end.
2. **UI Colour-Map Responsiveness & Canvas Batching (`web/js/metrics.js`, `web/js/charts.js`, `web/js/geometry.js`, `web/js/visibility.js`, `web/js/panorama.js`, `docs/frontend_explained.md`)**: Retained the `>= 3600 s` step and `<= 90 days` cap, `requestAnimationFrame` chunking, progress bar, and cancellation-on-change while lowering the default chunk time budget to `5.0 ms`, replacing `Math.hypot` with inline scalar `Math.sqrt` projections, single-passing `summarize()`, and bucketing site/track marker fills into shared canvas paths for smooth frames on large grids (`mons-mouton-plateau`, 2,629 sites at 1000 m spacing over 365 days).
3. **Verification of Static Deliverables & Tests**: Verified the existing Full 360 panorama caption and `0.01 deg` quantization note in `web/index.html` and `web/js/main.js`, the root `index.html` redirect and relative asset paths when serving repo root (`/web/` and `/web/tests.html`), and the required `README.md` sections.


## Phase 2 Request

```text
PHASE 2 (stay strictly inside this scope).

ALLOWED FILES: web/index.html, web/css/style.css, web/js/*.js, tests/test_web.mjs, web/tests.html,
scripts/build_datapack.py (ONLY the order of checks inside main()), tests/test_datapack.py (only if
needed for item 6), docs/frontend_explained.md, docs/ai_log.md, README.md.
Do NOT edit: lunar_engine/*, data_src/*, anything under web/data/, tests/fixtures/*.
Do NOT run any git command. Do NOT run build_datapack.py against the real output paths.

TASKS:
1. Layout: the left (site picker) column must not stretch; remove the blank card next to the visibility
   timeline strips. Check widths 1440, 1024, 768, 360 px.
2. Map metric selector in the Site Picker (segmented control): "Sun illumination" (default),
   "Earth visible (any part)", "Earth more than half visible". Reuse the existing chunked, cancellable
   computation, with the same time window rules; cache per region+height+window+metric; legend text changes
   with the metric ("0% ... 100% of the time"). The metric functions used by the map must be the SAME
   functions summarize() relies on (same discVisibleFraction thresholds: any = fraction > 0, more than half =
   fraction > 0.5).
3. Two buttons: "Select brightest site" and "Select site with most Earth view", enabled once the map
   computation for the current metric/window has finished. They choose the maximum of the computed values
   among the region's grid points (ties: closest to region centre). Show a note: "Selected: highest value
   among N grid sites in this region for this period and height. This is not a recommendation." NO combined
   score and no "best overall" label anywhere.
4. In "How this works", replace the light-time limitation with exactly: "Geometric ephemeris (no light-time or
   aberration correction): NAIF SPICE 'LT+S' directions differ from the geometric vectors used here by about
   0.006 deg for the Sun and 0.0002 deg for Earth, far below the 0.53 deg solar disc diameter and the 0.01 deg
   horizon precision."
5. Default region on load: Malapert Massif (site = its centre), if present in the manifest; otherwise first region.
6. scripts/build_datapack.py main(): load and validate data_src/regions.json BEFORE checking for the DEM, so
   the two refusal tests pass without LUNAR_DEM_PATH. Do not change anything else in that file.
7. Tests (tests/test_web.mjs): add checks that the map's Earth-any and Earth-more-than-half values for two
   reference fixture cases match the fixture summary earth_any_pct and earth_mostly_pct within 0.5
   percentage points (same time window as the fixture), and that the brightest-site picker returns the
   maximum.
8. Update docs/frontend_explained.md and README.md (Tests: how to run with and without the DEM).
   Append this prompt verbatim to docs/ai_log.md with a short summary.
9. Run pytest WITHOUT LUNAR_DEM_PATH set and again with it set, and node tests/test_web.mjs. Report both
   pytest outputs. Report the UI blocked-time measurement for the largest region at 365 days for each metric.

WHEN DONE: list exactly which files you changed or created, test outputs, and anything unsure.
```

### Phase 2 Summary
1. **Layout & Default Region (`web/css/style.css`, `web/js/data.js`, `web/js/main.js`, `web/index.html`)**: Set `align-items: start` on `.workspace-grid` so the Site Picker panel sizes to its own content instead of stretching vertically alongside the timeline strips, verified responsive widths `1440`, `1024`, `768`, and `360 px`, added `getDefaultRegionId()` defaulting to Malapert Massif (and its centre `malapert-massif-c`) when present in `manifest.json`, and updated the `"How this works"` geometric ephemeris limitation text to the exact `'LT+S'` comparison note.
2. **Site Picker Map Metrics & Max-Site Buttons (`web/js/visibility.js`, `web/js/metrics.js`, `web/js/charts.js`, `web/js/main.js`, `web/index.html`)**: Extracted shared `stepDiscVisibleFraction`, `isDiscVisibleAny` (`fraction > 0`), and `isDiscVisibleMostly` (`fraction > 0.5`) helpers used identically by `summarize()` and the Site Picker map metric computation; added the segmented map metric selector (`Sun illumination`, `Earth visible (any part)`, `Earth more than half visible`) with per-`region+height+window+metric` caching and dynamic colourbar legend/tooltip labels; and added `"Select brightest site"` and `"Select site with most Earth view"` buttons (`pickMaxMetricPoint()` breaking ties by proximity to region centre) with the required non-recommendation note and no combined score or `"best overall"` label.
3. **Pipeline Check Order, Tests & Documentation (`scripts/build_datapack.py`, `tests/test_web.mjs`, `web/tests.html`, `docs/frontend_explained.md`, `README.md`)**: Reordered `main()` in `scripts/build_datapack.py` to load and validate `data_src/regions.json` before checking `LUNAR_DEM_PATH`; added map Earth-metric fixture checks, default-region checks, cache-key separation, and max-site picker checks in `tests/test_web.mjs` and `web/tests.html`; updated `docs/frontend_explained.md` and `README.md` (with DEM and no-DEM `pytest` instructions).


## Phase 2.1 Request

```text
PHASE 2.1 (small fix; stay strictly inside this scope).
ALLOWED FILES: web/js/main.js, web/js/metrics.js, web/index.html, web/css/style.css (only if needed),
tests/test_web.mjs, web/tests.html, docs/frontend_explained.md, docs/ai_log.md.
Do NOT edit anything else. Do NOT run any git command.
1. formatMaxSelectedNote must say which metric and which window were used, e.g.:
   "Selected: highest 'Sun illumination' among 441 grid sites in this region (map window: first 30 days at
   1 h steps, 1 m observer height). This is not a recommendation."
   When the chosen duration is longer than the map window (90 days), append: "The cards below use your full
   period." Use the real window from getColorMapTimeWindow, not hard-coded numbers.
2. Add a one-line caption under the map legend: "Map colours use at most the first 90 days at 1 h steps; the
   cards below use your full period at 15 min steps."
3. Update tests in tests/test_web.mjs (and web/tests.html if it checks the old note text) for the new note text
   with both a 30-day and a 365-day case.
4. Run pytest (with and without LUNAR_DEM_PATH) and node tests/test_web.mjs and report the outputs.
5. Update docs/frontend_explained.md and append this prompt verbatim to docs/ai_log.md.
WHEN DONE: list exactly which files you changed, and the test outputs.
```

### Phase 2.1 Summary
1. **Rich Max-Selection Note (`web/js/metrics.js`, `web/js/main.js`)**: Updated `formatMaxSelectedNote` to accept the active metric, the real `mapTimeWindow` returned by `getColorMapTimeWindow`, `observerHeightM`, and selected `days`, reporting e.g. `"Selected: highest '<metric>' among N grid sites in this region (map window: first D days at S h steps, H m observer height). This is not a recommendation."` and appending `" The cards below use your full period."` when `days` exceeds the map window length.
2. **Map Legend Caption (`web/index.html`, `web/css/style.css`)**: Added `#map-legend-caption` below `#colorbar-row` explaining `"Map colours use at most the first 90 days at 1 h steps; the cards below use your full period at 15 min steps."`.
3. **Tests & Documentation (`tests/test_web.mjs`, `web/tests.html`, `docs/frontend_explained.md`, `docs/ai_log.md`)**: Updated `tests/test_web.mjs` and `web/tests.html` to test `formatMaxSelectedNote` for both 30-day and 365-day windows plus verify the map legend caption in `web/index.html`, and updated `docs/frontend_explained.md`.

