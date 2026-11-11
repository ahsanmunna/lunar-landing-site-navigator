"""Tests for the precomputed web data pack (Task 2B / 2C / 2D / 2E).

Verifies:
a) File sizes match the manifest layout exactly and total data pack is under 20 MB;
b) 5 random points: horizon in horizons.bin equals a fresh engine computation within 0.011 deg;
c) 3 random times: ephem.bin vectors equal direct spiceypy spkpos within 1e-3 km;
d) No point lies outside its region circle.
"""

import copy
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
import spiceypy as spice

from lunar_engine.config import get_dem_path
from lunar_engine.ephemeris import load_kernels
from lunar_engine.horizon import compute_horizon
from scripts.build_datapack import (
    MAX_DATAPACK_MB,
    compute_checkpoint_hash,
    load_or_create_checkpoint,
    precompute_horizons,
    validate_regions,
    generate_grid_points,
    generate_region_hillshades,
    select_darkest_and_brightest_points,
    generate_reference_fixtures,
    parse_args as build_datapack_parse_args,
    main as build_datapack_main,
)
from scripts.pick_regions import DEFAULT_SOURCE_TAG

WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
MANIFEST_PATH = WEB_DATA_DIR / "manifest.json"
HORIZONS_BIN = WEB_DATA_DIR / "horizons.bin"
EPHEM_BIN = WEB_DATA_DIR / "ephem.bin"
FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "reference.json"

dem_available = get_dem_path() is not None and get_dem_path().exists()


@pytest.fixture(scope="module")
def manifest():
    """Load and parse manifest.json."""
    assert MANIFEST_PATH.exists(), f"manifest.json not found at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_datapack_file_sizes_match_manifest_layout(manifest):
    """Test 5a: Verify file sizes match manifest layout exactly and total pack size < 20 MB."""
    points = manifest["points"]
    heights = manifest["observer_heights_m"]
    n_points = len(points)
    n_heights = len(heights)

    # 1. horizons.bin: [n_points][n_heights][360] int16 (2 bytes per value)
    expected_horizons_bytes = n_points * n_heights * 360 * 2
    assert HORIZONS_BIN.exists(), f"horizons.bin not found at {HORIZONS_BIN}"
    actual_horizons_bytes = HORIZONS_BIN.stat().st_size
    assert actual_horizons_bytes == expected_horizons_bytes, (
        f"horizons.bin size mismatch: expected {expected_horizons_bytes} bytes, got {actual_horizons_bytes}"
    )

    # 2. ephem.bin: [n_times][body: 0=SUN, 1=EARTH][x, y, z] float32 km (4 bytes per value)
    ephem_meta = manifest["ephemeris"]
    n_times = ephem_meta["n_times"]
    expected_ephem_bytes = n_times * 2 * 3 * 4
    assert EPHEM_BIN.exists(), f"ephem.bin not found at {EPHEM_BIN}"
    actual_ephem_bytes = EPHEM_BIN.stat().st_size
    assert actual_ephem_bytes == expected_ephem_bytes, (
        f"ephem.bin size mismatch: expected {expected_ephem_bytes} bytes, got {actual_ephem_bytes}"
    )

    # 3. Region hillshade images exist and match extent
    for reg in manifest["regions"]:
        img_rel = reg["image"]
        img_path = WEB_DATA_DIR / img_rel
        assert img_path.exists(), f"Region image not found: {img_path}"
        assert img_path.stat().st_size > 1000, f"Region image suspiciously small: {img_path}"
        extent = reg["extent"]
        for key in ["x_min", "x_max", "y_min", "y_max"]:
            assert key in extent, f"Missing {key} in region extent for {reg['id']}"
        assert extent["x_max"] > extent["x_min"]
        assert extent["y_max"] > extent["y_min"]

    # 4. Total data pack size must be under 20 MB
    total_bytes = sum(f.stat().st_size for f in WEB_DATA_DIR.rglob("*") if f.is_file())
    max_bytes = int(MAX_DATAPACK_MB * 1024 * 1024)
    assert MAX_DATAPACK_MB == 20.0
    assert total_bytes < max_bytes, (
        f"Total web/data size ({total_bytes} bytes = {total_bytes / (1024*1024):.2f} MB) exceeds 20 MB limit"
    )


