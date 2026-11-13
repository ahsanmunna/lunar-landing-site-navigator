# Lunar Landing Site Navigator

**NASA International Space Apps Challenge 2026 - Lunar Landing Site Navigator**

Built on NASA Lunar Orbiter Laser Altimeter (LOLA) 20 m South Polar topography and official NAIF SPICE ephemeris kernels, Lunar Landing Site Navigator computes 360-degree terrain horizons, solar illumination availability, and geometric Earth line-of-sight visibility across candidate lunar South Pole landing sites for 2027–2029. It is designed for mission planners, planetary scientists, engineers, students, and educators comparing local power, communications, and terrain trade-offs without installing specialized astrodynamics software. A Python analysis engine precomputes compact regional horizon and Moon-centred ephemeris data packs that a dependency-free static web application explores interactively in the browser.

**Live demo:** https://github.com/ahsanmunna/lunar-landing-site-navigator

## What you can do

In the browser explorer (`web/index.html`), you can:

- **Candidate region (`Candidate region`)**: Switch across the 9 precomputed Artemis III candidate landing regions (`web/data/manifest.json`). The full data pack (manifest.json, horizons.bin, ephem.bin; about 12 MB) loads once at start; each region's hillshade image loads on demand.
- **Observer height (`Observer height`)**: Toggle observer height above local ground between `1 m` and `5 m`.
- **Start date & duration (`Start date (UTC)`, `Duration`)**: Choose any UTC start date within the 2027–2029 ephemeris range and evaluate `7 days`, `14 days`, `30 days`, `90 days`, or `365 days (1 year)` windows at 15-minute (900 s) steps.
- **Map colour metric (`Map colour metric`)**: Colour the clickable stereographic terrain hillshade grid by `Sun illumination`, `Earth visible (any part)`, or `Earth more than half visible` (computed over at most the first 90 days at 1 h steps; summary cards use the full selected period at 15 min steps), click any grid dot or `Centre` to reset, and read coordinates, ground height, ~100 m local slope, and horizon min/max.
- **Select-highest buttons**: Jump directly to grid extremes with `Select brightest site` or `Select site with most Earth view` (explicitly marked in the UI as a quick selection helper, not a recommendation).
- **Panorama with Sun and Earth discs (`Horizon Panorama`)**: Inspect the 360° terrain horizon profile (0° = outward-radial north, clockwise) with horizon-clipped Sun and Earth discs at the active instant, using `Full 360°`, `Zoom Sun (1:1)`, or `Zoom Earth (1:1)` view modes.
- **Time slider & timeline strips**: Scrub through the window with the time slider, `‹` / `›` step buttons, `Play` / `Pause` playback, or clickable/draggable `Sun visible fraction` and `Earth visible fraction (dashed line = 50% threshold)` strips while reading instantaneous Sun/Earth visible disc percentages, azimuth, elevation, and angular radius.
- **Six metric cards (`Period Summary Metrics`)**: Inspect full-period 15-minute metrics for the selected grid site:
  1. `Illumination availability` — Average fraction of the solar disc visible over the selected period.
  2. `Sun visible (any part)` — Share of time when at least part of the Sun rises above terrain.
  3. `Longest continuous darkness` — Longest unbroken stretch with zero direct sunlight.
  4. `Geometric Earth visibility (any part of the disc)` — Share of time when any part of Earth has line of sight above terrain (geometric line of sight, not a radio link budget).
  5. `Earth more than half visible` — Share of time when over half of Earth's disc clears the horizon.
  6. `Longest Earth-visibility blackout` — Longest unbroken period with zero geometric line of sight to Earth.
- **Comparison of up to 3 configurations (`Site Comparison (up to 3 configurations)`)**: Save configurations with `Add to comparison` and inspect up to 3 side-by-side across region, grid site ID, coordinates, observer height, UTC date window, and all six metrics (with inline bars, `Remove`, and `Clear all`), without an overall score or single "best" ranking.

## How it works

