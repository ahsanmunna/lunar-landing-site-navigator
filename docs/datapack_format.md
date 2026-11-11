# Lunar Data Pack Format Specification & Limitations

## 1. Overview & Architecture

The static lunar data pack is a self-contained, precomputed asset package deployed under `web/data/`. It powers the static web application for lunar South Pole landing site navigation without requiring a live Python backend or SPICE server.

The entire package is engineered to remain strictly under the **20 MB** total distribution ceiling while providing high-resolution terrain horizon profiles, two full years of continuous solar and terrestrial ephemeris, and interactive regional hillshade overlays for the candidate Artemis III exploration zones.

### Directory Structure

```text
web/data/
├── manifest.json       # Master metadata, constants, regions, and points catalog
├── horizons.bin        # Compact int16 binary horizon profiles [n_points][n_heights][360]
├── ephem.bin           # Compact float32 binary Moon-centred ephemeris [n_times][2][3]
└── regions/            # Regional hillshade relief PNGs (res = max(40, 2*radius_m/800) m/px, up to 800x800 px)
    ├── de-gerlache-rim-2.png
    ├── haworth.png
    ├── malapert-massif.png
    ├── mons-mouton.png
    ├── mons-mouton-plateau.png
    ├── nobile-rim-1.png
    ├── nobile-rim-2.png
    ├── peak-near-cabeus-b.png
    └── slater-plain.png
```

---

## 2. File Specifications & Binary Layouts

### 2.1 `manifest.json`

The central configuration manifest. Structure:

- `version`: Data format version string (`"1.0.0"`).
- `created_utc`: ISO 8601 UTC creation timestamp.
- `constants`: Physical reference constants matching LOLA and IAU models:
  - `moon_radius_m`: $1737400\text{ m}$ (lunar reference sphere radius).
  - `sun_radius_km`: $695700\text{ km}$ (solar physical radius).
  - `earth_radius_km`: $6371\text{ km}$ (Earth volumetric mean radius).
  - `horizon_az_step_deg`: $1^\circ$.
  - `azimuth_convention`: `"clockwise from outward-radial north"`.
- `observer_heights_m`: Observer heights evaluated in the horizon cache, e.g. `[1.0, 5.0]`.
- `grid_spacing_m`: Spatial step size between regular grid points within regions (default `1000` m, configurable via `--spacing`).
- `ephemeris`:
  - `file`: Relative path to binary ephemeris file (`"ephem.bin"`).
  - `start_utc`: Grid start time (`"2027-01-01T00:00:00Z"`).
  - `step_s`: Time increment in seconds (`900.0` s = 15 minutes).
  - `n_times`: Total number of ephemeris time epochs ($70,177$).
  - `frame`: SPICE reference frame (`"MOON_ME"`).
  - `layout`: `"[n_times][body: 0=SUN, 1=EARTH][x, y, z] float32 km"`.
- `horizons`:
  - `file`: Relative path to binary horizon file (`"horizons.bin"`).
  - `layout`: `"[n_points][n_heights][360] int16, value = round(deg*100), -32768 = no data"`.
  - `scale`: Fixed-point scale factor ($0.01^\circ$ per unit).
  - `nodata`: $-32768$.
- `regions`: List of region records containing:
  - `id`: Slug identifier (e.g. `"malapert-massif"`).
  - `name`: Display title (e.g. `"Malapert Massif"`).
  - `center_x_m`, `center_y_m`: Stereographic coordinates in metres.
  - `center_lat`, `center_lon`: Degrees ($^\circ$).
  - `radius_km`: Per-region boundary circle radius in kilometres ($1 \le \text{radius\_km} \le 40$).
  - `image`: Path to hillshade PNG (`"regions/<id>.png"`).
  - `extent`: Bounding box `{"x_min", "x_max", "y_min", "y_max"}` in stereographic metres.