@pytest.mark.skipif(not dem_available, reason="LUNAR_DEM_PATH is unset or DEM file not found")
def test_horizons_match_fresh_engine_computation(manifest):
    """Test 5b: 5 random points: horizon in .bin equals fresh engine computation within 0.011 deg."""
    points = manifest["points"]
    heights = manifest["observer_heights_m"]
    n_points = len(points)
    n_heights = len(heights)

    # Load horizons binary array [n_points, n_heights, 360]
    horizons_data = np.fromfile(HORIZONS_BIN, dtype="<i2").reshape((n_points, n_heights, 360))

    # Pick 5 deterministic pseudo-random points across the dataset
    rng = np.random.default_rng(20261108)
    sample_indices = rng.choice(n_points, size=5, replace=False)

    for idx in sample_indices:
        pt = points[idx]
        lat, lon = pt["lat"], pt["lon"]
        pt_idx = pt["index"]
        assert pt_idx == idx

        for h_idx, h in enumerate(heights):
            bin_raw = horizons_data[pt_idx, h_idx, :]
            # Check nodata
            assert not np.any(bin_raw == -32768), f"Unexpected nodata in horizon for point {pt['id']} @ {h}m"
            bin_deg = bin_raw.astype(np.float64) / 100.0

            fresh_hor, fresh_gh = compute_horizon(lat, lon, observer_height_m=h)

            # Max absolute error must be within 0.011 deg
            max_err = float(np.max(np.abs(bin_deg - fresh_hor)))
            assert max_err <= 0.011, (
                f"Horizon mismatch at point {pt['id']} @ {h}m: max diff = {max_err:.5f} deg (> 0.011 deg)"
            )

            # Ground height consistency
            assert fresh_gh == pytest.approx(pt["ground_height_m"], abs=1.0)


def test_ephemeris_vectors_match_spice(manifest):
    """Test 5c: 3 random times: ephem.bin vectors equal direct spiceypy spkpos within 1e-3 km."""
    load_kernels()
    ephem_meta = manifest["ephemeris"]
    n_times = ephem_meta["n_times"]
    step_s = float(ephem_meta["step_s"])
    start_utc = ephem_meta["start_utc"]
    frame = ephem_meta["frame"]

    et0 = spice.str2et(start_utc)

    # Load ephem binary array [n_times, 2, 3] float32
    ephem_data = np.fromfile(EPHEM_BIN, dtype="<f4").reshape((n_times, 2, 3))

    rng = np.random.default_rng(20261108)
    sample_times_idx = rng.choice(n_times, size=3, replace=False)

    for t_idx in sample_times_idx:
        et = et0 + float(t_idx) * step_s

        # 0 = SUN, 1 = EARTH
        expected_sun_pos, _ = spice.spkpos("SUN", et, frame, "NONE", "MOON")
        expected_earth_pos, _ = spice.spkpos("EARTH", et, frame, "NONE", "MOON")

        bin_sun_pos = ephem_data[t_idx, 0, :]
        bin_earth_pos = ephem_data[t_idx, 1, :]

        # Compare against direct spiceypy spkpos in the file's target float32 precision
        expected_sun_f32 = np.array(expected_sun_pos, dtype="<f4")
        expected_earth_f32 = np.array(expected_earth_pos, dtype="<f4")

        sun_diff_km = float(np.linalg.norm(bin_sun_pos - expected_sun_f32))
        earth_diff_km = float(np.linalg.norm(bin_earth_pos - expected_earth_f32))

        assert sun_diff_km <= 1e-3, (
            f"Sun position mismatch at index {t_idx} (ET={et}): diff = {sun_diff_km:.6f} km (> 1e-3 km)"
        )
        assert earth_diff_km <= 1e-3, (
            f"Earth position mismatch at index {t_idx} (ET={et}): diff = {earth_diff_km:.6f} km (> 1e-3 km)"
        )


