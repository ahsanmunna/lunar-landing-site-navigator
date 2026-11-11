"""Precompute the static web data pack for lunar landing site navigation.

Implements TASK 2B:
- Step 1: Stereographic grid point generation, clipped to region circles, with slope & ground height
- Step 2: 360-ray terrain horizon computation for heights [1 m, 5 m] with multiprocessing & checkpoints
- Step 3: Moon-centred SPICE position vectors for SUN and EARTH (every 900s, 2027-2029)
- Step 4: Web data pack files (manifest.json, horizons.bin, ephem.bin, regions/<id>.png hillshades)
- Step 6: tests/fixtures/reference.json with 12 validation cases for future JavaScript port
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LightSource
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy.ndimage import map_coordinates
import spiceypy as spice

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lunar_engine.config import (
    MOON_RADIUS_M,
    SUN_RADIUS_KM,
    EARTH_RADIUS_KM,
    get_dem_path,
    get_kernel_dir,
)
from lunar_engine.ephemeris import (
    load_kernels,
    create_time_grid,
    get_moon_centered_positions,
    angular_radius_deg,
    sun_earth_azel,
)
from lunar_engine.geometry import forward, inverse, site_local_frame, site_position_km
from lunar_engine.horizon import compute_horizon
from lunar_engine.visibility import summarize, visible_fraction
from scripts.datapack_worker import compute_point_horizons

MAX_DATAPACK_MB: float = 20.0


def validate_regions(regions: List[Dict]) -> None:
    """Validate candidate regions list.

    Refuses to run if:
    - region list is empty
    - any region's 'source' field starts with 'placeholder' or is empty/missing
    - any region lacks 'picked_by' and/or 'picked_utc' (missing, None, or empty)
    """
    if not regions:
        raise ValueError("Region list is empty. Refusing to run.")

    for idx, reg in enumerate(regions):
        reg_id = reg.get("id", f"index-{idx}")
        source = reg.get("source")
        if source is None or not str(source).strip():
            raise ValueError(
                f"Region '{reg_id}' has an empty 'source' field. Refusing to run."
            )
        clean_source = str(source).strip()
        if clean_source.lower().startswith("placeholder"):
            raise ValueError(
                f"Region '{reg_id}' has placeholder source ('{clean_source}'). Refusing to run."
            )

        picked_by = reg.get("picked_by")
        picked_utc = reg.get("picked_utc")
        has_picked_by = picked_by is not None and bool(str(picked_by).strip())
        has_picked_utc = picked_utc is not None and bool(str(picked_utc).strip())

        if not has_picked_by and not has_picked_utc:
            raise ValueError(
                f"Region '{reg_id}' lacks 'picked_by' and 'picked_utc'. Refusing to run."
            )
        if not has_picked_by:
            raise ValueError(
                f"Region '{reg_id}' lacks 'picked_by'. Refusing to run."
            )
        if not has_picked_utc:
            raise ValueError(
                f"Region '{reg_id}' lacks 'picked_utc'. Refusing to run."
            )


def generate_grid_points(
    regions: List[Dict],
    dem_path: Path,
    spacing_m: float = 1000.0,
    slope_baseline_m: float = 100.0,
) -> Tuple[List[Dict], List[Dict]]:
    """Generate stereographic grid points for each region, sample elevation and slope.

    Parameters
    ----------
    regions : list of dict
        Region definitions from data_src/regions.json.
    dem_path : Path
        Path to LOLA 20 m DEM TIFF.
    spacing_m : float
        Regular grid spacing in stereographic metres (default 1000.0).
    slope_baseline_m : float
        Baseline in metres for finite difference slope calculation (default 100.0).

    Returns
    -------
    points : list of dict
        List of valid point metadata dictionaries.
    regions_with_extent : list of dict
        List of region dictionaries augmented with extent and image paths.
    """
    print(f"\n[Step 1] Generating grid points with spacing = {spacing_m:.1f} m...")
    validate_regions(regions)

    points = []
    regions_out = []
    point_index = 0

    half_base = slope_baseline_m / 2.0  # 50 m offset each side

    with rasterio.open(dem_path) as src:
        # Edge limit: 80S model edge is at rho ~ 304,000 m. Drop points within 5 km (299,000 m).
        edge_limit_m = 304000.0 - 5000.0

        for reg in regions:
            reg_id = reg["id"]
            cx = float(reg["center_x_m"])
            cy = float(reg["center_y_m"])
            radius_m = float(reg["radius_km"]) * 1000.0

            # Image extent for web UI
            extent = {
                "x_min": round(cx - radius_m, 2),
                "x_max": round(cx + radius_m, 2),
                "y_min": round(cy - radius_m, 2),
                "y_max": round(cy + radius_m, 2),
            }

            reg_copy = dict(reg)
            reg_copy["extent"] = extent
            reg_copy["image"] = f"regions/{reg_id}.png"
            regions_out.append(reg_copy)

            # Read regional DEM window for fast elevation and slope sampling
            pad_m = radius_m + 200.0
            win = Window(
                int((cx - pad_m - src.transform.c) / src.transform.a),
                int((cy + pad_m - src.transform.f) / src.transform.e),
                int(2 * pad_m / 20.0),
                int(2 * pad_m / 20.0),
            )
            zn = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")
            tn = src.window_transform(win)

            def get_elevation(x: float, y: float) -> float:
                col = (x - tn.c) / tn.a - 0.5
                row = (y - tn.f) / tn.e - 0.5
                return float(map_coordinates(zn, [[row], [col]], order=1, output=np.float64)[0])

            # Generate candidate offsets around center
            offsets = np.arange(-radius_m, radius_m + 0.1, spacing_m)

            # Ensure centre point (0, 0) is processed first
            candidate_offsets = [(0.0, 0.0)]
            for dy in offsets:
                for dx in offsets:
                    if abs(dx) < 1e-5 and abs(dy) < 1e-5:
                        continue  # Centre already added
                    if dx**2 + dy**2 <= (radius_m**2 + 1e-5):
                        candidate_offsets.append((float(dx), float(dy)))

            reg_point_count = 0
            for dx, dy in candidate_offsets:
                x = cx + dx
                y = cy + dy

                # Check edge distance (must be > 5 km inside 80S model edge)
                rho = np.hypot(x, y)
                if abs(x) >= edge_limit_m or abs(y) >= edge_limit_m or rho >= edge_limit_m:
                    continue

                # Ground elevation
                h_ground = get_elevation(x, y)
                if np.isnan(h_ground):
                    continue

                # Slope over ~100 m baseline (+-50 m)
                h_x_plus = get_elevation(x + half_base, y)
                h_x_minus = get_elevation(x - half_base, y)
                h_y_plus = get_elevation(x, y + half_base)
                h_y_minus = get_elevation(x, y - half_base)

                if (
                    np.isnan(h_x_plus)
                    or np.isnan(h_x_minus)
                    or np.isnan(h_y_plus)
                    or np.isnan(h_y_minus)
                ):
                    continue

                dz_dx = (h_x_plus - h_x_minus) / slope_baseline_m
                dz_dy = (h_y_plus - h_y_minus) / slope_baseline_m
                slope_deg = float(np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))))

                # Assign point ID: <region>-c for centre, <region>-p001 etc for others
                if abs(dx) < 1e-5 and abs(dy) < 1e-5:
                    pt_id = f"{reg_id}-c"
                else:
                    reg_point_count += 1
                    pt_id = f"{reg_id}-p{reg_point_count:03d}"

                lat, lon = inverse(x, y)

                pt_record = {
                    "id": pt_id,
                    "region": reg_id,
                    "x_m": round(x, 2),
                    "y_m": round(y, 2),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "ground_height_m": round(h_ground, 2),
                    "slope_deg": round(slope_deg, 2),
                    "index": point_index,
                }
                points.append(pt_record)
                point_index += 1

            total_for_reg = reg_point_count + 1
            print(f"  Region '{reg_id}': {total_for_reg} points (center: {reg_id}-c)")

    print(f"Total valid grid points generated across all regions: {len(points)}")
    return points, regions_out


def compute_checkpoint_hash(points: List[Dict], heights: List[float]) -> str:
    """Compute a deterministic SHA-256 hash of point IDs, x/y, ground heights, and observer heights."""
    hasher = hashlib.sha256()
    heights_repr = [float(h) for h in heights]
    hasher.update(json.dumps(heights_repr).encode("utf-8"))

    pts_repr = [
        (
            str(pt["id"]),
            float(pt["x_m"]),
            float(pt["y_m"]),
            float(pt["ground_height_m"]),
        )
        for pt in points
    ]
    hasher.update(json.dumps(pts_repr).encode("utf-8"))
    return hasher.hexdigest()


def load_or_create_checkpoint(
    checkpoint_file: Path,
    shape: Tuple[int, int, int],
    points: List[Dict],
    heights: List[float],
) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Load an existing checkpoint if valid and hash matches; otherwise start fresh.

    Returns
    -------
    horizons_data : np.ndarray
        Array of shape [n_points, n_heights, 360], int16.
    completed : np.ndarray
        Boolean array of length n_points.
    resumed : bool
        True if loaded from valid matching checkpoint, False if started fresh.
    """
    n_points, n_heights, _ = shape
    expected_hash = compute_checkpoint_hash(points, heights)

    if not checkpoint_file.exists():
        return (
            np.full(shape, -32768, dtype=np.int16),
            np.zeros(n_points, dtype=bool),
            False,
        )

    try:
        ckpt = np.load(checkpoint_file)
        saved_hash = None
        if "config_hash" in ckpt.files:
            saved_hash = str(ckpt["config_hash"])
        elif "checkpoint_hash" in ckpt.files:
            saved_hash = str(ckpt["checkpoint_hash"])

        if saved_hash != expected_hash:
            print(
                f"  WARNING: Checkpoint hash mismatch (checkpoint: {saved_hash}, current: {expected_hash}). "
                f"Ignoring checkpoint and starting fresh."
            )
            return (
                np.full(shape, -32768, dtype=np.int16),
                np.zeros(n_points, dtype=bool),
                False,
            )

        horizons_data = ckpt["horizons"]
        completed = ckpt["completed"]
        if horizons_data.shape != shape or len(completed) != n_points:
            print(
                f"  WARNING: Checkpoint shape mismatch (expected {shape}, got {horizons_data.shape}). "
                f"Ignoring checkpoint and starting fresh."
            )
            return (
                np.full(shape, -32768, dtype=np.int16),
                np.zeros(n_points, dtype=bool),
                False,
            )

        n_done = int(np.sum(completed))
        print(
            f"  Resuming from checkpoint: {n_done}/{n_points} points "
            f"({n_done / n_points * 100:.1f}%) already completed."
        )
        return horizons_data, completed, True

    except Exception as e:
        print(f"  WARNING: Could not load checkpoint ({e}). Ignoring checkpoint and starting fresh.")
        return (
            np.full(shape, -32768, dtype=np.int16),
            np.zeros(n_points, dtype=bool),
            False,
        )


