"""Command-line interface to analyze lunar landing sites.

Computes terrain horizon profile, Sun/Earth ephemeris tracks, illumination fraction,
and Earth direct line-of-sight communication visibility. Prints summary metrics,
writes JSON metrics, and produces a horizon panorama PNG plot.
"""

import argparse
import json
from pathlib import Path
import sys

from lunar_engine.config import (
    DEFAULT_STEP_S,
    DEFAULT_OBSERVER_HEIGHT_M,
    DEFAULT_START,
    DEFAULT_DAYS,
    get_dem_path,
)
from lunar_engine.horizon import compute_horizon
from lunar_engine.ephemeris import sun_earth_azel
from lunar_engine.visibility import summarize, plot_panorama


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lunar Landing Site Navigator: compute terrain horizon and Sun/Earth visibility.",
    )
    parser.add_argument("lat", type=float, help="Latitude in degrees (negative for South Pole, e.g. -86.0)")
    parser.add_argument("lon", type=float, help="Longitude in degrees east (e.g. 2.0)")
    parser.add_argument("--start", default=DEFAULT_START, help=f"UTC start date/time (default: {DEFAULT_START})")
    parser.add_argument("--days", type=float, default=DEFAULT_DAYS, help=f"Duration in days (default: {DEFAULT_DAYS})")
    parser.add_argument(
        "--height",
        type=float,
        default=DEFAULT_OBSERVER_HEIGHT_M,
        help=f"Observer height above ground in metres (e.g. 1.0, 2.0, 5.0; default: {DEFAULT_OBSERVER_HEIGHT_M})",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=DEFAULT_STEP_S,
        help=f"Time step in seconds (default: {DEFAULT_STEP_S})",
    )
    parser.add_argument(
        "--dem",
        default=None,
        help="Path to LOLA DEM TIFF (defaults to LUNAR_DEM_PATH environment variable)",
    )
    parser.add_argument(
        "--json",
        default=None,
        help="Path for output JSON file (default: site_lat{lat}_lon{lon}.json)",
    )
    parser.add_argument(
        "--png",
        default="site_panorama.png",
        help="Path for output PNG panorama (default: site_panorama.png)",
    )

    args = parser.parse_args()

    # Verify DEM availability
    dem_file = get_dem_path(args.dem)
    if dem_file is None or not dem_file.exists():
        print(
            f"Error: LOLA DEM not found. Set LUNAR_DEM_PATH environment variable or pass --dem <path>.",
            file=sys.stderr,
        )
        return 1

    print(f"Computing horizon for lat {args.lat}, lon {args.lon} (observer height {args.height} m)...", flush=True)
    hor, ground_height_m = compute_horizon(
        lat=args.lat,
        lon=args.lon,
        observer_height_m=args.height,
        dem_path=dem_file,
    )

    print(f"Computing Sun and Earth ephemeris tracks (start {args.start}, {args.days} days, step {args.step} s)...", flush=True)
    ephem = sun_earth_azel(
        lat=args.lat,
        lon=args.lon,
        ground_height_m=ground_height_m,
        observer_height_m=args.height,
        start=args.start,
        days=args.days,
        step_s=args.step,
    )

    metrics = summarize(
        hor=hor,
        ground_height_m=ground_height_m,
        sun=ephem.sun,
        sun_r=ephem.sun_r,
        earth=ephem.earth,
        earth_r=ephem.earth_r,
        lat=args.lat,
        lon=args.lon,
        start=args.start,
        days=args.days,
        observer_height_m=args.height,
        step_s=args.step,
    )

    # Print human-readable summary
    print(f"Site lat {args.lat}, lon {args.lon}; ground height {ground_height_m:.0f} m; "
          f"{args.start} for {args.days} days (step: {args.step:.0f}s)")
    print(f"Horizon elevation: min {metrics['horizon_min']:.2f}, max {metrics['horizon_max']:.2f} deg")
    print(f"Sun:   average visible fraction {metrics['illumination_avg_fraction']:.2f}; "
          f"any sun {metrics['sun_any_pct']:.0f}%; "
          f"longest total darkness {metrics['sun_longest_dark_h']:.1f} h")
    print(f"Earth: mostly visible {metrics['earth_mostly_pct']:.0f}%; "
          f"any part visible {metrics['earth_any_pct']:.0f}%; "
          f"longest no-contact gap {metrics['earth_longest_blackout_h']:.1f} h")

    # Save JSON metrics
    json_path = Path(args.json) if args.json else Path(f"site_lat{args.lat}_lon{args.lon}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"saved {json_path}")

    # Render and save PNG
    png_path = plot_panorama(
        hor=hor,
        sun=ephem.sun,
        earth=ephem.earth,
        lat=args.lat,
        lon=args.lon,
        start=args.start,
        days=args.days,
        output_path=args.png,
    )
    print(f"saved {png_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