- `points`: Catalog of landing sites across all regions:
  - `id`: Unique identifier (`"<region>-c"` for region centre, `"<region>-p001"` for grid sites).
  - `region`: Parent region slug.
  - `x_m`, `y_m`: Stereographic projection coordinates (metres).
  - `lat`, `lon`: Lunar latitude (negative for south) and east longitude (degrees).
  - `ground_height_m`: Elevation above $R = 1737400\text{ m}$ reference sphere.
  - `slope_deg`: Local surface slope angle ($^\circ$) over $\sim 100\text{ m}$ baseline.
  - `index`: 0-based array index into first dimension of `horizons.bin`.
- `sources`: Provenance citations (`LOLA LDEM_80S_20MPP_ADJ`, `NAIF de440`, `moon_pa_de440`, `naif0012`, `MOON_ME frame kernel`).

---

### 2.2 `horizons.bin` (Terrain Horizons)

- **Layout**: `[n_points][n_heights][360]` little-endian signed 16-bit integers (`int16`, `<i2`).
- **Dimensions**:
  - `n_points`: Total candidate sites across all regions (depends on per-region `radius_km` and `--spacing`, default `1000 m`).
  - `n_heights`: Observer heights ($2$ heights: index 0 = $1\text{ m}$, index 1 = $5\text{ m}$).
  - `360`: Azimuth angle bins ($0^\circ, 1^\circ, \ldots, 359^\circ$ clockwise from local north).
- **Encoding**:
  $$\text{value} = \text{round}(\theta_{\text{deg}} \times 100)$$
  $$\theta_{\text{deg}} = \frac{\text{value}}{100.0}$$
- **Missing Value**: $-32768$.
- **File Size**: $\text{n\_points} \times \text{n\_heights} \times 360 \times 2\text{ bytes}$ (kept within the $20\text{ MB}$ total `web/data/` limit).

---

### 2.3 `ephem.bin` (SPICE Solar & Terrestrial Ephemeris)

- **Layout**: `[n_times][body: 0=SUN, 1=EARTH][x, y, z]` little-endian 32-bit floats (`float32`, `<f4`).
- **Dimensions**:
  - `n_times`: $70,177$ time samples spanning `2027-01-01T00:00:00 UTC` through `2029-01-01T00:00:00 UTC` in $900\text{ s}$ intervals.
  - `body`: 2 bodies (index 0 = `SUN`, index 1 = `EARTH`).
  - `3`: Cartesian coordinates $[x, y, z]$ in kilometres.
- **Reference Frame**: Moon-centred `MOON_ME` (Mean Earth / Polar Axis frame).
- **Aberration Correction**: `NONE` (geometric positions).
- **File Size**: $70177 \times 2 \times 3 \times 4\text{ bytes} = 1,684,248\text{ bytes} \approx 1.61\text{ MB}$.

---

### 2.4 `regions/<id>.png` (Hillshaded Relief)

- **Resolution**: Adaptive pixel spacing $\text{res} = \max(40,\; 2 \cdot \text{radius\_m} / 800)\text{ m/px}$ across a $2 \times \text{radius\_m}$ square window centred on the region ($40\text{ m/px}$ for $\text{radius\_km} \le 16\text{ km}$, and capped at $800 \times 800\text{ px}$ for larger radii up to $40\text{ km}$).
- **Illumination**: Cartographic standard azimuth $315^\circ$ (NW), altitude $45^\circ$, vertical exaggeration $3.0\times$.
- **Format**: 8-bit grayscale PNG.
- **Size**: Scales with region image dimensions (up to $800 \times 800\text{ px}$), kept within the $20\text{ MB}$ total `web/data/` budget.

---

## 3. Known Limitations & Engineering Assumptions

When utilizing or interpreting this data pack, the following physical and computational limitations must be taken into account:

### 3.1 Local Near-Field Terrain Sensitivity (~100 m Baseline)
- Terrain elevation profiles within $\sim 100\text{ m}$ of the observer dominate high positive horizon angles, especially for low observer heights ($1\text{ m}$ or $5\text{ m}$).
- The calculation blends a high-resolution $20\text{ m}$ DEM window ($16\text{ km} \times 16\text{ km}$) with a downsampled $160\text{ m}$ regional DEM ($300\text{ km}$ diameter). Sub-pixel surface roughness, rocks, boulders, or micro-craters smaller than the $20\text{ m}$ DEM grid spacing are not modeled.
- Small positional shifts of even $10\text{ m}$ to $20\text{ m}$ on steep crater rims can alter horizon cutoffs by several degrees.