def precompute_horizons(
    points: List[Dict],
    heights: List[float],
    checkpoint_file: Path,
    output_bin: Path,
    num_workers: int = 8,
    chunk_size: int = 50,
) -> np.ndarray:
    """Precompute 360-ray horizons for all points and heights with checkpointing.

    Format: [n_points][n_heights][360] int16 (value = round(deg * 100), -32768 = nodata).
    """
    n_points = len(points)
    n_heights = len(heights)
    shape = (n_points, n_heights, 360)
    expected_hash = compute_checkpoint_hash(points, heights)

    print(f"\n[Step 2] Precomputing horizons for {n_points} points x {n_heights} heights ({n_points * n_heights} profiles)...")
    print(f"  Checkpoint path: {checkpoint_file}")
    print(f"  Checkpoint hash: {expected_hash}")
    print(f"  Worker processes: {num_workers}")

    # Check for existing checkpoint
    horizons_data, completed, resumed = load_or_create_checkpoint(
        checkpoint_file, shape, points, heights
    )

    # Gather remaining work
    pending_tasks = []
    for pt in points:
        idx = pt["index"]
        if not completed[idx]:
            pending_tasks.append((idx, pt["lat"], pt["lon"], heights))

    if not pending_tasks:
        print("  All points already computed from checkpoint!")
    else:
        print(f"  Computing remaining {len(pending_tasks)} points using {num_workers} parallel workers...")
        t_start = time.perf_counter()
        completed_since_start = 0
        total_to_do = len(pending_tasks)

        # Process in chunks with checkpoint persistence
        for chunk_start in range(0, total_to_do, chunk_size):
            chunk = pending_tasks[chunk_start : chunk_start + chunk_size]
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = {executor.submit(compute_point_horizons, task): task[0] for task in chunk}
                for fut in as_completed(futures):
                    idx, hor_stack = fut.result()
                    horizons_data[idx] = hor_stack
                    completed[idx] = True
                    completed_since_start += 1

            # Save checkpoint after each chunk
            np.savez_compressed(
                checkpoint_file,
                horizons=horizons_data,
                completed=completed,
                config_hash=expected_hash,
            )

            elapsed = time.perf_counter() - t_start
            rate = completed_since_start / elapsed if elapsed > 0 else 0.0
            remaining_pts = total_to_do - completed_since_start
            eta_sec = remaining_pts / rate if rate > 0 else 0.0
            total_done = int(np.sum(completed))
            print(
                f"  Progress: [{total_done:4d}/{n_points}] ({total_done / n_points * 100:5.1f}%) | "
                f"Elapsed: {elapsed:.1f} s | ETA: {eta_sec:.1f} s"
            )

    # Write little-endian binary file
    output_bin.parent.mkdir(parents=True, exist_ok=True)
    horizons_data.astype("<i2").tofile(output_bin)
    print(f"  Wrote horizons to: {output_bin} ({output_bin.stat().st_size:,} bytes)")
    return horizons_data


