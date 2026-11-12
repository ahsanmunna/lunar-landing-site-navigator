# Lunar Landing Site Navigator (`lunar_engine` + Static Web App)

A lunar South Pole landing-site illumination and Earth line-of-sight analysis toolkit developed for NASA Space Apps 2026. It combines a modular Python engine (`lunar_engine`) using LOLA topography and NAIF SPICE kernels with a precomputed data pack (`web/data/`) and a dependency-free static web explorer (`web/`).

For any candidate site, the tool computes:
1. **Terrain Horizon**: 360-degree horizon profile (0° = outward-radial north, clockwise) from the 20 m LOLA South Polar DEM (`LDEM_80S_20MPP_ADJ.tiff`) blended with a 160 m regional cache (`dem_160m_cache.npy`) and lunar curvature.
2. **SPICE Ephemeris**: Topocentric azimuth, elevation, and distance-derived angular radii (`arcsin(R / distance)`) for the Sun and Earth in the `MOON_ME` frame (Earth's angular radius is about 0.90–1.02 deg depending on the Earth–Moon distance).
3. **Visibility & Mission Metrics**: Partial-disc visible fraction above terrain, solar illumination availability, Sun/Earth visibility percentages, and longest continuous darkness and Earth-visibility blackout spans.

## Project Structure

```text
├── index.html                  # Root redirect to web/index.html
├── lunar_engine/               # Core Python package (geometry, horizon, ephemeris, visibility)
├── scripts/                    # Data pack precomputation & interactive region digitizer
├── web/                        # Static HTML/CSS/JS ES module web app & browser verification suite
│   ├── index.html              # Interactive Navigator UI
│   ├── tests.html              # Browser verification page (Python fixtures vs JS)
│   ├── css/style.css           # Responsive dark/light theme styles
│   ├── js/                     # Vanilla ES modules (data, geometry, visibility, metrics, panorama, charts, compare, main)
│   └── data/                   # Precomputed manifest.json, horizons.bin, ephem.bin, regions/<id>.png
├── data_src/                   # Region names and candidate region centres/radii
├── kernels/                    # NAIF SPICE kernels (TLS, BSP, BPC, TF)
├── tests/                      # pytest suite, Node web test runner (test_web.mjs), reference fixtures
├── docs/                       # Data pack specification, frontend guide, AI engineering log
├── analyze_site.py             # Single-site Python CLI
├── requirements.txt            # Python dependencies
└── LICENSE                     # Apache-2.0
```

## Run locally

### 1. Web App (Static HTTP Server, No Build Step)

Browsers block ES modules and `fetch()` over `file://`. Serve the **repository root** over HTTP so both `/web/` and `/web/tests.html` (which fetches `../tests/fixtures/reference.json`) work cleanly:

```powershell
python -m http.server 8000
```

Then open:
- `http://localhost:8000/` (redirects automatically to `web/index.html`)
- `http://localhost:8000/web/` (Lunar Landing Site Navigator)
- `http://localhost:8000/web/tests.html` (Browser verification suite)

### 2. Python Environment & CLI (`analyze_site.py`)

Requires Python 3.10+ (and Node.js 18+ if running the CLI JS test runner):

```powershell
pip install -r requirements.txt
```

Set the LOLA DEM path environment variable (required for `analyze_site.py`, `scripts/build_datapack.py`, and DEM regression tests):

```powershell
$env:LUNAR_DEM_PATH = "D:\path\to\LDEM_80S_20MPP_ADJ.tiff"
```

Run single-site analysis on Windows PowerShell:

```powershell
# Analyze site at lat -86.0 deg, lon 2.0 deg for 30 days
python analyze_site.py -86 2 --start 2027-01-01 --days 30 --height 2.0 --step 900
```

CLI arguments:
- `lat`: Site latitude in degrees (negative for South Pole, e.g. `-86.0`)
- `lon`: Site longitude in degrees east (e.g. `2.0`)
- `--start`: UTC start date (default: `2027-01-01`)
- `--days`: Duration in days (default: `30`)
- `--height`: Observer height above ground in metres (default: `2.0`, supports `1.0`, `5.0`)
- `--step`: Time step in seconds (default: `900.0`)
- `--dem`: Path to LOLA DEM TIFF (defaults to `$env:LUNAR_DEM_PATH`)
- `--json`: Custom output JSON path (default: `site_lat{lat}_lon{lon}.json`)
- `--png`: Custom output PNG path (default: `site_panorama.png`)

To rebuild the precomputed web data pack under `web/data/` (optional; prebuilt data is already included):

```powershell
python scripts/build_datapack.py --spacing 1000
```

## Tests

### Python (`pytest`)

Run **without** the LOLA DEM (DEM-dependent tests skip cleanly; unit, SPICE ephemeris, data-pack validation/refusal, and fixture tests all run):

```powershell
Remove-Item Env:LUNAR_DEM_PATH -ErrorAction SilentlyContinue
pytest -v
```

Run **with** the LOLA DEM (executes the full suite including DEM horizon regression and packed-vs-fresh horizon checks):

```powershell
$env:LUNAR_DEM_PATH = "D:\path\to\LDEM_80S_20MPP_ADJ.tiff"
pytest -v
```

Run only the engine regression tests (requires `LUNAR_DEM_PATH`):

```powershell
pytest -v -k "test_regression"
```

### JavaScript / Web App

1. **Browser test page**: Serve the repo root with `python -m http.server 8000` and open `http://localhost:8000/web/tests.html`. It runs JS unit checks and compares all 12 cases in `tests/fixtures/reference.json` against the JS engine.
2. **Node.js test runner** (Node 18+):

```powershell
node tests/test_web.mjs
```

Both verify JS outputs against Python SPICE/LOLA packed-horizon fixtures within: illumination `±0.005`, percentages `±0.5`, longest run hours `±1 step`, sample visible fractions `±0.002`, and azimuth/elevation `±0.01°`.

## Data sources

- **NASA LOLA via PGDA**: `LDEM_80S_20MPP_ADJ.tiff` (Lunar Reconnaissance Orbiter Lunar Orbiter Laser Altimeter 20 m/px South Polar stereographic digital elevation model from NASA Planetary Geodesy Data Archive, referenced to a 1,737,400 m lunar sphere).
- **NAIF SPICE**: Official NASA Navigation and Ancillary Information Facility kernels under `kernels/` (`de440.bsp` planetary/lunar ephemeris, `moon_pa_de440_200625.bpc` lunar orientation binary PCK, `naif0012.tls` leap seconds, and `moon_de440_220930.tf` defining the Moon Mean Earth/Polar Axis `MOON_ME` reference frame).

## Limitations

- **Local near-field terrain sensitivity (~100 m baseline)**: Terrain within ~100 m of the observer strongly controls positive horizon angles at 1 m or 5 m observer heights. Sub-20 m features (rocks, boulders, micro-craters) are not resolved in the 20 m DEM, and moving 10–20 m on steep crater rims can shift horizon cutoffs by several degrees.
- **1-degree azimuthal discretization**: Terrain horizons are sampled at 360 integer-degree azimuths and linearly interpolated; spires or notches narrower than 1° may be smoothed.
- **0.01-degree packed horizon storage**: Horizons in `web/data/horizons.bin` are stored as `int16` in `0.01 deg` steps; this changes a single moment's visible fraction by up to ~0.01 at the Sun's edge and period metrics by `< 0.001`.
- **Geometric ephemeris (no light-time or aberration correction)**: NAIF SPICE `'LT+S'` directions differ from the geometric vectors used here by about `0.006 deg` for the Sun and `0.0002 deg` for Earth, far below the `0.53 deg` solar disc diameter and the `0.01 deg` horizon precision.
- **Approximate region boundaries**: Candidate region centres and radii are approximate positions intended for planning and trade studies rather than formal spacecraft landing hazard certification.
- **Geometric Earth visibility**: Earth visibility metrics report geometric line of sight to Earth's disc, not a full RF/optical communications link budget.
- **Map dot colour-map window**: To keep the browser responsive on large regions and long timelines, the Site Picker dot colour overlay (`Sun illumination`, `Earth visible (any part)`, `Earth more than half visible`) uses a time step of at least 3600 s and a window capped at 90 days, while Period Summary Metrics, Panorama, and Timeline Strips always evaluate the full selected duration at 900 s resolution.

## License

Apache-2.0
