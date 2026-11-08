# Lunar Landing Site Navigator (`lunar_engine`)

A modular Python package developed for NASA Space Apps 2026 to analyze lunar south-pole landing sites. For any given site, `lunar_engine` computes:
1. **Terrain Horizon**: 360-degree horizon profile using high-resolution LOLA 20 m DEM (`LDEM_80S_20MPP_ADJ.tiff`) with regional downsampled caching.
2. **SPICE Ephemeris**: Apparent topocentric azimuth, elevation, and distance-derived angular radii for both the Sun and Earth over time in the `MOON_ME` frame (Earth's angular radius is about 0.90-1.02 deg depending on the Earth-Moon distance).
3. **Visibility & Illumination**: Visible fraction of the solar and terrestrial discs obscured by local terrain, average illumination, and longest communication blackout periods.

## Project Structure

```text
├── lunar_engine/
│   ├── __init__.py        # Package exports
│   ├── config.py          # Paths, environment variables, physical constants
│   ├── geometry.py        # Forward/inverse polar stereographic projection and frames
│   ├── horizon.py         # 360-degree terrain horizon from LOLA DEM
│   ├── ephemeris.py       # SPICE kernel handling, positions, and angular radii
│   └── visibility.py      # Disc visible fraction, summary metrics, panorama plots
├── analyze_site.py        # CLI for analyzing lunar landing sites
├── tests/                 # pytest test suite
├── kernels/               # SPICE kernels (TLS, BSP, BPC, TF)
├── legacy/                # Original scripts preserved
├── requirements.txt       # Dependencies (numpy, scipy, rasterio, spiceypy, matplotlib, pytest)
├── LICENSE                # Apache-2.0
└── docs/ai_log.md         # AI engineering log
```

## Installation & Requirements

Python 3.10+ with the following packages:
```powershell
pip install -r requirements.txt
```

Set the LOLA DEM path environment variable (optional if passed via `--dem`):
```powershell
$env:LUNAR_DEM_PATH = "D:\path\to\LDEM_80S_20MPP_ADJ.tiff"
```

## CLI Usage

Run `analyze_site.py` on Windows PowerShell:
```powershell
# Analyze site at lat -86.0 deg, lon 2.0 deg for 30 days
python analyze_site.py -86 2 --start 2027-01-01 --days 30 --height 2.0 --step 900
```

### CLI Arguments
- `lat`: Site latitude in degrees (negative for South Pole, e.g. `-86.0`)
- `lon`: Site longitude in degrees east (e.g. `2.0`)
- `--start`: UTC start date (default: `2027-01-01`)
- `--days`: Duration in days (default: `30`)
- `--height`: Observer height above ground in metres (default: `2.0`, supports `1.0`, `5.0`)
- `--step`: Time step in seconds (default: `900.0`)
- `--dem`: Path to LOLA DEM TIFF (defaults to `$env:LUNAR_DEM_PATH`)
- `--json`: Custom output JSON path (default: `site_lat{lat}_lon{lon}.json`)
- `--png`: Custom output PNG path (default: `site_panorama.png`)

Outputs:
- Printed summary metrics to stdout
- JSON file containing all computed metrics and run configuration
- PNG panorama visualization plotting terrain horizon and celestial tracks

## Running Tests

Run all unit tests:
```powershell
pytest -v
```

Run regression tests against the LOLA DEM:
```powershell
$env:LUNAR_DEM_PATH = "D:\path\to\LDEM_80S_20MPP_ADJ.tiff"
pytest -v -k "test_regression"
```

## License

Apache-2.0
