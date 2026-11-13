# Validation & Verification Report

This document summarizes every automated check currently in the repository, what each test proves, its acceptance tolerance, observed test outputs, and what has **not** been validated.

## Latest Observed Test Runs

- **Python (`pytest -v` with `LUNAR_DEM_PATH` set to `LDEM_80S_20MPP_ADJ.tiff`)**: `56 passed` (`Python 3.13.7`, `pytest-9.1.1`).
- **Node.js web parity & unit suite (`node tests/test_web.mjs`, Node `v24.18.0`)**: `ALL WEB JS TESTS PASSED.`
  - Verbatim max-error line across all 12 fixture cases:
    `Max errors across all 12 cases: Δillum=0.000000, Δpct=0.0000, Δh=0.00h, Δaz=0.00005°, Δel=0.00005°, Δvis=0.000001`
- **Browser runner (`web/tests.html`)**: Available when serving the repo root over HTTP (`http://localhost:8000/web/tests.html`); executes 6 browser unit checks plus the same 12 fixture cases in `tests/fixtures/reference.json` against `web/js/` modules (not executed inside a browser UI during Phase 3 documentation verification).

---

## Automated Validations

### 1. SPICE Ephemeris, Frame Alignment & Angular Radius

| Test File | Test Function | What It Proves | Tolerance / Bounds |
| :--- | :--- | :--- | :--- |
| `tests/test_ephemeris.py` | `test_spice_sub_points_check` | Verifies loaded NAIF SPICE kernels (`de440.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_220930.tf`, `naif0012.tls`) reproduce LRO reference sub-Earth point (`-1.600°` lat, `6.545° E` lon) and sub-solar longitude (`135.917° E`) in `MOON_ME` at `2026-06-18 18:00:00 UTC`. | `abs=0.05°` |
| `tests/test_ephemeris.py` | `test_angular_radius_pure_formula` | Proves `angular_radius_deg(R, d)` equals `degrees(arcsin(R / d))` across scalar and vector distances (Earth at `384,400 km` and `[360,000, 384,400, 405,000] km`; Sun at `1.496e8 km`). | `abs=1e-12°` / `atol=1e-12°` |
| `tests/test_ephemeris.py` | `test_angular_radius_calculation` | Proves `sun_earth_azel` computes distance-derived Earth and Sun angular radii (`6371.0 km` and solar radius) across 30 days (`step_s=3600`) at `(-86°, 2°)`, capturing Earth's orbital distance modulation (`min` in `[0.89°, 0.91°]`, `max` in `[1.01°, 1.03°]`) and solar radius (`[0.269°, 0.273°]`). | `atol=1e-9°` elementwise |
| `tests/test_ephemeris.py` | `test_moon_centered_raw_vectors` | Verifies 24 hourly `(24, 3)` `MOON_ME` position vectors stay within physical Earth (`350,000–410,000 km`) and Sun (`1.4e8–1.6e8 km`) distances. | Physical range bounds |
| `tests/test_ephemeris.py` | `test_observer_heights_supported` | Proves `sun_earth_azel` supports `1.0`, `2.0`, and `5.0` m observer heights over 12 hourly steps. | Exact shape (12 steps) |

### 2. Polar Stereographic Geometry & Topocentric ENU Frames

| Test File | Test Function | What It Proves | Tolerance / Bounds |
| :--- | :--- | :--- | :--- |
| `tests/test_geometry.py` | `test_geometry_round_trip` | Proves `forward()` ↔ `inverse()` coordinate transforms round-trip accurately across 7 South Polar coordinates (`-80°` to `-89.99°`, longitudes `0°` to `180°` / `-179.9°`). | `abs=1e-6°` (lat & mod-360 lon) |
| `tests/test_geometry.py` | `test_pole_adjacent_round_trip` | Proves near-pole coordinate round-trip consistency across 8 cases (`-89.999999°`, `-89.9999999°`) in both `lunar_engine.geometry` and `scripts._geo`. | `abs=1e-6°` |
| `tests/test_geometry.py` | `test_pole_adjacent_xy_round_trip` | Proves tiny `(x, y)` metre offsets (`1e-5` to `1.0` m) round-trip cleanly around the pole in both modules. | `abs=1e-6` m |
| `tests/test_geometry.py` | `test_south_pole_lat_neg_90_does_not_crash` | Proves exact South Pole (`lat = -90°`) does not trigger division-by-zero singularities: `forward=(0, 0)`, `inverse=(-90, 0)`, `k0 ≈ 1.0`, orthonormal local frames, finite `(360, 2)` directions, valid `site_position_km`. | `atol=1e-12` on local frames |
| `tests/test_geometry.py` | `test_site_local_frame_orthonormality` | Proves `site_local_frame` vectors (`east`, `north`, `up`) are unit-length, mutually orthogonal, and right-handed (`east × north == up`) across 16 `(lat, lon)` combinations. | `abs=1e-12` / `atol=1e-12` |