def precompute_ephemeris(
    start_utc: str = "2027-01-01T00:00:00",
    end_utc: str = "2029-01-01T00:00:00",
    step_s: float = 900.0,
    output_bin: Path = Path("web/data/ephem.bin"),
) -> Tuple[np.ndarray, np.ndarray]:
    """Precompute Moon-centred position vectors of Sun and Earth in MOON_ME frame.

    Layout: [n_times][body: 0=SUN, 1=EARTH][x, y, z] float32 km (little-endian).
    """
    print(f"\n[Step 3] Precomputing SPICE ephemeris from {start_utc} to {end_utc} every {step_s:.0f} s...")
    load_kernels()

    et0 = spice.str2et(start_utc)
    et1 = spice.str2et(end_utc)
    ets = np.arange(et0, et1, step_s, dtype=np.float64)
    n_times = len(ets)

    print(f"  Total time samples: {n_times}")
    print(f"  First time: {spice.et2utc(ets[0], 'ISOC', 0)}")
    print(f"  Last time:  {spice.et2utc(ets[-1], 'ISOC', 0)}")

    t0 = time.perf_counter()
    sun_pos = get_moon_centered_positions("SUN", ets)
    earth_pos = get_moon_centered_positions("EARTH", ets)
    dt = time.perf_counter() - t0
    print(f"  Computed {n_times} Moon-centred SPICE vectors in {dt:.2f} s")

    ephem_arr = np.empty((n_times, 2, 3), dtype="<f4")
    ephem_arr[:, 0, :] = sun_pos.astype("<f4")
    ephem_arr[:, 1, :] = earth_pos.astype("<f4")

    output_bin.parent.mkdir(parents=True, exist_ok=True)
    ephem_arr.tofile(output_bin)
    print(f"  Wrote ephemeris to: {output_bin} ({output_bin.stat().st_size:,} bytes)")
    return ets, ephem_arr


