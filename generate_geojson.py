#!/usr/bin/env python3
"""
Generate all GeoJSON data files for the GitHub Pages map site.
Run from the repo root: python generate_geojson.py
"""
import json, math, os, subprocess, tempfile
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from rasterio.features import shapes as rasterio_shapes
from rasterio.warp import transform_bounds
from pyproj import Transformer
from shapely.geometry import shape, mapping, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

SRC = '/home/rpas/Downloads'
OUT = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUT, exist_ok=True)

# ── 1. Wildland fire incidents heatmap ───────────────────────────────────────
with open(f'{SRC}/hm_WF.json') as f:
    wf = json.load(f)

wf_pts = [(r['lon'], r['lat']) for r in wf if r.get('lat') and r.get('lon')]
wf_lons = np.array([p[0] for p in wf_pts])
wf_lats = np.array([p[1] for p in wf_pts])

fc = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature',
         'geometry': {'type': 'Point', 'coordinates': list(p)},
         'properties': {}}
        for p in wf_pts
    ]
}
with open(f'{OUT}/wf_incidents.geojson', 'w') as f:
    json.dump(fc, f, separators=(',', ':'))
print(f'wf_incidents.geojson: {len(fc["features"])} points')

# ── 2. GeoPackage → GeoJSON helper ──────────────────────────────────────────
def gpkg_to_geojson(gpkg_path, layer, out_name):
    gdf = gpd.read_file(gpkg_path, layer=layer).to_crs('EPSG:4326')
    if gdf.geometry.geom_type.iloc[0] in ('Polygon', 'MultiPolygon'):
        gdf['geometry'] = gdf.geometry.simplify(0.0001, preserve_topology=True)
    path = f'{OUT}/{out_name}'
    gdf.to_file(path, driver='GeoJSON')
    print(f'{out_name}: {len(gdf)} features')

gpkg_to_geojson(f'{SRC}/existing6_stations.gpkg', 'existing6_stations', 'existing6_stations.geojson')
gpkg_to_geojson(f'{SRC}/existing6_rings.gpkg',    'existing6_rings',    'existing6_rings.geojson')
gpkg_to_geojson(f'{SRC}/optC_stations.gpkg',      'optC_stations',      'optC_stations.geojson')
gpkg_to_geojson(f'{SRC}/optC_rings.gpkg',         'optC_rings',         'optC_rings.geojson')

# ── 3. PTZ Camera stations + terrain-aware viewsheds ────────────────────────
#
# VIEWSHED METHOD (SRTM 30m DEM, gdal_viewshed):
#  - Observer height: 15 m above terrain (camera tower / telecom mast)
#  - Target height:   2 m (smoke near ground before it lifts)
#  - Max range:       coverage_km × 1000 m
#  - Field of view:   180° arc, auto-oriented toward nearest valley low point
#    (the camera faces the valley, not away from it)
#  - Earth curvature + atmospheric refraction correction enabled (cc=0.85)
#  - DEM: SRTM 1-arcsec (~30 m), UTM Zone 12N for accurate distance calc
#
# TERRAIN EFFECT: Edmonton's river valley is 50-70 m below the upland plateau.
# Cameras mounted on the rim see across the open valley but are blocked by the
# near escarpment wall — the ravine floor within ~200-400 m of the rim is in
# shadow. This shadow is visible as the concave notch near the camera in each
# viewshed polygon. Floor-level gas sensors cover this sub-escarpment zone.
#
# DATA SOURCE: /home/rpas/Downloads/edmonton_dem.tif (SRTM1, downloaded via
# elevation pkg from AWS elevation-tiles-prod, tile N53W114)

