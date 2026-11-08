import sys
import numpy as np
import rasterio
from rasterio.enums import Resampling

path = sys.argv[1]
print("opening:", path, flush=True)

with rasterio.open(path) as src:
    print("size (px):", src.width, "x", src.height)
    print("pixel size:", src.res)
    print("data type:", src.dtypes[0], " nodata:", src.nodata)
    print("CRS:", src.crs)
    print("bounds:", src.bounds)
    print("overviews:", src.overviews(1))
    print("tags:", src.tags(), src.tags(1), flush=True)

    print("reading a thinned-out preview...", flush=True)
    step = max(src.width // 1500, 1)
    h, w = src.height // step, src.width // step
    small = src.read(1, out_shape=(h, w),
                     resampling=Resampling.nearest).astype("float64")
    if src.nodata is not None:
        small[small == src.nodata] = np.nan
    print(f"preview {w}x{h}: min {np.nanmin(small):.1f}  "
          f"max {np.nanmax(small):.1f}  mean {np.nanmean(small):.1f}")