### 3. Partial-Disc Visibility & Mission Metric Calculations

| Test File | Test Function | What It Proves | Tolerance / Bounds |
| :--- | :--- | :--- | :--- |
| `tests/test_visibility.py` | `test_visible_fraction_at_t_minus1_0_1` | Proves spherical-cap visible fraction maps `t = (el - horizon) / r_ang` at `-1, 0, +1` to `0.0, 0.5, 1.0` and clamps extremes (`t = -2.5 -> 0.0`, `t = 3.0 -> 1.0`). | `abs=1e-12` / `atol=1e-12` |
| `tests/test_visibility.py` | `test_longest_run`, `test_summarize_metrics` | Proves longest continuous zero/threshold run detection and `step_s / 3600.0` hour scaling (verified with 4 steps at `900 s`), plus metric aggregation. | Exact / unit-tested assertions |

### 4. Precomputed Data Pack vs Raw Engine & SPICE

| Test File | Test Function | What It Proves | Tolerance / Bounds |
| :--- | :--- | :--- | :--- |
| `tests/test_datapack.py` | `test_datapack_file_sizes_match_manifest_layout` | Proves `horizons.bin` (`n_points * n_heights * 360 * 2`), `ephem.bin` (`n_times * 2 * 3 * 4`), regional PNG extents/sizes (`> 1000` bytes), and total `web/data/` footprint (`< 20.0 MB`, `MAX_DATAPACK_MB == 20.0`) match `web/data/manifest.json`. | Exact byte match; `< 20.0 MB` |
| `tests/test_datapack.py` | `test_horizons_match_fresh_engine_computation` *(requires `LUNAR_DEM_PATH`)* | Proves unpacked `int16` horizons (`0.01°` scale) at 5 deterministic pseudo-random grid points (`seed=20261108`, both `1 m` and `5 m` heights) match fresh `compute_horizon()` execution on the 20 m LOLA DEM with zero `-32768` nodata. | `<= 0.011°` horizon; `abs=1.0` m `ground_height_m` |
| `tests/test_datapack.py` | `test_ephemeris_vectors_match_spice` | Proves `float32` (`<f4`) Moon-centred Sun and Earth vectors in `web/data/ephem.bin` at 3 deterministic pseudo-random epochs (`seed=20261108`) match direct `spice.spkpos` calls. | `<= 1e-3` km Euclidean norm |
| `tests/test_datapack.py` | `test_no_point_outside_region_circle` | Proves all grid points fall inside their region radius, carry valid `slope_deg >= 0.0`, and stay inside `|x|, |y|, rho < 299,000.0` m (`5 km` margin inside the `304 km` `80°S` DEM edge). | `dist <= radius_m + 1e-3` m |
| `tests/test_datapack.py` | `test_reference_fixtures`, `test_generate_reference_fixtures_decodes_tiny_synthetic_pack` | Proves `tests/fixtures/reference.json` consistency and end-to-end tiny-pack encode/decode parity against `lunar_engine`. | `abs=1e-12` summary; `abs=1e-6` sample vis |
| `tests/test_datapack.py` | Builder guardrail & helper tests (`test_checkpoint_rejected_when_point_modified`, `test_build_datapack_refuses_placeholder_or_empty_source`, `test_build_datapack_refuses_missing_picked_provenance`, `test_build_datapack_spacing_cli_default_and_override`, `test_generate_region_hillshades_adaptive_resolution`, `test_select_darkest_brightest_and_generate_fixtures`) | Proves `scripts/build_datapack.py` rejects tampered checkpoints, missing `picked` provenance, or placeholder coordinates, and validates CLI spacing, hillshades, and fixture selection. | Assertion checks |
| `tests/test_pick_regions.py` | 9 tests | Proves `data_src/regions.json` schema (`1 <= radius_km <= 40`, `forward()` consistency within `0.1` m), digitizer name matching, height sampling, save guards, and re-prompting logic. | `0.1` m coordinate check |

### 5. Two DEM End-to-End Regression Sites

Both tests run `sun_earth_azel` / full terrain horizon computation with `start="2027-01-01"`, `days=30`, `step_s=3600.0`, `observer_height_m=2.0` against the 20 m LOLA DEM (`LUNAR_DEM_PATH` required):