def test_no_point_outside_region_circle(manifest):
    """Test 5d: Verify no point lies outside its region circle, no NaNs, and > 5 km from model edge."""
    regions_map = {r["id"]: r for r in manifest["regions"]}
    edge_limit_m = 304000.0 - 5000.0  # 5 km inside 80S model edge

    for pt in manifest["points"]:
        reg_id = pt["region"]
        assert reg_id in regions_map, f"Unknown region '{reg_id}' for point '{pt['id']}'"
        reg = regions_map[reg_id]

        cx = float(reg["center_x_m"])
        cy = float(reg["center_y_m"])
        radius_m = float(reg["radius_km"]) * 1000.0

        x = float(pt["x_m"])
        y = float(pt["y_m"])
        dist_from_center = float(np.hypot(x - cx, y - cy))

        # Check distance from centre <= radius + margin
        assert dist_from_center <= radius_m + 1e-3, (
            f"Point {pt['id']} at ({x}, {y}) is {dist_from_center:.2f} m from centre, "
            f"exceeding radius {radius_m:.2f} m"
        )

        # Check not NaN
        assert not np.isnan(pt["ground_height_m"]), f"NaN ground_height_m at point {pt['id']}"
        assert not np.isnan(pt["slope_deg"]), f"NaN slope_deg at point {pt['id']}"
        assert pt["slope_deg"] >= 0.0, f"Negative slope at point {pt['id']}"

        # Check > 5 km from model edge
        rho = float(np.hypot(x, y))
        assert abs(x) < edge_limit_m, f"Point {pt['id']} x too close to model edge"
        assert abs(y) < edge_limit_m, f"Point {pt['id']} y too close to model edge"
        assert rho < edge_limit_m, f"Point {pt['id']} rho too close to 80S model edge"


def test_reference_fixtures():
    """Verify tests/fixtures/reference.json contains 12 cases including Malapert and dark/bright points."""
    assert FIXTURES_PATH.exists(), f"Fixtures file not found at {FIXTURES_PATH}"
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    assert len(fixtures) == 12, f"Expected 12 fixture cases, got {len(fixtures)}"

    point_ids = [c["point_id"] for c in fixtures]
    assert any("malapert" in pid and pid.endswith("-c") for pid in point_ids), (
        "Fixtures missing Malapert centre case"
    )
    illums = [c["summary"]["illumination_avg_fraction"] for c in fixtures]
    assert min(illums) <= 0.1, "Fixtures missing a low-illumination (dark) point"
    assert max(illums) >= 0.5, "Fixtures missing a high-illumination (bright) point"

    for case in fixtures:
        assert "point_id" in case
        assert "observer_height_m" in case
        assert case["observer_height_m"] in [1.0, 5.0]
        assert case.get("horizon_source") == "packed int16"
        assert "summary" in case
        summary = case["summary"]
        assert "illumination_avg_fraction" in summary
        assert "earth_any_pct" in summary
        assert "sample_times" in case
        assert len(case["sample_times"]) == 20
        for sample in case["sample_times"]:
            assert "sun_az_deg" in sample
            assert "sun_el_deg" in sample
            assert "earth_az_deg" in sample
            assert "earth_el_deg" in sample
            assert "sun_visible_fraction" in sample
            assert "earth_visible_fraction" in sample


def _mock_compute_point_horizons(task):
    idx, lat, lon, heights = task
    return idx, np.full((len(heights), 360), 42, dtype=np.int16)


