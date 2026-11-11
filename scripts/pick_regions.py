"""Interactive tool to digitize Artemis III candidate regions near the lunar South Pole.

Loads 160 m DEM cache, displays hillshaded relief with polar stereographic
graticule, and allows interactive digitization of candidate regions.
"""

import sys
import os
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import numpy as np

# Standalone or package geometry transforms
try:
    from scripts._geo import forward, inverse, MOON_RADIUS_M
except ImportError:
    try:
        from _geo import forward, inverse, MOON_RADIUS_M
    except ImportError:
        from lunar_engine.geometry import forward, inverse
        from lunar_engine.config import MOON_RADIUS_M

DEFAULT_REGION_NAMES: List[str] = [
    "Peak near Cabeus B",
    "Haworth",
    "Malapert Massif",
    "Mons Mouton Plateau",
    "Mons Mouton",
    "Nobile Rim 1",
    "Nobile Rim 2",
    "de Gerlache Rim 2",
    "Slater Plain",
]

DEFAULT_SOURCE_TAG: str = (
    "approximate; centre placed in pick_regions.py from box positions measured on an annotated screenshot of NASA's Artemis III candidate-region map; not surveyed"
)
DEFAULT_PICKED_BY: str = "pick_regions.py"


def is_region_digitized(region: Optional[dict]) -> bool:
    """Check if a region record contains both 'picked_by' and 'picked_utc'."""
    if not region or not isinstance(region, dict):
        return False
    picked_by = region.get("picked_by")
    picked_utc = region.get("picked_utc")
    return bool(picked_by and str(picked_by).strip() and picked_utc and str(picked_utc).strip())


def slugify(name: str) -> str:
    """Generate a clean slug identifier from a region name."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def sample_ground_height(dem: np.ndarray, x_m: float, y_m: float) -> float:
    """Bilinear interpolation of ground elevation (m) from 160 m DEM cache.

    Bounds: x in [-304000, 304000] m, y in [-304000, 304000] m.
    Row 0 corresponds to +304000 m (near side up).
    Col 0 corresponds to -304000 m (west edge, east to right).
    """
    col = (x_m + 304000.0) / 160.0 - 0.5
    row = (304000.0 - y_m) / 160.0 - 0.5
    h, w = dem.shape
    if 0.0 <= row < (h - 1) and 0.0 <= col < (w - 1):
        r0 = int(np.floor(row))
        c0 = int(np.floor(col))
        r1 = r0 + 1
        c1 = c0 + 1
        dr = row - r0
        dc = col - c0
        val = (
            (1.0 - dr) * (1.0 - dc) * dem[r0, c0]
            + dr * (1.0 - dc) * dem[r1, c0]
            + (1.0 - dr) * dc * dem[r0, c1]
            + dr * dc * dem[r1, c1]
        )
        return float(val)
    elif 0 <= row < h and 0 <= col < w:
        r0 = int(np.clip(round(row), 0, h - 1))
        c0 = int(np.clip(round(col), 0, w - 1))
        return float(dem[r0, c0])
    return 0.0


def load_or_compute_hillshade(dem: np.ndarray, cache_path: Optional[Path] = None) -> np.ndarray:
    """Return hillshaded relief of the DEM, using cache if available."""
    if cache_path is not None and cache_path.exists():
        try:
            return np.load(cache_path)
        except Exception:
            pass

    print("Computing hillshade from DEM (az=315°, alt=45°)...", flush=True)
    from matplotlib.colors import LightSource

    ls = LightSource(azdeg=315, altdeg=45)
    shade = ls.hillshade(dem, vert_exag=3.0, dx=160.0, dy=160.0)

    if cache_path is not None:
        try:
            np.save(cache_path, shade.astype(np.float32))
        except Exception:
            pass

    return shade


def load_region_names(path: Path) -> List[str]:
    """Load ordered region names list from JSON, or create with defaults."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_REGION_NAMES, f, indent=2)
        return list(DEFAULT_REGION_NAMES)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [str(x) for x in data]


