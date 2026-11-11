"""Worker task for multiprocessing horizon precomputations."""

import numpy as np
from lunar_engine.horizon import compute_horizon


def compute_point_horizons(args):
    """Compute 360-ray horizons for all specified observer heights at a given site.

    Parameters
    ----------
    args : tuple
        (point_idx, lat, lon, heights)

    Returns
    -------
    tuple
        (point_idx, np.ndarray of shape (len(heights), 360) dtype int16)
    """
    idx, lat, lon, heights = args
    hor_list = []
    for h in heights:
        hor, _ = compute_horizon(lat, lon, observer_height_m=h)
        hor_int16 = np.round(hor * 100.0).astype(np.int16)
        hor_list.append(hor_int16)
    return idx, np.stack(hor_list, axis=0)