CAMERAS = [
    {'name': 'Walterdale Hill',       'lat': 53.5268, 'lon': -113.4915,
     'mount': 'Telecom tower / utility structure',
     'coverage_km': 8, 'corridor': 'Downtown valley + Rossdale flats, both banks'},
    {'name': 'Mill Creek Ravine Rim', 'lat': 53.4752, 'lon': -113.5031,
     'mount': 'Utility pole cluster / park structure',
     'coverage_km': 6, 'corridor': 'Mill Creek / Whitemud confluence'},
    {'name': 'Whitemud Drive Ridge',  'lat': 53.5195, 'lon': -113.5938,
     'mount': 'Hydro transmission tower',
     'coverage_km': 8, 'corridor': 'Whitemud Creek full length'},
    {'name': 'Terwillegar Ridge',     'lat': 53.4334, 'lon': -113.6126,
     'mount': 'Park service / telecom structure',
     'coverage_km': 7, 'corridor': 'SW ravines, Terwillegar, Oleskiw'},
    {'name': 'Gold Bar / Beverly Rim','lat': 53.4957, 'lon': -113.4172,
     'mount': 'Cell tower',
     'coverage_km': 8, 'corridor': 'East valley, Rundle Park ravines'},
    {'name': 'Strathearn Heights',    'lat': 53.5211, 'lon': -113.4612,
     'mount': 'Building rooftop / hydro tower',
     'coverage_km': 6, 'corridor': 'Downtown valley east approach'},
    {'name': 'St. Albert Trail NW',   'lat': 53.5587, 'lon': -113.5441,
     'mount': 'Telecom mast',
     'coverage_km': 8, 'corridor': 'River valley NW, Big Island approach'},
    {'name': 'Victoria Trail NE',     'lat': 53.5987, 'lon': -113.3928,
     'mount': 'Cell tower',
     'coverage_km': 8, 'corridor': 'Beverly ravines, north valley'},
]

cam_fc = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature',
         'geometry': {'type': 'Point', 'coordinates': [c['lon'], c['lat']]},
         'properties': {k: v for k, v in c.items() if k not in ('lat', 'lon')}}
        for c in CAMERAS
    ]
}
with open(f'{OUT}/cameras.geojson', 'w') as f:
    json.dump(cam_fc, f, indent=2)
print(f'cameras.geojson: {len(cam_fc["features"])} stations')

# ── 3a. Terrain-aware viewsheds via gdal_viewshed + SRTM 30m DEM ────────────
DEM_GEO = '/home/rpas/Downloads/edmonton_dem.tif'      # WGS84
DEM_UTM = '/home/rpas/Downloads/edmonton_dem_utm.tif'  # UTM 12N (30m)
OBS_HEIGHT = 15.0    # m above terrain (camera tower)
TGT_HEIGHT = 2.0     # m (smoke at near-ground level)
SEARCH_R_M = 2000    # m radius to find valley low point for auto-orientation
FOV_DEG    = 180     # camera field of view

to_utm   = Transformer.from_crs('EPSG:4326', 'EPSG:32612', always_xy=True)
from_utm = Transformer.from_crs('EPSG:32612', 'EPSG:4326', always_xy=True)

def valley_facing_azimuth(cam_lon, cam_lat, dem_utm_path, search_r=SEARCH_R_M):
    """
    Find the azimuth from the camera toward the lowest terrain within search_r metres.
    This auto-orients the camera toward the valley floor.
    Returns azimuth in degrees (0=N, 90=E, 180=S, 270=W).
    """
    cx, cy = to_utm.transform(cam_lon, cam_lat)
    with rasterio.open(dem_utm_path) as src:
        data = src.read(1).astype(float)
        data[data == src.nodata] = np.nan
        transform = src.transform
        res = src.res[0]  # metres/pixel (square)

        # Window around the camera
        pad = int(math.ceil(search_r / res)) + 1
        r0, c0 = rowcol(transform, cx, cy)
        r_lo = max(0, r0 - pad); r_hi = min(data.shape[0], r0 + pad + 1)
        c_lo = max(0, c0 - pad); c_hi = min(data.shape[1], c0 + pad + 1)
        window = data[r_lo:r_hi, c_lo:c_hi]

        # Build coordinate grids for the window
        rows_w = np.arange(r_lo, r_hi)
        cols_w = np.arange(c_lo, c_hi)
        cols_g, rows_g = np.meshgrid(cols_w, rows_w)
        xs, ys = rasterio.transform.xy(transform, rows_g.ravel(), cols_g.ravel())
        xs = np.array(xs).reshape(window.shape)
        ys = np.array(ys).reshape(window.shape)

        # Distance mask
        dist = np.sqrt((xs - cx)**2 + (ys - cy)**2)
        mask = (dist > 50) & (dist <= search_r) & ~np.isnan(window)

        if not mask.any():
            return 180.0  # fallback: face south

        # Lowest point within search radius
        masked_elev = np.where(mask, window, np.nan)
        idx = np.nanargmin(masked_elev)
        row_min, col_min = np.unravel_index(idx, window.shape)
        low_x, low_y = xs[row_min, col_min], ys[row_min, col_min]

        # Azimuth from camera to lowest point
        dx = low_x - cx
        dy = low_y - cy
        az = math.degrees(math.atan2(dx, dy)) % 360  # atan2(E, N) → azimuth from N
        return az