def load_existing_regions(path: Path) -> Dict[str, dict]:
    """Load existing regions from JSON file into a name-keyed dict."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {r["name"]: r for r in data if "name" in r}
    except Exception as exc:
        print(f"Warning: Could not read {path}: {exc}")
        return {}


def save_regions(regions_dict: Dict[str, dict], names_order: List[str], path: Path) -> None:
    """Save region dictionary to JSON file in canonical name order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out_list = []
    for name in names_order:
        if name in regions_dict:
            out_list.append(regions_dict[name])
    for name, r in regions_dict.items():
        if name not in names_order:
            out_list.append(r)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out_list, f, indent=2)


def match_redo_targets(all_names: List[str], redo_args: List[str]) -> List[str]:
    """Match command line redo strings against region names or slugs."""
    if not redo_args:
        return []

    tokens = []
    for arg in redo_args:
        for t in arg.split(","):
            cleaned = t.strip()
            if cleaned:
                tokens.append(cleaned)

    if any(t.lower() == "all" for t in tokens):
        return list(all_names)

    matched = []
    for t in tokens:
        t_low = t.lower()
        t_slug = slugify(t)
        found = False
        # 1. Exact match (case insensitive)
        for name in all_names:
            if name.lower() == t_low or slugify(name) == t_slug:
                if name not in matched:
                    matched.append(name)
                found = True
        # 2. Substring match
        if not found:
            for name in all_names:
                if t_low in name.lower():
                    if name not in matched:
                        matched.append(name)
                    found = True
        if not found:
            print(f"Warning: No candidate region matches '--redo {t}'")

    return matched


def draw_graticule(ax, r_moon_m: float = MOON_RADIUS_M) -> None:
    """Overlay latitude circles every 1 deg and meridians every 30 deg, labelled."""
    import matplotlib.pyplot as plt

    r_moon_km = r_moon_m / 1000.0

    # Latitude circles every 1 deg from -89 to -80
    for lat in range(-89, -79):
        colat_rad = np.radians(90.0 + lat)
        rho_km = 2.0 * r_moon_km * np.tan(colat_rad / 2.0)
        is_major = (lat % 5 == 0)
        circle = plt.Circle(
            (0, 0),
            rho_km,
            fill=False,
            color="#55ffff" if is_major else "#aaaaaa",
            linestyle="--" if is_major else ":",
            linewidth=0.8 if is_major else 0.45,
            alpha=0.6 if is_major else 0.35,
            zorder=3,
        )
        ax.add_patch(circle)

        # Label along lon = 15 deg
        lon_lbl_rad = np.radians(15.0)
        lx = rho_km * np.sin(lon_lbl_rad)
        ly = rho_km * np.cos(lon_lbl_rad)
        ax.text(
            lx,
            ly,
            f"{abs(lat)}°S",
            color="#aaffff" if is_major else "#cccccc",
            fontsize=6.5 if not is_major else 7.5,
            ha="center",
            va="center",
            zorder=4,
            bbox=dict(boxstyle="round,pad=0.1", fc="#000000", ec="none", alpha=0.55),
        )

    # Meridians every 30 degrees
    meridians = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
    rho_max_km = 304.0
    for lon in meridians:
        lon_rad = np.radians(lon)
        x_end = rho_max_km * np.sin(lon_rad)
        y_end = rho_max_km * np.cos(lon_rad)
        is_cardinal = (lon % 90 == 0)
        ax.plot(
            [0, x_end],
            [0, y_end],
            color="#55ffff" if is_cardinal else "#aaaaaa",
            linestyle="--" if is_cardinal else ":",
            linewidth=0.8 if is_cardinal else 0.45,
            alpha=0.6 if is_cardinal else 0.35,
            zorder=3,
        )

        # Label near outer rim (292 km)
        label_r = 292.0
        lx = label_r * np.sin(lon_rad)
        ly = label_r * np.cos(lon_rad)
        if lon == 0:
            txt = "0° (Near Side)"
        elif lon == 180:
            txt = "180° (Far Side)"
        elif lon == 90:
            txt = "90°E"
        elif lon == 270:
            txt = "90°W"
        elif lon < 180:
            txt = f"{lon}°E"
        else:
            txt = f"{360 - lon}°W"

        ax.text(
            lx,
            ly,
            txt,
            color="#aaffff" if is_cardinal else "#eeeeee",
            fontsize=7.5,
            weight="bold" if is_cardinal else "normal",
            ha="center",
            va="center",
            zorder=4,
            bbox=dict(boxstyle="round,pad=0.15", fc="#000000", ec="none", alpha=0.6),
        )

    # South Pole marker at (0, 0)
    ax.plot(0, 0, "+", color="#ffff00", markersize=10, markeredgewidth=1.5, zorder=5)
    ax.text(
        0,
        -5.0,
        "90°S (South Pole)",
        color="#ffff00",
        fontsize=7.5,
        ha="center",
        va="top",
        zorder=5,
        bbox=dict(boxstyle="round,pad=0.1", fc="#000000", ec="none", alpha=0.6),
    )


