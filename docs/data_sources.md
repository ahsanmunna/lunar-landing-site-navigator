# Data Sources & Software Dependencies

This document lists every external dataset, SPICE kernel, and software dependency used by Lunar Landing Site Navigator, together with project file locations, roles, distribution sources, and licences verified in this environment.

> Official download URLs are provided below for the LOLA DEM and NAIF SPICE kernels. Python dependencies and external tools reference their respective package repositories or provider documentation.

## Datasets & SPICE Kernels

| Name | Provider / Source | Project Files | What It Is Used For | Where to Get It | Licence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LOLA 20 m South Polar DEM** (`LDEM_80S_20MPP_ADJ.tiff`) | NASA Goddard Space Flight Center / Planetary Geodesy Data Archive (PGDA), Lunar Reconnaissance Orbiter LOLA | Referenced externally via `LUNAR_DEM_PATH` / `--dem` by `lunar_engine/config.py`, `lunar_engine/horizon.py`, `scripts/build_datapack.py`, `analyze_site.py`, `tests/test_datapack.py`, `tests/test_regression.py` | Provides 20 m/px polar stereographic lunar South Pole terrain elevations (referenced to a `1,737,400 m` lunar sphere) for ground heights, ~100 m slopes, 20 m near-field + 160 m regional horizon ray-marching (`web/data/horizons.bin`), and hillshade backdrops (`web/data/regions/*.png`). | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF | NASA data; cite Barker et al. 2023 as requested on the PGDA product page (https://pgda.gsfc.nasa.gov/products/90) |
| **NAIF SPICE Planetary & Lunar Ephemeris** (`de440.bsp`) | NASA Navigation and Ancillary Information Facility (NAIF), JPL | `kernels/de440.bsp`; loaded by `lunar_engine/ephemeris.py`, `scripts/build_datapack.py`, `tests/test_datapack.py`, `tests/test_ephemeris.py`, `analyze_site.py` | Supplies Moon-centred Sun and Earth geometric position vectors (km), precomputed at 900 s steps across 2027–2029 in `web/data/ephem.bin` and verified in unit/datapack tests. | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp | NASA NAIF public data (no separate licence file bundled in `kernels/`) |
| **NAIF SPICE Lunar Orientation Binary PCK** (`moon_pa_de440_200625.bpc`) | NASA NAIF, JPL | `kernels/moon_pa_de440_200625.bpc`; loaded by `lunar_engine/ephemeris.py` and test suite | Provides lunar principal-axis body orientation angles across ephemeris epochs. | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc | NASA NAIF public data (no separate licence file bundled in `kernels/`) |
| **NAIF SPICE Lunar Reference Frame Kernel** (`moon_de440_220930.tf`) | NASA NAIF, JPL | `kernels/moon_de440_220930.tf`; loaded by `lunar_engine/ephemeris.py` and test suite | Defines the Moon Mean Earth / Polar Axis (`MOON_ME`) reference frame relative to the binary PCK principal-axis frame. | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/a_old_versions/moon_de440_220930.tf | NASA NAIF public data (no separate licence file bundled in `kernels/`) |
| **NAIF SPICE Leap Seconds Kernel** (`naif0012.tls`) | NASA NAIF, JPL | `kernels/naif0012.tls`; loaded by `lunar_engine/ephemeris.py` and test suite | Converts UTC timestamp strings (`str2et`) into Ephemeris Time (ET) seconds past J2000. | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls | NASA NAIF public data (no separate licence file bundled in `kernels/`) |
| **NASA Artemis III Candidate-Region Map** | NASA Artemis III candidate-region map (exact image file not stored in this repo) | `data_src/region_names.json`, `data_src/regions.json` (built via `scripts/pick_regions.py`, consumed by `scripts/build_datapack.py` -> `web/data/manifest.json`) | Supplies approximate centres (km / lat-lon) and radii (9–29 km) for the 9 South Pole candidate regions. | NASA release (exact image file not stored in this repo; picked JSON included in `data_src/regions.json`) | Public domain NASA map / `Apache-2.0` (`LICENSE`, for repository-authored JSON files) |

---

## Software Dependencies

Python package versions and licence strings below were read directly via `importlib.metadata` and `pip show` in the active Python `3.13.7` environment (not inferred from memory). Only standard-library modules plus the six packages listed in `requirements.txt` are imported across `lunar_engine/`, `scripts/`, `analyze_site.py`, and `tests/`.

| Name | Provider | Project Files | What It Is Used For | Where to Get It | Licence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`numpy`** (`2.5.1`) | NumPy Developers (PyPI) | `requirements.txt`, `analyze_site.py`, `lunar_engine/*.py`, `scripts/*.py`, `tests/*.py` | Polar stereographic math, elevation/ray arrays, binary `int16`/`float32` packing, ephemeris vector transforms, and visibility metrics. | see provider site | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` (`License-Expression` via `importlib.metadata` / `pip show`) |
| **`scipy`** (`1.17.1`) | SciPy Developers (PyPI) | `requirements.txt`, `lunar_engine/horizon.py`, `scripts/build_datapack.py` | Imports `scipy.ndimage.map_coordinates` for interpolated terrain elevation sampling along near-field and regional horizon rays. | see provider site | `BSD` (`Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers.` / `License :: OSI Approved :: BSD License`; bundled wheel also declares OpenBLAS `BSD-3-Clause` and LAPACK `BSD-3-Clause-Open-MPI` via `importlib.metadata`) |
| **`rasterio`** (`1.5.2`) | Rasterio Contributors / Mapbox (PyPI) | `requirements.txt`, `lunar_engine/horizon.py`, `scripts/build_datapack.py`, `tests/test_datapack.py` | Windowed GeoTIFF reading and resampling of `LDEM_80S_20MPP_ADJ.tiff` (plus synthetic GeoTIFF generation in datapack tests). | see provider site | `BSD-3-Clause` (`License-Expression` via `importlib.metadata` / `pip show`) |
| **`spiceypy`** (`8.3.0`) | Andrew Annex / SpiceyPy Contributors (PyPI wrapper for NASA NAIF CSPICE) | `requirements.txt`, `lunar_engine/ephemeris.py`, `scripts/build_datapack.py`, `tests/test_datapack.py` | Python bindings to NAIF CSPICE (`furnsh`, `str2et`, `spkpos`, `subpnt`, `subslr`, `reclat`) for ephemeris generation and validation. | see provider site | `MIT` (`License-Expression` via `importlib.metadata` / `pip show`) |
| **`matplotlib`** (`3.10.8`) | Matplotlib Development Team (PyPI) | `requirements.txt`, `lunar_engine/visibility.py`, `scripts/build_datapack.py`, `scripts/pick_regions.py`, `tests/test_datapack.py`, `tests/test_pick_regions.py` | Renders horizon panorama PNGs (`visibility.py` / `analyze_site.py`), greyscale hillshade backdrops (`LightSource` in `build_datapack.py`), interactive region picking (`pick_regions.py`), and PNG verification in tests. | see provider site | `License agreement for matplotlib versions 1.3.0 and later` / Classifier `License :: OSI Approved :: Python Software Foundation License` (`importlib.metadata` / `pip show`) |
| **`pytest`** (`9.1.1`) | pytest-dev team (PyPI) | `requirements.txt`, `tests/test_*.py` | Executes the Python unit, ephemeris, datapack integrity, region-picker, and DEM regression test suite. | see provider site | `MIT` (`License-Expression` via `importlib.metadata` / `pip show`) |
| **Python** (`3.10+` required; `3.13.7` tested) + Stdlib | Python Software Foundation | All Python modules under `lunar_engine/`, `scripts/`, `analyze_site.py`, `tests/`, plus `python -m http.server 8000` | Runtime interpreter, `argparse`, `concurrent.futures`, `json`, `math`, `os`, `pathlib`, `struct`, `sys`, `time`, and local static HTTP server. | see provider site | see provider site (`LICENSE.txt` present in `sys.base_prefix` of local Python `3.13.7` install) |
| **Node.js** (`18+` required; `v24.18.0` tested) | OpenJS Foundation / Node.js Contributors | `tests/test_web.mjs` | Optional CLI test runner verifying ES modules under `web/js/` against `tests/fixtures/reference.json`. Not required to serve or use the web UI. | see provider site | see provider site |

---

## Third-Party JavaScript / External Web Resources (`web/`)

**The web app uses zero third-party JavaScript and zero external CSS, fonts, or CDN resources.**

Verification via recursive search across `web/` (`*.html`, `*.js`, `*.css`) matching `<script`, `<link`, `@import`, `http(s)://`, and `url(` found only:
- Local asset references in `web/index.html` and `web/tests.html`:
  - `<link rel="icon" href="data:,">`
  - `<link rel="stylesheet" href="css/style.css">`
  - `<script type="module" src="js/main.js"></script>` (plus inline `<script>` / `<script type="module">` blocks inside the repo's own HTML files)
- One informational repository hyperlink anchor (`<a href="https://github.com/ahsanmunna/lunar-landing-site-navigator"...>`) in the footer of `web/index.html`
- Localhost helper strings (`http://localhost:8000/...`) inside UI hints and error messages (`web/index.html`, `web/tests.html`, `web/js/data.js`).

All application logic (`web/js/data.js`, `geometry.js`, `visibility.js`, `metrics.js`, `panorama.js`, `charts.js`, `compare.js`, `main.js`) is vanilla ES modules authored inside this repository.
