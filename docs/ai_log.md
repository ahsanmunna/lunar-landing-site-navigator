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

The monolithic `horizon.py` script and auxiliary inspection utilities were moved to `legacy/` and refactored into a modular, clean Python package `lunar_engine` containing `config`, `geometry`, `horizon`, `ephemeris`, and `visibility` modules, driven by a new command-line script `analyze_site.py`. In accordance with the prompt requirements: apparent angular radii for the Sun ($R=695700\text{ km}$) and Earth ($R=6371\text{ km}$) are dynamically computed per time step using $\arcsin(R / d)$ from the site-to-body topocentric vector norm rather than hard-coded constants; the default simulation time step was shifted to $900\text{ s}$ (`step_s`) and duration metrics are converted to hours scaled by `step_s / 3600`; `summarize()` returns a structured dictionary containing all requested illumination, communication blackout, and terrain metrics along with full input provenance; configurable observer heights (including $1\text{ m}$ and $5\text{ m}$, default $2\text{ m}$) are supported across terrain horizon and ephemeris calculations; exact polar singularity handling for $\text{lat} = -90^\circ$ ($\rho_0 = 0$) defines north along $\text{lon} = 0^\circ$ and avoids division by zero across both 2D stereographic map vectors and 3D Moon-fixed coordinate frames; `ephemeris.py` exposes vectorized access to raw Moon-centred position vectors; and a comprehensive pytest suite covers geometry round-trips within $10^{-6\circ}$, South Pole singularity robustness, SPICE sub-solar/sub-Earth calibration checks, distance-derived angular radii, and regression tests against LOLA DEM benchmark sites (which skip cleanly when `LUNAR_DEM_PATH` is unset).
