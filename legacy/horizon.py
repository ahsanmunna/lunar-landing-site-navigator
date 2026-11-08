import argparse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy.ndimage import map_coordinates
import spiceypy as spice
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RM = 1737400.0                 # lunar reference sphere radius (m), same as the DEM
SUN_R, EARTH_R = 0.2666, 0.95  # approximate angular radii (degrees)
HERE = Path(__file__).parent

ap = argparse.ArgumentParser()
ap.add_argument("dem")                          # path to the 80S elevation .tiff
ap.add_argument("lat", type=float)              # degrees, negative = south
ap.add_argument("lon", type=float)              # degrees east
ap.add_argument("--start", default="2027-01-01")
ap.add_argument("--days", type=int, default=30)
ap.add_argument("--height", type=float, default=2.0)   # observer height (m)
args = ap.parse_args()

# --- site position on the polar stereographic map (metres) ---
colat = np.radians(90.0 + args.lat)
rho0 = 2 * RM * np.tan(colat / 2)
lon = np.radians(args.lon)
x0, y0 = rho0 * np.sin(lon), rho0 * np.cos(lon)
k0 = 1 / np.cos(colat / 2) ** 2                 # map scale factor at the site
north = np.array([x0, y0]) / rho0               # "north" = away from the south pole
east = np.array([y0, -x0]) / rho0
az = np.radians(np.arange(0, 360, 1.0))
dirs = np.outer(np.cos(az), north) + np.outer(np.sin(az), east)   # (360, 2)

def horizon_from(z, tf, dist, h_site):
    """Highest terrain elevation angle (deg) along each azimuth, curvature included."""
    d = dist[None, :]
    xs, ys = x0 + dirs[:, 0:1] * d, y0 + dirs[:, 1:2] * d
    cols = (xs - tf.c) / tf.a - 0.5
    rows = (ys - tf.f) / tf.e - 0.5
    ht = map_coordinates(z, [rows, cols], order=1, mode="constant",
                         cval=np.nan, output=np.float64)
    delta = (d / k0) / RM                        # central angle (rad)
    rt, r0 = RM + ht, RM + h_site + args.height
    ang = np.degrees(np.arctan2(rt * np.cos(delta) - r0, rt * np.sin(delta)))
    return np.nanmax(np.where(np.isnan(ang), -90.0, ang), axis=1)

# --- read the DEM: a coarse copy of everything + a sharp window around the site ---
with rasterio.open(args.dem) as src:
    h, w = src.height // 8, src.width // 8
    cache = HERE / "dem_160m_cache.npy"
    if cache.exists():
        zf = np.load(cache)
    else:
        print("Building the 160 m copy (once, a few minutes)...", flush=True)
        zf = src.read(1, out_shape=(h, w), resampling=Resampling.average).astype("float32")
        np.save(cache, zf)
    tf = src.transform * src.transform.scale(src.width / w, src.height / h)

    half = 8000.0
    win = Window(int((x0 - half - src.transform.c) / src.transform.a),
                 int((y0 + half - src.transform.f) / src.transform.e),
                 int(2 * half / 20), int(2 * half / 20))
    zn = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")
    tn = src.window_transform(win)

col = (x0 - tn.c) / tn.a - 0.5
row = (y0 - tn.f) / tn.e - 0.5
h_site = float(map_coordinates(zn, [[row], [col]], order=1, output=np.float64)[0])

hor = np.maximum(horizon_from(zn, tn, np.arange(20, 8000, 20.0), h_site),
                 horizon_from(zf, tf, np.arange(160, 150000, 160.0), h_site))

# --- Sun and Earth directions from SPICE, in the site's local frame ---
for k in ["naif0012.tls", "de440.bsp", "moon_pa_de440_200625.bpc", "moon_de440_220930.tf"]:
    spice.furnsh(str(HERE / "kernels" / k))
la, lo = np.radians(args.lat), np.radians(args.lon)
up = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
e3 = np.array([-np.sin(lo), np.cos(lo), 0.0])
n3 = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
r_site = (RM + h_site + args.height) / 1000.0 * up       # km

def az_el(body, et):
    pos, _ = spice.spkpos(body, et, "MOON_ME", "NONE", "MOON")
    v = np.array(pos) - r_site
    v /= np.linalg.norm(v)
    return np.degrees(np.arctan2(v @ e3, v @ n3)) % 360, np.degrees(np.arcsin(v @ up))

et0 = spice.str2et(args.start + " 00:00:00")
ets = et0 + np.arange(0, args.days * 86400, 3600.0)
sun = np.array([az_el("SUN", t) for t in ets])
earth = np.array([az_el("EARTH", t) for t in ets])

def visible_fraction(body, r):
    hz = np.interp(body[:, 0], np.arange(360), hor, period=360)
    t = np.clip((body[:, 1] - hz) / r, -1, 1)
    return (np.arccos(-t) + t * np.sqrt(1 - t ** 2)) / np.pi

def longest_run(mask):
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best

sv, ev = visible_fraction(sun, SUN_R), visible_fraction(earth, EARTH_R)
print(f"Site lat {args.lat}, lon {args.lon}; ground height {h_site:.0f} m; "
      f"{args.start} for {args.days} days (hourly)")
print(f"Horizon elevation: min {hor.min():.2f}, max {hor.max():.2f} deg")
print(f"Sun:   average visible fraction {sv.mean():.2f}; "
      f"any sun {np.mean(sv > 0) * 100:.0f}% of hours; "
      f"longest total darkness {longest_run(sv == 0)} h")
print(f"Earth: mostly visible {np.mean(ev > 0.5) * 100:.0f}% of hours; "
      f"any part visible {np.mean(ev > 0) * 100:.0f}%; "
      f"longest no-contact gap {longest_run(ev == 0)} h")

fig, ax = plt.subplots(figsize=(12, 4.5))
ax.fill_between(np.arange(360), -10, hor, color="0.35", label="terrain horizon")
ax.scatter(sun[:, 0], sun[:, 1], s=6, c="orange", label="Sun")
ax.scatter(earth[:, 0], earth[:, 1], s=6, c="tab:blue", label="Earth")
ax.set_xlim(0, 360)
ax.set_ylim(min(hor.min(), -1) - 0.5,
            max(hor.max(), sun[:, 1].max(), earth[:, 1].max()) + 1)
ax.set_xlabel("azimuth (deg from north, clockwise)")
ax.set_ylabel("elevation (deg)")
ax.set_title(f"Lat {args.lat}, lon {args.lon}: {args.start}, {args.days} days")
ax.legend(loc="upper right")
fig.savefig("site_panorama.png", dpi=110, bbox_inches="tight")
print("saved site_panorama.png")