| Test File | Test Function | Site & Regime | Proven Reference Values & Tolerances |
| :--- | :--- | :--- | :--- |
| `tests/test_regression.py` | `test_regression_site_1` | `lat=-86.0°`, `lon=2.0°` (high sunlit ridge near Malapert) | `ground_height_m ≈ 5154.0 ± 10.0 m`, `horizon_min ≈ -5.10° ± 0.05°`, `horizon_max ≈ 3.64° ± 0.05°`, `illumination_avg_fraction ≈ 0.84 ± 0.02`, `earth_mostly_pct ≈ 45.0% ± 2.0`, `earth_any_pct ≈ 49.0% ± 2.0`, `earth_longest_blackout_h ≈ 212.0 h ± 6.0 h` |
| `tests/test_regression.py` | `test_regression_site_2` | `lat=-87.3°`, `lon=77.0°` (deep permanently shadowed interior) | `horizon_min > 6.0°`, `illumination_avg_fraction == 0.0 ± 1e-6`, `earth_any_pct == 0.0 ± 1e-6` |

### 6. JavaScript Web Engine Parity vs Python (12 Reference Fixture Cases)

Both `tests/test_web.mjs` (Node.js) and `web/tests.html` (browser) execute the exact browser ES modules (`web/js/geometry.js`, `web/js/visibility.js`, `web/js/metrics.js`, `web/js/data.js`, etc.) across 12 cases generated by Python in `tests/fixtures/reference.json` (`horizon_source == "packed int16"`, covering `malapert-massif-c`, `peak-near-cabeus-b-p006`, `malapert-massif-p043`, `peak-near-cabeus-b-c`, `mons-mouton-c`, `nobile-rim-1-c`, `de-gerlache-rim-2-c`, and `slater-plain-c` across `1 m` and `5 m` heights, all using start date `2027-01-01`, a duration of `30.0` days (30 days), and a step size of `900.0 s` / 15 minutes):

| Metric / Field | Configured Pass Tolerance (`tests/test_web.mjs` & `web/tests.html`) | Observed Max Error (`node tests/test_web.mjs`) |
| :--- | :--- | :--- |
| Solar illumination availability | `<= 0.005` | `Δillum=0.000000` |
| Sun/Earth visibility percentages | `<= 0.5` pp | `Δpct=0.0000` |
| Longest continuous darkness / blackout | `<= 1 step` (`stepHours + 1e-9`) | `Δh=0.00h` |
| Topocentric azimuth | `<= 0.01°` | `Δaz=0.00005°` |
| Topocentric elevation | `<= 0.01°` | `Δel=0.00005°` |
| Instantaneous sample disc visibility | `<= 0.002` | `Δvis=0.000001` |

`tests/test_web.mjs` also runs 12 unit/integration checks (spherical-cap math, ENU projection, map colour metrics `Earth visible (any part)` & `Earth more than half visible` within `0.5` pp against 2 fixtures, lazy chunk loading/caching, max-selection banners, and map legend text); `web/tests.html` runs 6 browser unit checks plus the 12 fixture cases.

---

## Not Validated

1. **No comparison against NASA PGDA illumination or Earth-visibility maps**: Output illumination percentages, cumulative sunlight maps, and Earth-visibility curves have **not** been quantitatively benchmarked against published NASA PGDA illumination or Earth-visibility data products.
2. **Earth visibility is geometric, not a radio link**: Earth visibility metrics evaluate geometric line of sight of Earth's spherical disc above terrain horizons only. They do **not** model RF/optical link budgets, Fresnel zone diffraction, multipath off nearby crater walls, ground-station elevation angles/schedules, or transponder SNR.
3. **DEM resolution, quantization, and near-field terrain limits**: Local terrain within ~100 m controls positive horizon cutoffs for 1 m and 5 m observer heights, but `LDEM_80S_20MPP_ADJ.tiff` (`20 m/px`) cannot resolve sub-20 m boulders, regolith scarps, or micro-craters, and packed web horizons discretize rays at 1° azimuth steps and `0.01°` elevation precision. Outputs have not been validated against higher-resolution NAC DTM or spacecraft surface imagery.
4. **Approximate region positions**: Candidate region centres and radii (`data_src/regions.json`) were picked manually with `scripts/pick_regions.py` from box positions measured on an annotated screenshot of NASA's Artemis III candidate-region map and have not been cross-checked against official GIS shapefiles.
5. **JS-vs-Python parity validates the port, not the underlying physics**: Parity between Python and JavaScript verifies numerical fidelity and algorithmic translation across the two runtimes, but does not validate the physical correctness of the underlying modeling assumptions.
6. **SPICE-vs-LRO check covers one epoch**: The SPICE orientation and frame-alignment check in `tests/test_ephemeris.py` verifies sub-Earth and sub-solar coordinates against LRO reference values at a single epoch (`2026-06-18 18:00:00 UTC`), rather than across the full 2027–2029 simulation mission envelope.
7. **DEM frame definition (DE421 vs DE440 MOON_ME)**: NASA PGDA states its DEM is in the `MOON_ME` frame of the DE421 ephemeris while this project uses the DE440 `MOON_ME` frame kernel (`moon_de440_220930.tf`); the difference was not quantified in this repository.
