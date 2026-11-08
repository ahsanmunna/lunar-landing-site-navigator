import sys
from pathlib import Path
import spiceypy as spice

KERNEL_DIR = Path(__file__).parent / "kernels"
LSK, SPK, BPC, FK = "naif0012.tls", "de440.bsp", "moon_pa_de440_200625.bpc", "moon_de440_220930.tf"
if not (KERNEL_DIR / SPK).exists() and (KERNEL_DIR / "de440s.bsp").exists():
    SPK = "de440s.bsp"

missing = [k for k in (LSK, SPK, BPC, FK) if not (KERNEL_DIR / k).exists()]
if missing:
    print("Missing kernel files in", KERNEL_DIR)
    for k in missing:
        print("  -", k)
    sys.exit(1)

for k in (LSK, SPK, BPC, FK):
    spice.furnsh(str(KERNEL_DIR / k))

et = spice.str2et("2026-06-18 18:00:00 UTC")

def lat_lon(body):
    # Direction from the Moon's center to `body`, in the MOON_ME frame
    pos, _ = spice.spkpos(body, et, "MOON_ME", "NONE", "MOON")
    _, lon, lat = spice.reclat(pos)
    return lat * spice.dpr(), lon * spice.dpr()

for body, label in [("SUN", "Sub-solar"), ("EARTH", "Sub-Earth")]:
    lat, lon = lat_lon(body)
    print(f"{label}: {lat:.3f} deg lat, {lon:.3f} deg lon")