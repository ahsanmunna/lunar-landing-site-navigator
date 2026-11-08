"""lunar_engine: Moon south-pole terrain horizon and ephemeris analysis package.

Built for NASA Space Apps ("Lunar Landing Site Navigator").
"""

from lunar_engine.config import (
    MOON_RADIUS_M,
    MOON_RADIUS_KM,
    SUN_RADIUS_KM,
    EARTH_RADIUS_KM,
    DEFAULT_STEP_S,
    DEFAULT_OBSERVER_HEIGHT_M,
    DEFAULT_START,
    DEFAULT_DAYS,
    get_dem_path,
    get_kernel_dir,
    get_cache_path,
)
from lunar_engine.geometry import (
    forward,
    inverse,
    latlon_to_xy,
    xy_to_latlon,
    map_scale_factor,
    map_local_frame,
    map_azimuth_directions,
    site_local_frame,
    site_position_km,
)
from lunar_engine.horizon import compute_horizon
from lunar_engine.ephemeris import (
    load_kernels,
    create_time_grid,
    moon_centered_positions,
    get_moon_centered_positions,
    sub_body_latlon,
    angular_radius_deg,
    sun_earth_azel,
    EphemerisData,
)
from lunar_engine.visibility import (
    disc_visible_fraction,
    visible_fraction,
    longest_run,
    summarize,
    plot_panorama,
)

__all__ = [
    "MOON_RADIUS_M",
    "MOON_RADIUS_KM",
    "SUN_RADIUS_KM",
    "EARTH_RADIUS_KM",
    "DEFAULT_STEP_S",
    "DEFAULT_OBSERVER_HEIGHT_M",
    "DEFAULT_START",
    "DEFAULT_DAYS",
    "get_dem_path",
    "get_kernel_dir",
    "get_cache_path",
    "forward",
    "inverse",
    "latlon_to_xy",
    "xy_to_latlon",
    "map_scale_factor",
    "map_local_frame",
    "map_azimuth_directions",
    "site_local_frame",
    "site_position_km",
    "compute_horizon",
    "load_kernels",
    "create_time_grid",
    "moon_centered_positions",
    "get_moon_centered_positions",
    "sub_body_latlon",
    "angular_radius_deg",
    "sun_earth_azel",
    "EphemerisData",
    "disc_visible_fraction",
    "visible_fraction",
    "longest_run",
    "summarize",
    "plot_panorama",
]
