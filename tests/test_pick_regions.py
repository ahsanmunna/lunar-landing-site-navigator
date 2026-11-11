"""Unit tests for candidate region digitizer (scripts/pick_regions.py)."""

import json
from pathlib import Path
import numpy as np
import pytest

from scripts._geo import forward, inverse
from scripts.pick_regions import (
    slugify,
    sample_ground_height,
    load_region_names,
    load_existing_regions,
    save_regions,
    match_redo_targets,
    is_region_digitized,
    RegionDigitizer,
    DEFAULT_REGION_NAMES,
    DEFAULT_SOURCE_TAG,
    DEFAULT_PICKED_BY,
)


def test_slugify():
    """Verify conversion of region names to slug IDs."""
    assert slugify("Peak near Cabeus B") == "peak-near-cabeus-b"
    assert slugify("Haworth") == "haworth"
    assert slugify("Malapert Massif") == "malapert-massif"
    assert slugify("Mons Mouton Plateau") == "mons-mouton-plateau"
    assert slugify("Mons Mouton") == "mons-mouton"
    assert slugify("Nobile Rim 1") == "nobile-rim-1"
    assert slugify("Nobile Rim 2") == "nobile-rim-2"
    assert slugify("de Gerlache Rim 2") == "de-gerlache-rim-2"
    assert slugify("Slater Plain") == "slater-plain"


def test_region_names_json_contents():
    """Verify data_src/region_names.json contains the exact 9 expected Artemis III regions."""
    path = Path("data_src/region_names.json")
    assert path.exists(), "data_src/region_names.json should exist"
    names = json.loads(path.read_text(encoding="utf-8"))
    assert names == DEFAULT_REGION_NAMES


def test_regions_json_schema_and_values():
    """Verify data_src/regions.json has the requested schema and valid candidate coordinates."""
    path = Path("data_src/regions.json")
    assert path.exists(), "data_src/regions.json should exist"
    regions = json.loads(path.read_text(encoding="utf-8"))
    assert len(regions) == 9

    expected_keys = {
        "id",
        "name",
        "center_x_m",
        "center_y_m",
        "center_lat",
        "center_lon",
        "ground_height_m",
        "radius_km",
        "source",
    }

    for reg in regions:
        assert expected_keys.issubset(set(reg.keys()))
        assert set(reg.keys()) - expected_keys <= {"picked_by", "picked_utc"}
        assert reg["id"] == slugify(reg["name"])
        assert reg["source"] == DEFAULT_SOURCE_TAG
        assert isinstance(reg["center_x_m"], (int, float))
        assert isinstance(reg["center_y_m"], (int, float))
        assert -90.0 <= reg["center_lat"] <= -80.0
        assert -180.0 <= reg["center_lon"] <= 180.0
        assert isinstance(reg["radius_km"], (int, float)) and not isinstance(reg["radius_km"], bool)
        assert 1 <= reg["radius_km"] <= 40

        # Verify forward transform matches x, y
        x_calc, y_calc = forward(reg["center_lat"], reg["center_lon"])
        assert reg["center_x_m"] == pytest.approx(x_calc, abs=0.1)
        assert reg["center_y_m"] == pytest.approx(y_calc, abs=0.1)


def test_match_redo_targets():
    """Verify matching of --redo arguments by exact name, slug, substring, and 'all'."""
    names = DEFAULT_REGION_NAMES

    # Single exact name
    assert match_redo_targets(names, ["Haworth"]) == ["Haworth"]

    # Slug match
    assert match_redo_targets(names, ["peak-near-cabeus-b"]) == ["Peak near Cabeus B"]

    # Multiple targets
    assert match_redo_targets(names, ["Haworth", "Mons Mouton"]) == ["Haworth", "Mons Mouton"]

    # Comma-separated
    assert match_redo_targets(names, ["Haworth, Mons Mouton"]) == ["Haworth", "Mons Mouton"]

    # Case-insensitive substring
    assert match_redo_targets(names, ["slater"]) == ["Slater Plain"]

    # 'all'
    assert match_redo_targets(names, ["all"]) == names


def test_sample_ground_height():
    """Verify ground height sampling on a synthetic DEM grid."""
    dem = np.zeros((3800, 3800), dtype=np.float32)
    # Put a 5000 m peak at center (South Pole: x=0, y=0 -> row 1899.5, col 1899.5)
    dem[1899, 1899] = 5000.0
    dem[1899, 1900] = 5000.0
    dem[1900, 1899] = 5000.0
    dem[1900, 1900] = 5000.0

    h = sample_ground_height(dem, 0.0, 0.0)
    assert h == pytest.approx(5000.0, abs=1e-3)


def test_save_regions_preserves_custom_radius(tmp_path):
    """Verify saving regions preserves user-customized radius_km."""
    out_file = tmp_path / "regions.json"
    regions_dict = {
        "Haworth": {
            "id": "haworth",
            "name": "Haworth",
            "center_x_m": -6968.95,
            "center_y_m": 77022.68,
            "center_lat": -87.45,
            "center_lon": -5.17,
            "ground_height_m": -3310.49,
            "radius_km": 6.5,  # user edited radius
            "source": DEFAULT_SOURCE_TAG,
        }
    }
    save_regions(regions_dict, ["Haworth"], out_file)
    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(loaded) == 1
    assert loaded[0]["radius_km"] == 6.5