def test_checkpoint_rejected_when_point_modified(tmp_path, capsys, monkeypatch):
    """Task 2C: key checkpoint to hash of all point ids, x/y, ground heights, and heights.
    Confirm old checkpoint is rejected when any point attribute is changed.
    """
    base_points = [
        {"id": "reg1-c", "region": "reg1", "lat": -85.0, "lon": 0.0, "x_m": 1000.0, "y_m": 2000.0, "ground_height_m": 500.0, "index": 0},
        {"id": "reg1-p001", "region": "reg1", "lat": -85.1, "lon": 0.1, "x_m": 1500.0, "y_m": 2500.0, "ground_height_m": 550.0, "index": 1},
    ]
    heights = [1.0, 5.0]
    shape = (len(base_points), len(heights), 360)
    expected_hash = compute_checkpoint_hash(base_points, heights)

    ckpt_file = tmp_path / "test_checkpoint.npz"

    # Save a valid checkpoint for base_points
    dummy_horizons = np.full(shape, 100, dtype=np.int16)
    dummy_completed = np.array([True, True], dtype=bool)
    np.savez_compressed(
        ckpt_file,
        horizons=dummy_horizons,
        completed=dummy_completed,
        config_hash=expected_hash,
    )

    # 1. Loading with unmodified points resumes cleanly
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, shape, base_points, heights)
    assert resumed is True
    assert np.all(completed)
    assert np.array_equal(horizons, dummy_horizons)

    # 2. Change ground_height_m on one point -> must reject old checkpoint
    pts_mod_h = copy.deepcopy(base_points)
    pts_mod_h[0]["ground_height_m"] += 1.0
    capsys.readouterr()  # clear buffer
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, shape, pts_mod_h, heights)
    captured = capsys.readouterr()
    assert resumed is False
    assert not np.any(completed)
    assert np.all(horizons == -32768)
    assert "WARNING: Checkpoint hash mismatch" in captured.out
    assert "Ignoring checkpoint and starting fresh." in captured.out

    # 3. Change x_m on one point -> must reject old checkpoint
    pts_mod_x = copy.deepcopy(base_points)
    pts_mod_x[1]["x_m"] += 50.0
    capsys.readouterr()
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, shape, pts_mod_x, heights)
    captured = capsys.readouterr()
    assert resumed is False
    assert not np.any(completed)
    assert "WARNING: Checkpoint hash mismatch" in captured.out

    # 4. Change y_m on one point -> must reject old checkpoint
    pts_mod_y = copy.deepcopy(base_points)
    pts_mod_y[0]["y_m"] -= 25.0
    capsys.readouterr()
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, shape, pts_mod_y, heights)
    captured = capsys.readouterr()
    assert resumed is False
    assert not np.any(completed)
    assert "WARNING: Checkpoint hash mismatch" in captured.out

    # 5. Change id on one point -> must reject old checkpoint
    pts_mod_id = copy.deepcopy(base_points)
    pts_mod_id[1]["id"] = "reg1-p999"
    capsys.readouterr()
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, shape, pts_mod_id, heights)
    captured = capsys.readouterr()
    assert resumed is False
    assert not np.any(completed)
    assert "WARNING: Checkpoint hash mismatch" in captured.out

    # 6. Change observer heights -> must reject old checkpoint
    capsys.readouterr()
    horizons, completed, resumed = load_or_create_checkpoint(ckpt_file, (2, 3, 360), base_points, [1.0, 2.0, 5.0])
    captured = capsys.readouterr()
    assert resumed is False
    assert not np.any(completed)
    assert "WARNING: Checkpoint hash mismatch" in captured.out

    # 7. End-to-end precompute_horizons with modified point recomputes fresh
    monkeypatch.setattr(
        "scripts.build_datapack.compute_point_horizons",
        _mock_compute_point_horizons,
    )
    out_bin = tmp_path / "out_horizons.bin"
    capsys.readouterr()
    result_horizons = precompute_horizons(
        points=pts_mod_h,
        heights=heights,
        checkpoint_file=ckpt_file,
        output_bin=out_bin,
        num_workers=1,
    )
    captured = capsys.readouterr()
    assert "WARNING: Checkpoint hash mismatch" in captured.out
    assert np.all(result_horizons == 42)