def draw_region_marker(ax, record: dict) -> List[Any]:
    """Draw a region's center point, circular perimeter, and text label on the axes."""
    import matplotlib.pyplot as plt

    x_km = record["center_x_m"] / 1000.0
    y_km = record["center_y_m"] / 1000.0
    radius_km = float(record.get("radius_km", 4.0))
    name = record["name"]

    dot = ax.plot(x_km, y_km, "o", color="#00ff66", markersize=5, zorder=10)[0]
    circle = plt.Circle(
        (x_km, y_km),
        radius_km,
        fill=False,
        color="#00ff66",
        linewidth=1.4,
        linestyle="-",
        zorder=10,
    )
    ax.add_patch(circle)
    label = ax.text(
        x_km,
        y_km + radius_km + 1.2,
        name,
        color="#00ff66",
        fontsize=8.5,
        weight="bold",
        ha="center",
        va="bottom",
        zorder=11,
        bbox=dict(boxstyle="round,pad=0.2", fc="#000000", ec="#00ff66", alpha=0.7),
    )
    return [dot, circle, label]


class RegionDigitizer:
    """Interactive controller for digitizing Artemis III candidate regions."""

    def __init__(
        self,
        fig,
        ax,
        dem: np.ndarray,
        region_names: List[str],
        existing_regions: Dict[str, dict],
        redo_targets: List[str],
        out_path: Path,
    ):
        self.fig = fig
        self.ax = ax
        self.dem = dem
        self.region_names = region_names
        self.regions_by_name: Dict[str, dict] = dict(existing_regions)
        self.out_path = out_path
        self.artists_by_name: Dict[str, List[Any]] = {}
        self.last_mouse_pos: Tuple[float, float] = (0.0, 0.0)
        self.history: List[Tuple[str, str, Optional[dict]]] = []

        # Determine queue of regions to digitize: undigitized regions + redo targets
        self.queue: List[str] = []
        if redo_targets:
            for r in redo_targets:
                if r not in self.queue:
                    self.queue.append(r)
        for r in region_names:
            rec = self.regions_by_name.get(r)
            if not is_region_digitized(rec) and r not in self.queue:
                self.queue.append(r)

        self.current_idx: int = 0

        # Draw already-digitized regions not in redo/prompt queue
        for name, rec in self.regions_by_name.items():
            if is_region_digitized(rec) and name not in self.queue:
                self.artists_by_name[name] = draw_region_marker(self.ax, rec)

        # Hook events
        self.fig.canvas.mpl_connect("motion_notify_event", self.on_mouse_move)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key_press)

        # Status line coordinate formatting
        self.ax.format_coord = self.format_status_coord

        self.update_title()

    def format_status_coord(self, x_km: float, y_km: float) -> str:
        """Format real-time cursor status: lat, lon, x_km, y_km, ground height (m)."""
        x_m = x_km * 1000.0
        y_m = y_km * 1000.0
        lat, lon = inverse(x_m, y_m)
        h_m = sample_ground_height(self.dem, x_m, y_m)
        return (
            f"lat: {lat:+.4f}°, lon: {lon:+.4f}° | "
            f"x: {x_km:+.2f} km, y: {y_km:+.2f} km | height: {h_m:.1f} m"
        )

    def on_mouse_move(self, event) -> None:
        """Track mouse coordinates and update toolbar status."""
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return
        self.last_mouse_pos = (event.xdata, event.ydata)
        if self.fig.canvas.toolbar is not None and hasattr(self.fig.canvas.toolbar, "set_message"):
            msg = self.format_status_coord(event.xdata, event.ydata)
            self.fig.canvas.toolbar.set_message(msg)

    def on_key_press(self, event) -> None:
        """Handle keyboard commands: SPACE (record), BACKSPACE (undo), N (skip)."""
        key = event.key
        if key in (" ", "space"):
            self.record_current()
        elif key in ("backspace",):
            self.undo()
        elif key in ("n", "N"):
            self.skip()
        elif key in ("q", "Q", "escape"):
            import matplotlib.pyplot as plt

            plt.close(self.fig)

    def record_current(self) -> None:
        """Record current mouse position as the center for active region."""
        if self.current_idx >= len(self.queue):
            print("All regions in digitization queue recorded. Re-run with --redo <name> to re-record.")
            return

        x_km, y_km = self.last_mouse_pos
        if abs(x_km) > 304.0 or abs(y_km) > 304.0:
            print("Cursor outside DEM bounds (+-304 km). Please hover over the map.")
            return

        region_name = self.queue[self.current_idx]
        x_m = float(x_km * 1000.0)
        y_m = float(y_km * 1000.0)
        lat, lon = inverse(x_m, y_m)
        ground_height_m = sample_ground_height(self.dem, x_m, y_m)

        existing_rec = self.regions_by_name.get(region_name)
        radius_km = existing_rec.get("radius_km", 4.0) if existing_rec else 4.0

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "id": slugify(region_name),
            "name": region_name,
            "center_x_m": round(x_m, 2),
            "center_y_m": round(y_m, 2),
            "center_lat": round(lat, 6),
            "center_lon": round(lon, 6),
            "ground_height_m": round(ground_height_m, 2),
            "radius_km": radius_km,
            "source": DEFAULT_SOURCE_TAG,
            "picked_by": DEFAULT_PICKED_BY,
            "picked_utc": now_utc,
        }

        # Clear previous artists
        if region_name in self.artists_by_name:
            for artist in self.artists_by_name[region_name]:
                artist.remove()
            del self.artists_by_name[region_name]

        # Draw updated marker
        self.artists_by_name[region_name] = draw_region_marker(self.ax, record)

        # Update history & storage
        self.history.append(("record", region_name, existing_rec))
        self.regions_by_name[region_name] = record

        save_regions(self.regions_by_name, self.region_names, self.out_path)

        print(
            f"[RECORDED {self.current_idx + 1}/{len(self.queue)}] '{region_name}': "
            f"lat={lat:.4f}°, lon={lon:.4f}°, x={x_km:.2f} km, y={y_km:.2f} km, height={ground_height_m:.1f} m"
        )

        self.current_idx += 1
        self.update_title()
        self.fig.canvas.draw_idle()

    def undo(self) -> None:
        """Undo the previous record or skip action."""
        if not self.history:
            print("Nothing to undo.")
            return

        action = self.history.pop()
        action_type = action[0]

        if action_type == "record":
            _, region_name, prev_rec = action
            if region_name in self.artists_by_name:
                for artist in self.artists_by_name[region_name]:
                    artist.remove()
                del self.artists_by_name[region_name]

            if prev_rec is not None:
                self.regions_by_name[region_name] = prev_rec
                if is_region_digitized(prev_rec):
                    self.artists_by_name[region_name] = draw_region_marker(self.ax, prev_rec)
            else:
                if region_name in self.regions_by_name:
                    del self.regions_by_name[region_name]

            save_regions(self.regions_by_name, self.region_names, self.out_path)
            if self.current_idx > 0:
                self.current_idx -= 1
            print(f"[UNDO] Reverted recording for '{region_name}'")

        elif action_type == "skip":
            _, region_name = action
            if self.current_idx > 0:
                self.current_idx -= 1
            print(f"[UNDO] Reverted skip for '{region_name}'")

        self.update_title()
        self.fig.canvas.draw_idle()

    def skip(self) -> None:
        """Skip recording the current region."""
        if self.current_idx >= len(self.queue):
            print("Queue already completed.")
            return

        region_name = self.queue[self.current_idx]
        self.history.append(("skip", region_name, None))
        print(f"[SKIP] Skipped '{region_name}'")
        self.current_idx += 1
        self.update_title()
        self.fig.canvas.draw_idle()

    def update_title(self) -> None:
        """Update figure title with target region and interaction controls."""
        if self.current_idx < len(self.queue):
            reg = self.queue[self.current_idx]
            self.ax.set_title(
                f"Target [{self.current_idx + 1}/{len(self.queue)}]: {reg}\n"
                f"[SPACE]: Record  |  [BACKSPACE]: Undo  |  [N]: Skip  |  [Q]: Exit",
                fontsize=10.5,
                weight="bold",
                color="#ffff55",
            )
        else:
            total_saved = len(self.regions_by_name)
            self.ax.set_title(
                f"All {total_saved} Artemis III regions digitized! (Saved to {self.out_path.name})\n"
                f"Re-run with --redo <name> to re-record. Press [Q] to close.",
                fontsize=10.5,
                weight="bold",
                color="#55ff55",
            )


