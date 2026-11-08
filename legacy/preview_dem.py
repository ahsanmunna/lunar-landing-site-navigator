import sys
import numpy as np
import rasterio
from rasterio.enums import Resampling
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = sys.argv[1]
SCALE = 16          # 20 m pixels -> 320 m preview pixels
EXAGGERATION = 3    # makes the relief easier to see

with rasterio.open(path) as src:
    h, w = src.height // SCALE, src.width // SCALE
    z = src.read(1, out_shape=(h, w), resampling=Resampling.average).astype("float64")
    pixel = src.res[0] * SCALE

z = np.where(np.isnan(z), np.nanmean(z), z)
gy, gx = np.gradient(z * EXAGGERATION, pixel)
normal = np.dstack((-gx, -gy, np.ones_like(z)))
normal /= np.linalg.norm(normal, axis=2, keepdims=True)
light = np.array([-1.0, -1.0, 1.5])
light /= np.linalg.norm(light)
shade = np.clip(normal @ light, 0, 1)

fig, ax = plt.subplots(figsize=(9, 9))
ax.imshow(shade, cmap="gray", extent=[-304, 304, -304, 304])
ax.plot(0, 0, "r+", markersize=14)                                    # south pole
ax.add_patch(plt.Circle((0, 0), 151.7, fill=False, color="cyan", lw=1))  # 85 deg S ring
ax.set_xlabel("km from the pole (x)")
ax.set_ylabel("km from the pole (y)")
ax.set_title("LOLA 80S DEM preview (320 m pixels)")
fig.savefig("dem_preview.png", dpi=110, bbox_inches="tight")
print("saved dem_preview.png")