def generate_region_hillshades(
    regions: List[Dict],
    dem_path: Path,
    output_dir: Path,
    target_res_m: float = 40.0,
) -> None:
    """Render hillshade PNG of each region at res = max(40, 2*radius_m/800) m/px, 2*radius_km wide."""
    print(f"\n[Step 4a] Rendering hillshade images for {len(regions)} regions (res = max({target_res_m:.0f}, 2*radius_m/800) m/px)...")
    output_dir.mkdir(parents=True, exist_ok=True)

    ls = LightSource(azdeg=315, altdeg=45)

    with rasterio.open(dem_path) as src:
        for reg in regions:
            reg_id = reg["id"]
            cx = float(reg["center_x_m"])
            cy = float(reg["center_y_m"])
            rad = float(reg["radius_km"]) * 1000.0
            res = max(float(target_res_m), (2.0 * rad) / 800.0)

            # Window of width 2 * radius
            win = Window(
                int((cx - rad - src.transform.c) / src.transform.a),
                int((cy + rad - src.transform.f) / src.transform.e),
                int(2 * rad / 20.0),
                int(2 * rad / 20.0),
            )

            # Target shape at adaptive resolution res m/px (max 800x800 px)
            px_size = max(1, int(round((2.0 * rad) / res)))
            z = src.read(
                1,
                window=win,
                out_shape=(px_size, px_size),
                resampling=Resampling.bilinear,
                boundless=True,
                fill_value=np.nan,
            ).astype("float32")

            # Fill any NaN with median
            if np.isnan(z).any():
                z = np.nan_to_num(z, nan=float(np.nanmedian(z)))

            shade = ls.hillshade(z, vert_exag=3.0, dx=res, dy=res)

            img_path = output_dir / f"{reg_id}.png"
            plt.imsave(img_path, shade, cmap="gray")
            print(f"  Rendered {img_path.name:25s} ({shade.shape[1]}x{shade.shape[0]} px @ {res:.1f} m/px, {img_path.stat().st_size:,} bytes)")