def find_file(filename: str, candidates: List[Path]) -> Optional[Path]:
    """Find the first matching file among candidates."""
    for c in candidates:
        if c.exists():
            return c
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive tool to digitize Artemis III candidate regions near the lunar South Pole."
    )
    parser.add_argument(
        "--redo",
        nargs="*",
        default=[],
        help="One or more region names or slugs to re-digitize (e.g. --redo Haworth, or --redo all).",
    )
    parser.add_argument(
        "--names",
        default=None,
        help="Path to region_names.json (default: data_src/region_names.json)",
    )
    parser.add_argument(
        "--regions",
        default=None,
        help="Path to regions.json (default: data_src/regions.json)",
    )
    parser.add_argument(
        "--cache",
        default=None,
        help="Path to dem_160m_cache.npy (default: ./dem_160m_cache.npy)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without displaying GUI window (for headless checks and automated tests).",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    # Resolve paths
    names_path = (
        Path(args.names)
        if args.names
        else project_root / "data_src" / "region_names.json"
    )
    regions_path = (
        Path(args.regions)
        if args.regions
        else project_root / "data_src" / "regions.json"
    )

    cache_candidates = [
        Path(args.cache) if args.cache else None,
        Path.cwd() / "dem_160m_cache.npy",
        project_root / "dem_160m_cache.npy",
    ]
    cache_path = find_file("dem_160m_cache.npy", [p for p in cache_candidates if p is not None])

    if cache_path is None or not cache_path.exists():
        print("Error: 160 m DEM cache file dem_160m_cache.npy not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading DEM cache from: {cache_path}")
    dem = np.load(cache_path)

    # Hillshade cache path
    hillshade_cache = cache_path.parent / "dem_160m_hillshade_cache.npy"
    shade = load_or_compute_hillshade(dem, hillshade_cache)

    # Load regions
    region_names = load_region_names(names_path)
    existing_regions = load_existing_regions(regions_path)

    redo_targets = match_redo_targets(region_names, args.redo)

    print(f"Candidate regions ({len(region_names)} total): {', '.join(region_names)}")
    if redo_targets:
        print(f"Redo requested for: {', '.join(redo_targets)}")
    digitized_count = sum(1 for r in existing_regions.values() if is_region_digitized(r))
    print(f"Already digitized: {digitized_count} / {len(region_names)} regions")

    if args.non_interactive:
        print("Non-interactive mode: verified DEM and data files successfully.")
        return

    # Interactive GUI with TkAgg
    import matplotlib

    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 10))
    fig.canvas.manager.set_window_title("Artemis III Candidate Regions Digitizer (80S-90S)")

    ax.imshow(shade, extent=[-304.0, 304.0, -304.0, 304.0], cmap="gray", origin="upper")
    ax.set_xlim(-304.0, 304.0)
    ax.set_ylim(-304.0, 304.0)
    ax.set_aspect("equal")
    ax.set_xlabel("km from the pole (East ->)", fontsize=10)
    ax.set_ylabel("km from the pole (Near Side ^)", fontsize=10)

    draw_graticule(ax, MOON_RADIUS_M)

    digitizer = RegionDigitizer(
        fig=fig,
        ax=ax,
        dem=dem,
        region_names=region_names,
        existing_regions=existing_regions,
        redo_targets=redo_targets,
        out_path=regions_path,
    )

    print("\n--- CONTROLS ---")
    print("  [SPACE]     : Record hovered position for current candidate region")
    print("  [BACKSPACE] : Undo last action")
    print("  [N]         : Skip current candidate region")
    print("  [Q]         : Close window")
    print("  Zoom / Pan  : Use the matplotlib toolbar")
    print("----------------\n")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