1. **Stereographic site grid:** Each candidate zone is sampled on a regular stereographic X/Y grid (clipped to region radius) over the 20 m LOLA DEM, recording ground elevation and 100 m-baseline slope.
2. **360° terrain horizons:** For each grid point and observer height (1 m / 5 m), rays at 1° azimuth steps (0° = outward-radial north, clockwise) march across near-field (20 m) and regional (160 m) LOLA terrain with lunar curvature to record maximum horizon angles.
3. **Moon-centred ephemeris:** NAIF SPICE geometric position vectors (km, `MOON_ME` frame) for the Sun and Earth are precomputed every 900 s (15 min) across 2027–2029.
4. **Topocentric projection:** In your browser, site latitude, longitude, ground height, and observer height form a local East-North-Up frame; subtracting the site vector from each body vector yields azimuth, elevation, and angular radius `asin(R / distance)`.
5. **Partial-disc visibility:** At each step, the terrain horizon is linearly interpolated (periodic at 360°) at the body's azimuth, giving normalized height `t = (el - horizon) / r_ang` and spherical-cap disc visibility fraction.
6. **Mission summary metrics:** Averaging and consecutive-step run lengths over the chosen date window yield solar illumination availability, Sun/Earth visibility percentages, and longest continuous darkness or blackout spans.

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
├── kernels/                    # NAIF SPICE kernels (.tls and .tf kernels are in the repo; de440.bsp and moon_pa_de440_200625.bpc are NOT: too large, download them)
├── tests/                      # pytest suite, Node web test runner (test_web.mjs), reference fixtures
├── docs/                       # Validation report, data sources, format spec, frontend guide, AI log
├── analyze_site.py             # Single-site Python CLI
├── requirements.txt            # Python dependencies
└── LICENSE                     # Apache-2.0
```

## Get the data (Python side only)

The web app needs none of these.

```powershell
Invoke-WebRequest https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp -OutFile kernels\de440.bsp
Invoke-WebRequest https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc -OutFile kernels\moon_pa_de440_200625.bpc
Invoke-WebRequest https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls -OutFile kernels\naif0012.tls
Invoke-WebRequest https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/a_old_versions/moon_de440_220930.tf -OutFile kernels\moon_de440_220930.tf
Invoke-WebRequest https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF -OutFile LDEM_80S_20MPP_ADJ.TIF
$env:LUNAR_DEM_PATH = "LDEM_80S_20MPP_ADJ.TIF"
```

The DEM is at https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF (about 2.6 GB; set LUNAR_DEM_PATH).

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

Requires tested with Python 3.13.7 (and tested with Node v24.18.0 if running the CLI JS test runner):

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
2. **Node.js test runner** (tested with Node v24.18.0):

```powershell
node tests/test_web.mjs
```

Both verify JS outputs against Python SPICE/LOLA packed-horizon fixtures within: illumination `±0.005`, percentages `±0.5`, longest run hours `±1 step`, sample visible fractions `±0.002`, and azimuth/elevation `±0.01°`. See [docs/validation.md](docs/validation.md) for the full validation table and known unvalidated boundaries.

## Data sources

- **NASA LOLA via PGDA**: `LDEM_80S_20MPP_ADJ.tiff` (Lunar Reconnaissance Orbiter Lunar Orbiter Laser Altimeter 20 m/px South Polar stereographic digital elevation model from NASA Planetary Geodesy Data Archive, referenced to a 1,737,400 m lunar sphere).
- **NAIF SPICE**: Official NASA Navigation and Ancillary Information Facility kernels under `kernels/` (`de440.bsp` planetary/lunar ephemeris, `moon_pa_de440_200625.bpc` lunar orientation binary PCK, `naif0012.tls` leap seconds, and `moon_de440_220930.tf` defining the Moon Mean Earth/Polar Axis `MOON_ME` reference frame).

See [docs/data_sources.md](docs/data_sources.md) for the full inventory of datasets, software packages, and licences.

## Limitations

- **Local near-field terrain sensitivity (~100 m baseline)**: Terrain within ~100 m of the observer strongly controls positive horizon angles at 1 m or 5 m observer heights. Sub-20 m features (rocks, boulders, micro-craters) are not resolved in the 20 m DEM, and moving 10–20 m on steep crater rims can shift horizon cutoffs by several degrees.
- **1-degree azimuthal discretization**: Terrain horizons are sampled at 360 integer-degree azimuths and linearly interpolated; spires or notches narrower than 1° may be smoothed.
- **0.01-degree packed horizon storage**: Horizons in `web/data/horizons.bin` are stored as `int16` in `0.01 deg` steps; this changes a single moment's visible fraction by up to ~0.01 at the Sun's edge and period metrics by `< 0.001`.
- **Geometric ephemeris (no light-time or aberration correction)**: NAIF SPICE `'LT+S'` directions differ from the geometric vectors used here by about `0.006 deg` for the Sun and `0.0002 deg` for Earth, far below the `0.53 deg` solar disc diameter and the `0.01 deg` horizon precision.
- **Approximate region boundaries**: Candidate region centres and radii are approximate positions intended for planning and trade studies rather than formal spacecraft landing hazard certification.
- **Geometric Earth visibility**: Earth visibility metrics report geometric line of sight to Earth's disc, not a full RF/optical communications link budget.
- **Map dot colour-map window**: To keep the browser responsive on large regions and long timelines, the Site Picker dot colour overlay (`Sun illumination`, `Earth visible (any part)`, `Earth more than half visible`) uses a time step of at least 3600 s and a window capped at 90 days, while Period Summary Metrics, Panorama, and Timeline Strips always evaluate the full selected duration at 900 s resolution.

## Region positions

Region centres were picked with scripts/pick_regions.py from box positions measured on an annotated screenshot of NASA's Artemis III candidate-region map; they are approximate. An earlier AI-generated set of coordinates was discarded.

## Use of AI

AI tools were used in this project: Google Antigravity (code generation) and Claude by Anthropic (technical supervision and code review). Antigravity wrote the Python engine, the data-pack builder, the region picker, the web app and documentation drafts from written task briefs. Claude wrote the briefs, reviewed code and reports, ran independent checks and flagged errors. Every Antigravity prompt is recorded verbatim, with a summary of changes, in docs/ai_log.md. A fuller account (what each tool did, the data they worked on, human verification steps and AI mistakes that were caught and corrected) is in docs/ai_use.md. The project owner chose the challenge, placed the region centres with the picker, ran every test and rebuild, and made the final decisions.

## Credits

- **NASA LOLA via PGDA**: Lunar Reconnaissance Orbiter Lunar Orbiter Laser Altimeter 20 m/px South Polar Digital Elevation Model (`LDEM_80S_20MPP_ADJ.tiff`) distributed via NASA Goddard's Planetary Geodesy Data Archive (PGDA). Citation: Barker, M. K., et al., 2023, Planetary Science Journal, 4, 183, https://doi.org/10.3847/PSJ/acf3e1 ; data DOI 10.60903/gsfcpgda-lola-spole ; product page https://pgda.gsfc.nasa.gov/products/90
- **NAIF SPICE**: NASA Navigation and Ancillary Information Facility (NAIF) SPICE kernels (`de440.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_220930.tf`, `naif0012.tls`) defining planetary ephemerides, lunar orientation, leap seconds, and the `MOON_ME` frame.

## License

Apache-2.0