def test_build_datapack_refuses_placeholder_or_empty_source(tmp_path, capsys, monkeypatch):
    """Task 2C: build_datapack.py must refuse to run if any region's 'source' starts with 'placeholder' or is empty."""
    # 1. Empty or whitespace source
    empty_cases = [
        {"id": "reg1", "name": "Reg1", "source": ""},
        {"id": "reg2", "name": "Reg2", "source": "   "},
        {"id": "reg3", "name": "Reg3", "source": None},
        {"id": "reg4", "name": "Reg4"},  # missing 'source'
    ]
    for bad_reg in empty_cases:
        with pytest.raises(ValueError, match="empty 'source' field. Refusing to run."):
            validate_regions([bad_reg])

    # 2. Source starting with 'placeholder' (case-insensitive)
    placeholder_cases = [
        {"id": "reg1", "name": "Reg1", "source": "placeholder"},
        {"id": "reg2", "name": "Reg2", "source": "Placeholder: unconfirmed"},
        {"id": "reg3", "name": "Reg3", "source": "PLACEHOLDER_NASA_DATA"},
        {"id": "reg4", "name": "Reg4", "source": "  placeholder with leading spaces"},
    ]
    for bad_reg in placeholder_cases:
        with pytest.raises(ValueError, match="placeholder source .* Refusing to run."):
            validate_regions([bad_reg])

    # 3. Empty list of regions
    with pytest.raises(ValueError, match="Region list is empty. Refusing to run."):
        validate_regions([])

    # 4. Valid source with valid picked provenance passes
    valid_regions = [
        {
            "id": "haworth",
            "name": "Haworth",
            "source": DEFAULT_SOURCE_TAG,
            "picked_by": "pick_regions.py",
            "picked_utc": "2026-11-08T00:00:00Z",
        }
    ]
    validate_regions(valid_regions)  # does not raise

    # 5. Direct build_datapack_main refusal test
    with monkeypatch.context() as m:
        m.setattr(
            "json.load",
            lambda f: [{"id": "bad-site", "name": "Bad Site", "source": "placeholder"}],
        )
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc_info:
            build_datapack_main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ERROR: Region 'bad-site' has placeholder source" in captured.out

    # 6. Real data_src/regions.json must pass validate_regions (skip if picking incomplete)
    real_regions_file = Path("data_src/regions.json")
    assert real_regions_file.exists()
    real_regions = json.loads(real_regions_file.read_text(encoding="utf-8"))
    missing_picked = [
        r.get("id", r.get("name", f"index-{i}"))
        for i, r in enumerate(real_regions)
        if not (
            r.get("picked_by") is not None
            and str(r.get("picked_by")).strip()
            and r.get("picked_utc") is not None
            and str(r.get("picked_utc")).strip()
        )
    ]
    if missing_picked:
        pytest.skip(
            "data_src/regions.json has regions lacking picked_by or picked_utc "
            f"(picking not finished yet: {', '.join(missing_picked)})"
        )
    validate_regions(real_regions)