def compute_terrain_viewshed(cam_lon, cam_lat, coverage_km, dem_utm_path):
    """
    Run gdal_viewshed, mask to 180° arc toward valley, vectorize.
    Returns GeoJSON geometry (Polygon or MultiPolygon) in EPSG:4326.
    """
    max_range = coverage_km * 1000
    cx, cy = to_utm.transform(cam_lon, cam_lat)
    facing = valley_facing_azimuth(cam_lon, cam_lat, dem_utm_path)

    with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp:
        vshed_path = tmp.name

    try:
        cmd = [
            'gdal_viewshed', '-q',
            '-oz', str(OBS_HEIGHT),
            '-tz', str(TGT_HEIGHT),
            '-md', str(max_range),
            '-ox', str(cx), '-oy', str(cy),
            '-cc', '0.85',           # earth curvature + refraction (standard)
            '-vv', '1', '-iv', '0', '-ov', '0',
            dem_utm_path, vshed_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        with rasterio.open(vshed_path) as src:
            vshed  = src.read(1)
            tform  = src.transform
            nrows, ncols = vshed.shape

            # Build coordinate grids (vectorised)
            r_idx = np.arange(nrows)
            c_idx = np.arange(ncols)
            col_g, row_g = np.meshgrid(c_idx, r_idx)
            xs, ys = rasterio.transform.xy(tform, row_g.ravel(), col_g.ravel())
            xs = np.array(xs).reshape(nrows, ncols)
            ys = np.array(ys).reshape(nrows, ncols)

            # Angular mask: ±90° around facing azimuth
            dx = xs - cx; dy = ys - cy
            az_grid = np.degrees(np.arctan2(dx, dy)) % 360
            delta = np.abs(((az_grid - facing + 180) % 360) - 180)
            sector = delta <= (FOV_DEG / 2)

            visible = ((vshed == 1) & sector).astype(np.uint8)

        # Vectorise visible pixels
        polys = [shape(geom) for geom, val
                 in rasterio_shapes(visible, transform=tform) if val == 1]
        if not polys:
            return None

        merged = unary_union(polys)
        # Keep only the largest connected piece (drop tiny artefacts)
        if merged.geom_type == 'MultiPolygon':
            merged = max(merged.geoms, key=lambda g: g.area)
        # Simplify ~50m in UTM coords
        simplified = merged.simplify(50, preserve_topology=True)

        # Reproject to WGS84
        def reproject_coords(coords):
            lons, lats = from_utm.transform(
                [c[0] for c in coords], [c[1] for c in coords])
            return list(zip(lons, lats))

        def reproject_poly(poly):
            ext = reproject_coords(list(poly.exterior.coords))
            holes = [reproject_coords(list(i.coords)) for i in poly.interiors]
            return Polygon(ext, holes)

        if simplified.geom_type == 'Polygon':
            reprojected = reproject_poly(simplified)
        else:
            reprojected = unary_union([reproject_poly(p) for p in simplified.geoms])

        return mapping(reprojected)

    finally:
        if os.path.exists(vshed_path):
            os.unlink(vshed_path)

print('Computing terrain-aware viewsheds (SRTM 30m, gdal_viewshed)...')
vs_features = []
for c in CAMERAS:
    geom = compute_terrain_viewshed(c['lon'], c['lat'], c['coverage_km'], DEM_UTM)
    facing = valley_facing_azimuth(c['lon'], c['lat'], DEM_UTM)
    if geom:
        vs_features.append({
            'type': 'Feature',
            'geometry': geom,
            'properties': {
                'name':          c['name'],
                'coverage_km':   c['coverage_km'],
                'fov_deg':       FOV_DEG,
                'facing_az':     round(facing, 1),
                'obs_height_m':  OBS_HEIGHT,
                'dem_source':    'SRTM 1-arcsec (~30 m), EPSG:32612',
                'note': (
                    'Terrain-aware viewshed (180° arc toward valley). '
                    'Near-escarpment shadow visible as concave notch — '
                    'floor-level gas sensors cover this sub-escarpment zone.'
                )
            }
        })
        print(f'  {c["name"]}: facing {facing:.0f}°, geom type {geom["type"]}')
    else:
        print(f'  {c["name"]}: WARNING — no visible area computed')

vs_fc = {'type': 'FeatureCollection', 'features': vs_features}
with open(f'{OUT}/camera_viewsheds.geojson', 'w') as f:
    json.dump(vs_fc, f, separators=(',', ':'))
print(f'camera_viewsheds.geojson: {len(vs_features)} terrain viewsheds')

LAT_M = 111_000.0  # m per degree latitude (used by sensor section below)

# ── 4. Gas/particulate sensor nodes — density-weighted triangulated clusters ─
#
# DESIGN BASIS (Ucinski 2004, Nehorai 1994, IEEE WSN wildfire literature):
#
#  Linear arrays provide only 1-D gradient info → cannot triangulate a point
#  source under variable wind. Point-source localization requires ≥3 non-
#  collinear sensors. Solution: equilateral TRIANGLE triads placed within the
#  actual wildfire ignition-risk zone.
#
# ALGORITHM:
#  1. Kernel density estimate of WF incident locations → ignition probability
#     surface (uses only historical fire data — no manual corridor drawing)
#  2. Proximity filter: only cells within ~1 km of at least one WF incident
#     are eligible (clips naturally to the valley / ravine system without a
#     hard polygon boundary)
#  3. Poisson-disc weighted sampling → cluster centroids at ≥1 km separation
#  4. Equilateral triangle at each centroid (~280 m radius ≈ 485 m side):
#       Vertex A: 330° (NNW) — upwind reference, Edmonton prevailing NW flow
#       Vertex B:  90° (E)   — primary downwind detector for NW plumes
#       Vertex C: 210° (SSW) — Chinook (SW) plume + crosswind triangulation
#
# Physical basis: the NNW/E/SSW triangle covers the two dominant Edmonton
# wind quadrants (NW Arctic outflow, SW Chinook) while maintaining the
# non-collinearity required for 2-D source triangulation. Floor-level nodes
# detect CO/PM2.5 co-spike before smoke exits the ravine; rim-level nodes
# cross-validate and provide gradient data for source estimation.

# ── 4a. WF density grid ─────────────────────────────────────────────────────
LON_MIN, LON_MAX = -113.650, -113.370
LAT_MIN, LAT_MAX =  53.415,   53.605
GRID_RES = 0.005          # ~400 m grid cells

lon_c = np.arange(LON_MIN + GRID_RES/2, LON_MAX, GRID_RES)
lat_c = np.arange(LAT_MIN + GRID_RES/2, LAT_MAX, GRID_RES)
GLON, GLAT = np.meshgrid(lon_c, lat_c)      # (nlat, nlon)

# Count WF incidents within ~1.1 km of each cell centre
KDE_R = 0.012   # degrees ≈ 1.1 km at 53.5°N (lon-corrected: ~720 m E-W, 1.33 km N-S)
dists = np.hypot(
    GLON[np.newaxis] - wf_lons[:, np.newaxis, np.newaxis],
    GLAT[np.newaxis] - wf_lats[:, np.newaxis, np.newaxis]
)                                             # (n_wf, nlat, nlon)
density = (dists < KDE_R).sum(axis=0).astype(float)

# Light 3×3 box smoothing to spread density slightly across cell boundaries
pad = np.pad(density, 1, mode='edge')
smooth = sum(pad[di:di+density.shape[0], dj:dj+density.shape[1]]
             for di in range(3) for dj in range(3)) / 9.0

# Proximity filter: cluster centroid must be within ~1.1 km of a WF incident
# (dists already computed; check per-cell minimum)
min_wf_dist = dists.min(axis=0)              # (nlat, nlon) minimum dist to any WF pt

# ── 4b. Poisson-disc weighted sampling ──────────────────────────────────────
DENSITY_THRESH  = smooth.max() * 0.12  # top 88% of density
PROXIMITY_THRESH = 0.013               # ≤ ~1.1 km from a WF incident
MIN_SEP = 0.012                        # ≥ ~1 km between cluster centres
N_CLUSTERS = 28
SEED = 42

flat = smooth.ravel()
valid_mask = (flat > DENSITY_THRESH) & (min_wf_dist.ravel() < PROXIMITY_THRESH)
valid_idx = np.where(valid_mask)[0]
if len(valid_idx) < 5:           # fallback: relax proximity
    valid_idx = np.where(flat > DENSITY_THRESH)[0]

weights = flat[valid_idx]
weights /= weights.sum()

rng = np.random.default_rng(SEED)
clusters = []

for _ in range(200_000):
    if len(clusters) >= N_CLUSTERS:
        break
    pick = rng.choice(len(valid_idx), p=weights)
    fi = valid_idx[pick]
    row, col = divmod(fi, len(lon_c))
    lon = float(lon_c[col]) + rng.uniform(-GRID_RES/2, GRID_RES/2)
    lat = float(lat_c[row]) + rng.uniform(-GRID_RES/2, GRID_RES/2)
    if clusters and min(math.hypot(lon-cx, lat-cy) for cx, cy in clusters) < MIN_SEP:
        continue
    clusters.append((lon, lat))

print(f'  sensor cluster centroids: {len(clusters)}')

# ── 4c. Equilateral triangle triads ─────────────────────────────────────────
# Triangle radius ~280 m from centroid → side ≈ 485 m
# Orientation tuned to Edmonton wind climatology:
#   NNW vertex (330°): upwind reference for prevailing NW/W flow
#   E   vertex ( 90°): primary detector — NW plume goes eastward
#   SSW vertex (210°): catches SW Chinook plume + provides E-W crosswind info
TR_M = 280                                    # m from centroid to vertex
TR_LAT = TR_M / LAT_M
TR_LON = TR_M / (LAT_M * math.cos(math.radians(53.5)))

VERTICES = [
    (330, 'upwind',   'NNW — upwind reference (prevailing NW flow)'),
    ( 90, 'downwind', 'E   — primary downwind detector (NW plume)'),
    (210, 'downwind', 'SSW — Chinook / crosswind detector'),
]

sensor_features = []
node_id = 1

for ci, (clon, clat) in enumerate(clusters):
    cid = f'C{ci+1:02d}'
    for angle_deg, placement, role in VERTICES:
        a = math.radians(angle_deg)
        sensor_features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [
                round(clon + TR_LON * math.sin(a), 5),
                round(clat + TR_LAT * math.cos(a), 5)
            ]},
            'properties': {
                'id':               f'SN{node_id:03d}',
                'cluster':          cid,
                'placement':        placement,
                'role':             role,
                'detects':          'CO, PM2.5, PM10, H\u2082, Temp, RH',
                'comms':            'LoRaWAN mesh',
                'power':            'Solar + LiFePO\u2084',
                'alert_latency_min': 5,
                'platform':         'N5-class sensor node',
            }
        })
        node_id += 1

sensor_fc = {'type': 'FeatureCollection', 'features': sensor_features}
with open(f'{OUT}/sensors.geojson', 'w') as f:
    json.dump(sensor_fc, f, separators=(',', ':'))
print(f'sensors.geojson: {len(sensor_features)} nodes ({len(clusters)} clusters × 3 vertices)')

print('\nAll GeoJSON files written to', OUT)