def test_is_region_digitized():
    """Verify is_region_digitized requires non-empty picked_by and picked_utc."""
    # Fully digitized
    assert is_region_digitized({"picked_by": "pick_regions.py", "picked_utc": "2026-11-08T00:00:00Z"}) is True

    # Missing or empty picked_by
    assert is_region_digitized({"picked_utc": "2026-11-08T00:00:00Z"}) is False
    assert is_region_digitized({"picked_by": "", "picked_utc": "2026-11-08T00:00:00Z"}) is False
    assert is_region_digitized({"picked_by": "   ", "picked_utc": "2026-11-08T00:00:00Z"}) is False
    assert is_region_digitized({"picked_by": None, "picked_utc": "2026-11-08T00:00:00Z"}) is False

    # Missing or empty picked_utc
    assert is_region_digitized({"picked_by": "pick_regions.py"}) is False
    assert is_region_digitized({"picked_by": "pick_regions.py", "picked_utc": ""}) is False
    assert is_region_digitized({"picked_by": "pick_regions.py", "picked_utc": "   "}) is False
    assert is_region_digitized({"picked_by": "pick_regions.py", "picked_utc": None}) is False

    # Missing both / empty / None
    assert is_region_digitized({}) is False
    assert is_region_digitized(None) is False


def test_undigitized_regions_are_reprompted(tmp_path):
    """Task 2D: Existing regions lacking picked_by or picked_utc are treated as undigitized and queued for re-prompting."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    dem = np.zeros((100, 100), dtype=np.float32)
    names = ["Digitized Site", "Missing UTC Site", "Missing PickedBy Site", "Missing Both Site"]
    existing = {
        "Digitized Site": {
            "id": "digitized-site",
            "name": "Digitized Site",
            "center_x_m": 1000.0,
            "center_y_m": 2000.0,
            "center_lat": -85.0,
            "center_lon": 10.0,
            "ground_height_m": 100.0,
            "radius_km": 4.0,
            "source": DEFAULT_SOURCE_TAG,
            "picked_by": "pick_regions.py",
            "picked_utc": "2026-11-08T00:00:00Z",
        },
        "Missing UTC Site": {
            "id": "missing-utc-site",
            "name": "Missing UTC Site",
            "center_x_m": 3000.0,
            "center_y_m": 4000.0,
            "center_lat": -86.0,
            "center_lon": 20.0,
            "ground_height_m": 200.0,
            "radius_km": 4.0,
            "source": DEFAULT_SOURCE_TAG,
            "picked_by": "pick_regions.py",
        },
        "Missing PickedBy Site": {
            "id": "missing-pickedby-site",
            "name": "Missing PickedBy Site",
            "center_x_m": 5000.0,
            "center_y_m": 6000.0,
            "center_lat": -87.0,
            "center_lon": 30.0,
            "ground_height_m": 300.0,
            "radius_km": 4.0,
            "source": DEFAULT_SOURCE_TAG,
            "picked_utc": "2026-11-08T00:00:00Z",
        },
        "Missing Both Site": {
            "id": "missing-both-site",
            "name": "Missing Both Site",
            "center_x_m": 7000.0,
            "center_y_m": 8000.0,
            "center_lat": -88.0,
            "center_lon": 40.0,
            "ground_height_m": 400.0,
            "radius_km": 4.0,
            "source": DEFAULT_SOURCE_TAG,
        },
    }
    out_file = tmp_path / "regions.json"

    digitizer = RegionDigitizer(
        fig=fig,
        ax=ax,
        dem=dem,
        region_names=names,
        existing_regions=existing,
        redo_targets=[],
        out_path=out_file,
    )

    # Only "Digitized Site" is fully digitized; all 3 others must be in queue to be re-prompted
    assert "Digitized Site" not in digitizer.queue
    assert "Missing UTC Site" in digitizer.queue
    assert "Missing PickedBy Site" in digitizer.queue
    assert "Missing Both Site" in digitizer.queue
    assert digitizer.queue == ["Missing UTC Site", "Missing PickedBy Site", "Missing Both Site"]
    plt.close(fig)


def test_space_record_adds_picked_fields(tmp_path):
    """Task 2D: every SPACE-recorded region gets 'picked_by': 'pick_regions.py' and 'picked_utc': <timestamp>."""
    from datetime import datetime
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    dem = np.zeros((100, 100), dtype=np.float32)
    names = ["Haworth"]
    existing = {
        "Haworth": {
            "id": "haworth",
            "name": "Haworth",
            "center_x_m": -6968.95,
            "center_y_m": 77022.68,
            "center_lat": -87.45,
            "center_lon": -5.17,
            "ground_height_m": -3310.49,
            "radius_km": 4.0,
            "source": DEFAULT_SOURCE_TAG,
        }
    }
    out_file = tmp_path / "regions.json"

    digitizer = RegionDigitizer(
        fig=fig,
        ax=ax,
        dem=dem,
        region_names=names,
        existing_regions=existing,
        redo_targets=[],
        out_path=out_file,
    )

    assert "Haworth" in digitizer.queue
    assert digitizer.current_idx == 0

    # Simulate mouse hovering over Haworth at x= -6.97 km, y= 77.02 km
    digitizer.last_mouse_pos = (-6.97, 77.02)
    digitizer.record_current()

    # Verify updated in-memory record
    rec = digitizer.regions_by_name["Haworth"]
    assert rec["picked_by"] == "pick_regions.py"
    assert "picked_utc" in rec
    ts_str = rec["picked_utc"]
    assert ts_str.endswith("Z")
    parsed_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    assert parsed_dt.year >= 2026

    # Verify saved file has the fields
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["picked_by"] == "pick_regions.py"
    assert saved[0]["picked_utc"] == ts_str

    plt.close(fig)