def select_darkest_and_brightest_points(
    points: List[Dict],
    horizons_data: np.ndarray,
    observer_heights: Optional[List[float]] = None,
    start: str = "2027-01-01",
    days: float = 30.0,
    step_s: float = 3600.0,
    target_height_m: float = 1.0,
) -> Tuple[Tuple[str, float], Tuple[str, float]]:
    """Compute illumination_avg_fraction from packed horizons and return darkest and brightest points.

    Returns ((darkest_id, darkest_illum), (brightest_id, brightest_illum)).
    """
    heights = list(observer_heights) if observer_heights is not None else [1.0, 5.0]
    if target_height_m not in heights:
        raise ValueError(f"Observer height {target_height_m} m not found in {heights}")
    h_idx = heights.index(target_height_m)

    ets = create_time_grid(start, days=days, step_s=step_s)
    sun_pos = get_moon_centered_positions("SUN", ets)

    scored: List[Tuple[float, int, str]] = []
    for pt in points:
        idx = int(pt["index"])
        raw_hor = horizons_data[idx, h_idx, :]
        if np.any(raw_hor == -32768):
            continue
        hor_deg = raw_hor.astype(np.float64) / 100.0
        lat = float(pt["lat"])
        lon = float(pt["lon"])
        gh = float(pt["ground_height_m"])

        up, e3, n3 = site_local_frame(lat, lon)
        r_site = site_position_km(lat, lon, gh, observer_height_m=target_height_m)
        v = sun_pos - r_site[None, :]
        dist = np.linalg.norm(v, axis=1)
        v_unit = v / dist[:, None]
        az = np.degrees(np.arctan2(v_unit @ e3, v_unit @ n3)) % 360.0
        el = np.degrees(np.arcsin(np.clip(v_unit @ up, -1.0, 1.0)))
        sun_r = angular_radius_deg(SUN_RADIUS_KM, dist)
        sv = visible_fraction(np.column_stack((az, el)), sun_r, hor_deg)
        illum = float(np.mean(sv))
        scored.append((illum, idx, pt["id"]))

    if not scored:
        raise ValueError("No valid horizon profiles found in packed horizons.")

    dark_illum, _, darkest_id = min(scored, key=lambda x: (x[0], x[1]))
    bright_pool = [r for r in scored if r[2] != darkest_id] if len(scored) > 1 else scored
    bright_illum, _, brightest_id = max(bright_pool, key=lambda x: (x[0], -x[1]))
    return (darkest_id, dark_illum), (brightest_id, bright_illum)