def test_build_datapack_refuses_missing_picked_provenance(capsys, monkeypatch):
    """Task 2D: build_datapack.py must refuse to run if any region lacks 'picked_by' and 'picked_utc'."""
    base_region = {
        "id": "haworth",
        "name": "Haworth",
        "source": DEFAULT_SOURCE_TAG,
        "center_x_m": -6968.95,
        "center_y_m": 77022.68,
        "center_lat": -87.45,
        "center_lon": -5.17,
        "ground_height_m": -3310.49,
        "radius_km": 4.0,
    }

    # 1. Lacks picked_by
    missing_picked_by_cases = [
        dict(base_region, picked_utc="2026-11-08T00:00:00Z"),  # key missing
        dict(base_region, picked_by="", picked_utc="2026-11-08T00:00:00Z"),
        dict(base_region, picked_by="   ", picked_utc="2026-11-08T00:00:00Z"),
        dict(base_region, picked_by=None, picked_utc="2026-11-08T00:00:00Z"),
    ]
    for bad_reg in missing_picked_by_cases:
        with pytest.raises(ValueError, match="lacks 'picked_by'"):
            validate_regions([bad_reg])

    # 2. Lacks picked_utc
    missing_picked_utc_cases = [
        dict(base_region, picked_by="pick_regions.py"),  # key missing
        dict(base_region, picked_by="pick_regions.py", picked_utc=""),
        dict(base_region, picked_by="pick_regions.py", picked_utc="   "),
        dict(base_region, picked_by="pick_regions.py", picked_utc=None),
    ]
    for bad_reg in missing_picked_utc_cases:
        with pytest.raises(ValueError, match="lacks 'picked_utc'"):
            validate_regions([bad_reg])

    # 3. Lacks both picked_by and picked_utc
    lacks_both = dict(base_region)
    with pytest.raises(ValueError, match="lacks 'picked_by' and 'picked_utc'"):
        validate_regions([lacks_both])

    # 4. Both present and non-empty -> passes
    valid_reg = dict(base_region, picked_by="pick_regions.py", picked_utc="2026-11-08T00:00:00Z")
    validate_regions([valid_reg])  # does not raise

    # 5. Direct build_datapack_main refusal tests
    # 5a. Region lacks picked_by -> main exits 1
    monkeypatch.setattr(
        "json.load",
        lambda f: [dict(base_region, picked_utc="2026-11-08T00:00:00Z")]
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc_info:
        build_datapack_main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: Region 'haworth' lacks 'picked_by'" in captured.out

    # 5b. Region lacks picked_utc -> main exits 1
    monkeypatch.setattr(
        "json.load",
        lambda f: [dict(base_region, picked_by="pick_regions.py")]
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc_info:
        build_datapack_main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: Region 'haworth' lacks 'picked_utc'" in captured.out


def test_build_datapack_spacing_cli_default_and_override():
    """Task 2E: --spacing defaults to 1000 m and accepts overrides."""
    default_args = build_datapack_parse_args([])
    assert default_args.spacing == 1000.0

    custom_args = build_datapack_parse_args(["--spacing", "500"])
    assert custom_args.spacing == 500.0

    with pytest.raises(SystemExit):
        build_datapack_parse_args(["--spacing", "0"])


def test_generate_region_hillshades_adaptive_resolution(tmp_path):
    """Task 2E: region hillshade size uses res = max(40, 2*radius_m/800) m/px."""
    import matplotlib.image as mpimg
    import rasterio
    from rasterio.transform import from_origin

    dem_file = tmp_path / "tiny_dem.tif"
    data = np.linspace(0.0, 500.0, 100 * 100, dtype=np.float32).reshape(100, 100)
    transform = from_origin(-1000.0, 1000.0, 20.0, 20.0)
    with rasterio.open(
        dem_file,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype="float32",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    regions = [
        {"id": "small-4km", "center_x_m": 0.0, "center_y_m": 0.0, "radius_km": 4.0},
        {"id": "edge-16km", "center_x_m": 0.0, "center_y_m": 0.0, "radius_km": 16.0},
        {"id": "large-29km", "center_x_m": 0.0, "center_y_m": 0.0, "radius_km": 29.0},
    ]
    out_dir = tmp_path / "regions"
    generate_region_hillshades(regions, dem_file, out_dir, target_res_m=40.0)

    # radius=4 km -> res = max(40, 8000/800)=40 -> 200x200 px
    img_small = mpimg.imread(out_dir / "small-4km.png")
    assert img_small.shape[:2] == (200, 200)

    # radius=16 km -> res = max(40, 32000/800)=40 -> 800x800 px
    img_edge = mpimg.imread(out_dir / "edge-16km.png")
    assert img_edge.shape[:2] == (800, 800)

    # radius=29 km -> res = max(40, 58000/800)=72.5 -> capped at 800x800 px
    img_large = mpimg.imread(out_dir / "large-29km.png")
    assert img_large.shape[:2] == (800, 800)


def test_select_darkest_brightest_and_generate_fixtures(tmp_path, capsys, monkeypatch):
    """Task 2E: generate_reference_fixtures keeps 12 cases, keeps malapert-massif-c,
    replaces shadowed-crater assumption with darkest & brightest from packed horizons, and prints IDs."""
    point_ids = [
        "malapert-massif-c",
        "peak-near-cabeus-b-c",
        "mons-mouton-c",
        "nobile-rim-1-c",
        "de-gerlache-rim-2-c",
        "slater-plain-c",
        "haworth-c",
        "haworth-p001",
        "mons-mouton-p001",
        "mons-mouton-plateau-c",
        "nobile-rim-2-c",
        "slater-plain-p001",
    ]
    points = [
        {
            "id": pid,
            "region": pid.rsplit("-", 1)[0],
            "x_m": 0.0,
            "y_m": 120000.0,
            "lat": -86.0,
            "lon": 0.0,
            "ground_height_m": 1000.0,
            "slope_deg": 1.0,
            "index": idx,
        }
        for idx, pid in enumerate(point_ids)
    ]

    # Default horizon +2.00 deg at 1 m & 5 m; malapert-massif-c +1.23 deg (1 m) / -0.45 deg (5 m);
    # haworth-p001 shadowed (+80.00 deg); mons-mouton-p001 brightest (-10.00 deg)
    horizons_data = np.full((len(points), 2, 360), 200, dtype=np.int16)
    mal_idx = point_ids.index("malapert-massif-c")
    horizons_data[mal_idx, 0, :] = 123
    horizons_data[mal_idx, 1, :] = -45
    dark_idx = point_ids.index("haworth-p001")
    bright_idx = point_ids.index("mons-mouton-p001")
    horizons_data[dark_idx, 0, :] = 8000
    horizons_data[bright_idx, 0, :] = -1000

    (dark_id, dark_illum), (bright_id, bright_illum) = select_darkest_and_brightest_points(
        points=points,
        horizons_data=horizons_data,
        observer_heights=[1.0, 5.0],
    )
    assert dark_id == "haworth-p001"
    assert bright_id == "mons-mouton-p001"
    assert dark_illum == 0.0
    assert bright_illum > dark_illum

    def _forbid_compute_horizon(*args, **kwargs):
        raise AssertionError("generate_reference_fixtures must decode packed horizons, not call compute_horizon")

    monkeypatch.setattr("scripts.build_datapack.compute_horizon", _forbid_compute_horizon)
    web_data_dir = tmp_path / "web" / "data"
    web_data_dir.mkdir(parents=True)
    horizons_data.astype("<i2").tofile(web_data_dir / "horizons.bin")

    out_json = tmp_path / "reference.json"
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    generate_reference_fixtures(
        points=points,
        output_json=out_json,
        horizons_data=None,
        observer_heights=[1.0, 5.0],
    )
    captured = capsys.readouterr()
    assert "haworth-p001" in captured.out
    assert "mons-mouton-p001" in captured.out

    fixtures = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(fixtures) == 12
    chosen_ids = [c["point_id"] for c in fixtures]
    assert "malapert-massif-c" in chosen_ids
    assert "haworth-p001" in chosen_ids
    assert "mons-mouton-p001" in chosen_ids
    assert "haworth-c" not in chosen_ids
    for c in fixtures:
        assert c["horizon_source"] == "packed int16"
    mal_1m = next(c for c in fixtures if c["point_id"] == "malapert-massif-c" and c["observer_height_m"] == 1.0)
    mal_5m = next(c for c in fixtures if c["point_id"] == "malapert-massif-c" and c["observer_height_m"] == 5.0)
    assert mal_1m["summary"]["horizon_min"] == pytest.approx(1.23)
    assert mal_5m["summary"]["horizon_min"] == pytest.approx(-0.45)