### 3.2 1-Degree Azimuthal Discretization
- The horizon profile is sampled into 360 integer-degree azimuth rays ($0^\circ$ to $359^\circ$).
- While sufficient for calculating disk illumination and line-of-sight communication blockage, narrow terrain notches or sharp spires narrower than $1^\circ$ azimuth may be averaged or clipped during ray marching. The client app linearly interpolates between adjacent azimuthal rays.

### 3.3 Geometric Ephemeris (No Light-Time Correction)
- SPICE position vectors are queried with `abcorr = "NONE"` (geometric positions).
- One-way light time from the Moon is $\sim 1.28\text{ s}$ to Earth and $\sim 499\text{ s}$ ($\sim 8.3\text{ minutes}$) to the Sun. At lunar orbital velocities, the apparent position change due to light-time travel is less than $0.001^\circ$, well below the solar disk diameter ($0.53^\circ$) and the horizon resolution ($0.01^\circ$). Therefore, geometric positions provide ample fidelity while ensuring simplicity and reproducibility.

### 3.4 Approximate Candidate Region Boundaries
- Region centres and per-region radii ($1\text{--}40\text{ km}$) are approximate bounds from NASA's Artemis III candidate-region map (not surveyed).
- The region circles are intended for mission planning, illumination profiling, and site comparison rather than definitive spacecraft hazard maps or formal flight boundaries.

---

## 4. Client-Side Evaluation Workflow (JavaScript / Web)

To evaluate site metrics in the static browser application:
1. **Load Manifest**: Fetch `web/data/manifest.json`.
2. **Retrieve Horizon**: Compute byte offset for site `index` and observer height `h_idx` ($0$ or $1$):
   $$\text{byte\_offset} = (\text{index} \times 2 + \text{h\_idx}) \times 360 \times 2$$
   Fetch or extract 360 `int16` values; divide by $100.0$ to recover horizon degrees.
3. **Lookup Ephemeris**: For UTC timestamp $t$, calculate time index:
   $$i = \text{round}\left(\frac{t - t_{\text{start}}}{900\text{ s}}\right)$$
   Retrieve Sun vector $\mathbf{r}_{\text{sun}}$ and Earth vector $\mathbf{r}_{\text{earth}}$ in $\text{km}$.
4. **Topocentric Projection**:
   Construct site local frame $(\hat{\mathbf{u}}, \hat{\mathbf{e}}, \hat{\mathbf{n}})$ in `MOON_ME` coordinates:
   $$\mathbf{r}_{\text{site}} = \frac{R_M + h_{\text{ground}} + h_{\text{obs}}}{1000.0} \hat{\mathbf{u}}$$
   $$\mathbf{v} = \mathbf{r}_{\text{body}} - \mathbf{r}_{\text{site}},\quad d = \|\mathbf{v}\|$$
   $$\text{az} = \text{atan2}(\mathbf{v} \cdot \hat{\mathbf{e}}, \mathbf{v} \cdot \hat{\mathbf{n}}) \pmod{360^\circ}$$
   $$\text{el} = \arcsin\left(\frac{\mathbf{v} \cdot \hat{\mathbf{u}}}{d}\right)$$
   $$r_{\text{ang}} = \arcsin\left(\frac{R_{\text{body}}}{d}\right)$$
5. **Visible Fraction**:
   Interpolate terrain horizon at $\text{az}$, evaluate normalized offset $t = (\text{el} - \text{hor}(\text{az})) / r_{\text{ang}}$, and apply the spherical cap area formula:
   $$f_{\text{vis}}(t) = \frac{\arccos(-t) + t\sqrt{1 - t^2}}{\pi}\quad (t \in [-1, 1])$$