def generate_reference_fixtures(
    points: List[Dict],
    output_json: Path,
    horizons_data: Optional[np.ndarray] = None,
    observer_heights: Optional[List[float]] = None,
    horizons_bin: Optional[Path] = None,
) -> None:
    """Generate tests/fixtures/reference.json with 12 validation cases for JS port."""
    print(f"\n[Step 6] Generating reference test fixtures with 12 cases...")
    output_json.parent.mkdir(parents=True, exist_ok=True)

    heights = list(observer_heights) if observer_heights is not None else [1.0, 5.0]
    if horizons_data is None:
        horizons_path = Path(horizons_bin) if horizons_bin is not None else Path("web/data/horizons.bin")
        if not horizons_path.exists():
            raise ValueError(f"horizons_data must be provided or {horizons_path} must exist.")
        horizons_data = np.fromfile(horizons_path, dtype="<i2").reshape((len(points), len(heights), 360))

    # Point index lookup by id
    pt_map = {p["id"]: p for p in points}

    # Select darkest and brightest points from packed horizons (1 m, 30 d from 2027-01-01, step 3600)
    (darkest_id, darkest_illum), (brightest_id, brightest_illum) = select_darkest_and_brightest_points(
        points=points,
        horizons_data=horizons_data,
        observer_heights=heights,
        start="2027-01-01",
        days=30.0,
        step_s=3600.0,
        target_height_m=1.0,
    )
    print(
        f"  Darkest point (1 m, 30 d from 2027-01-01, step 3600 s):   "
        f"{darkest_id} (illumination_avg_fraction={darkest_illum:.4f})"
    )
    print(
        f"  Brightest point (1 m, 30 d from 2027-01-01, step 3600 s): "
        f"{brightest_id} (illumination_avg_fraction={brightest_illum:.4f})"
    )

    # Target 12 cases: keep Malapert centre + darkest/brightest points + remaining region centres
    candidate_specs = [
        # Malapert Massif centre (1 m and 5 m)
        ("malapert-massif-c", 1.0, "2027-01-01", 30, 900.0),
        ("malapert-massif-c", 5.0, "2027-01-01", 30, 900.0),
        # Darkest and brightest points of the pack (1 m)
        (darkest_id, 1.0, "2027-01-01", 30, 900.0),
        (brightest_id, 1.0, "2027-01-01", 30, 900.0),
        # Peak near Cabeus B centre (1 m and 5 m)
        ("peak-near-cabeus-b-c", 1.0, "2027-01-01", 30, 900.0),
        ("peak-near-cabeus-b-c", 5.0, "2027-01-01", 30, 900.0),
        # Mons Mouton centre (1 m and 5 m)
        ("mons-mouton-c", 1.0, "2027-01-01", 30, 900.0),
        ("mons-mouton-c", 5.0, "2027-01-01", 30, 900.0),
        # Nobile Rim 1 centre (1 m and 5 m)
        ("nobile-rim-1-c", 1.0, "2027-01-01", 30, 900.0),
        ("nobile-rim-1-c", 5.0, "2027-01-01", 30, 900.0),
        # de Gerlache Rim 2 centre (1 m)
        ("de-gerlache-rim-2-c", 1.0, "2027-01-01", 30, 900.0),
        # Slater Plain centre (5 m)
        ("slater-plain-c", 5.0, "2027-01-01", 30, 900.0),
        # Fallbacks to maintain 12 distinct cases if darkest/brightest overlaps a centre above
        ("de-gerlache-rim-2-c", 5.0, "2027-01-01", 30, 900.0),
        ("slater-plain-c", 1.0, "2027-01-01", 30, 900.0),
        ("mons-mouton-plateau-c", 1.0, "2027-01-01", 30, 900.0),
        ("mons-mouton-plateau-c", 5.0, "2027-01-01", 30, 900.0),
        ("nobile-rim-2-c", 1.0, "2027-01-01", 30, 900.0),
        ("nobile-rim-2-c", 5.0, "2027-01-01", 30, 900.0),
        ("haworth-c", 1.0, "2027-01-01", 30, 900.0),
        ("haworth-c", 5.0, "2027-01-01", 30, 900.0),
    ]

    case_specs: List[Tuple[str, float, str, int, float]] = []
    seen_cases = set()
    for spec in candidate_specs:
        key = (spec[0], spec[1])
        if spec[0] in pt_map and key not in seen_cases:
            case_specs.append(spec)
            seen_cases.add(key)
            if len(case_specs) == 12:
                break

    if len(case_specs) < 12:
        for pt in points:
            for h in heights:
                key = (pt["id"], float(h))
                if key not in seen_cases:
                    case_specs.append((pt["id"], float(h), "2027-01-01", 30, 900.0))
                    seen_cases.add(key)
                    if len(case_specs) == 12:
                        break
            if len(case_specs) == 12:
                break

    print(
        f"  Chosen fixture case IDs ({len(case_specs)}): "
        + ", ".join(f"{pid} ({h:.0f} m)" for pid, h, *_ in case_specs)
    )

    height_lookup = [float(val) for val in heights]
    fixture_cases = []
    for pt_id, h, start, days, step_s in case_specs:
        pt = pt_map[pt_id]
        pt_idx = int(pt["index"])
        h_idx = height_lookup.index(float(h))
        lat = float(pt["lat"])
        lon = float(pt["lon"])
        gh = float(pt["ground_height_m"])

        raw_hor = np.asarray(horizons_data[pt_idx, h_idx, :], dtype=np.int16)
        if np.any(raw_hor == -32768):
            raise ValueError(f"Packed horizon contains nodata (-32768) for {pt_id} @ {h:.1f} m.")
        hor = raw_hor.astype(np.float64) / 100.0

        ephem = sun_earth_azel(
            lat=lat,
            lon=lon,
            ground_height_m=gh,
            observer_height_m=h,
            start=start,
            days=days,
            step_s=step_s,
        )

        metrics = summarize(
            hor=hor,
            ground_height_m=gh,
            sun=ephem.sun,
            sun_r=ephem.sun_r,
            earth=ephem.earth,
            earth_r=ephem.earth_r,
            lat=lat,
            lon=lon,
            start=start,
            days=days,
            observer_height_m=h,
            step_s=step_s,
        )

        sv = visible_fraction(ephem.sun, ephem.sun_r, hor)
        ev = visible_fraction(ephem.earth, ephem.earth_r, hor)

        # 20 sample times across the run
        sample_indices = np.linspace(0, len(ephem.ets) - 1, 20, dtype=int)
        sample_times = []
        for s_idx in sample_indices:
            et = ephem.ets[s_idx]
            sample_times.append({
                "index": int(s_idx),
                "time_utc": spice.et2utc(et, "ISOC", 0),
                "sun_az_deg": round(float(ephem.sun[s_idx, 0]), 4),
                "sun_el_deg": round(float(ephem.sun[s_idx, 1]), 4),
                "earth_az_deg": round(float(ephem.earth[s_idx, 0]), 4),
                "earth_el_deg": round(float(ephem.earth[s_idx, 1]), 4),
                "sun_visible_fraction": round(float(sv[s_idx]), 6),
                "earth_visible_fraction": round(float(ev[s_idx]), 6),
            })

        fixture_cases.append({
            "point_id": pt_id,
            "observer_height_m": float(h),
            "start": str(start),
            "days": float(days),
            "step_s": float(step_s),
            "horizon_source": "packed int16",
            "summary": metrics,
            "sample_times": sample_times,
        })
        print(f"  Fixture generated: {pt_id} @ {h:.1f} m (illumination: {metrics['illumination_avg_fraction']:.4f})")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(fixture_cases, f, indent=2)
    print(f"Wrote reference fixtures to: {output_json} ({output_json.stat().st_size:,} bytes)")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for build_datapack.py."""
    parser = argparse.ArgumentParser(
        description="Precompute static web data pack for lunar landing site navigation."
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=1000.0,
        help="Stereographic grid spacing in metres (default: 1000.0).",
    )
    if argv is None:
        if sys.argv and "pytest" in sys.argv[0].lower():
            argv = []
        else:
            argv = sys.argv[1:]
    args = parser.parse_args(argv)
    if args.spacing <= 0:
        parser.error("--spacing must be positive.")
    return args


def main(argv: Optional[List[str]] = None):
    args = parse_args(argv)

    print("=" * 70)
    print("LUNAR DATA PACK PRECOMPUTATION (TASK 2B)")
    print("=" * 70)

    dem_path = get_dem_path()
    if dem_path is None or not dem_path.exists():
        print("ERROR: LOLA DEM not found. Please set LUNAR_DEM_PATH.")
        sys.exit(1)

    regions_json = Path("data_src/regions.json")
    if not regions_json.exists():
        print(f"ERROR: {regions_json} not found.")
        sys.exit(1)

    with open(regions_json, "r", encoding="utf-8") as f:
        regions = json.load(f)

    try:
        validate_regions(regions)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    web_data_dir = Path("web/data")
    web_data_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = Path("data_src/horizons_checkpoint.npz")
    output_horizons = web_data_dir / "horizons.bin"
    output_ephem = web_data_dir / "ephem.bin"
    output_manifest = web_data_dir / "manifest.json"
    regions_img_dir = web_data_dir / "regions"
    fixtures_file = Path("tests/fixtures/reference.json")

    # Step 1: Grid points
    grid_spacing_m = float(args.spacing)
    observer_heights = [1.0, 5.0]
    points, regions_with_extent = generate_grid_points(regions, dem_path, spacing_m=grid_spacing_m)

    # Step 2: Horizons
    num_cpus = os.cpu_count() or 4
    workers = max(1, min(num_cpus - 1, 8))
    horizons_data = precompute_horizons(
        points=points,
        heights=observer_heights,
        checkpoint_file=checkpoint_file,
        output_bin=output_horizons,
        num_workers=workers,
    )

    # Step 3: Ephemeris
    ets, ephem_arr = precompute_ephemeris(
        start_utc="2027-01-01T00:00:00",
        end_utc="2029-01-01T00:00:00",
        step_s=900.0,
        output_bin=output_ephem,
    )

    # Step 4a: Hillshade images
    generate_region_hillshades(regions_with_extent, dem_path, regions_img_dir, target_res_m=40.0)

    # Step 4b: Manifest
    created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "version": "1.0.0",
        "created_utc": created_utc,
        "constants": {
            "moon_radius_m": int(MOON_RADIUS_M),
            "sun_radius_km": int(SUN_RADIUS_KM),
            "earth_radius_km": int(EARTH_RADIUS_KM),
            "horizon_az_step_deg": 1,
            "azimuth_convention": "clockwise from outward-radial north",
        },
        "observer_heights_m": observer_heights,
        "ephemeris": {
            "file": "ephem.bin",
            "start_utc": "2027-01-01T00:00:00Z",
            "step_s": 900,
            "n_times": len(ets),
            "frame": "MOON_ME",
            "layout": "[n_times][body: 0=SUN,1=EARTH][x,y,z] float32 km",
        },
        "horizons": {
            "file": "horizons.bin",
            "layout": "[n_points][n_heights][360] int16, value = round(deg*100), -32768 = no data",
            "scale": 0.01,
            "nodata": -32768,
        },
        "grid_spacing_m": int(grid_spacing_m) if grid_spacing_m.is_integer() else grid_spacing_m,
        "regions": regions_with_extent,
        "points": points,
        "sources": [
            "LOLA LDEM_80S_20MPP_ADJ",
            "NAIF de440",
            "moon_pa_de440",
            "naif0012",
            "MOON_ME frame kernel",
        ],
    }

    with open(output_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n[Step 4b] Wrote manifest to: {output_manifest} ({output_manifest.stat().st_size:,} bytes)")

    # Step 6: Reference fixtures (decode directly from the horizons.bin written in Step 2)
    generate_reference_fixtures(
        points,
        fixtures_file,
        observer_heights=observer_heights,
        horizons_bin=output_horizons,
    )

    # Size verification
    print("\n" + "=" * 70)
    print("DATA PACK SIZES UNDER web/data/:")
    print("=" * 70)
    total_size = 0
    for p in web_data_dir.rglob("*"):
        if p.is_file():
            sz = p.stat().st_size
            total_size += sz
            rel_path = p.relative_to(web_data_dir)
            print(f"  {str(rel_path):35s}: {sz:>10,d} bytes ({sz / (1024*1024):>6.2f} MB)")

    total_mb = total_size / (1024 * 1024)
    print("-" * 70)
    print(f"  TOTAL web/data SIZE: {total_size:,} bytes ({total_mb:.2f} MB)")
    print(f"  Size under {MAX_DATAPACK_MB:.0f} MB limit: {'PASSED' if total_mb < MAX_DATAPACK_MB else 'FAILED'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
