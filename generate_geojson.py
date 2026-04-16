#!/usr/bin/env python3
"""
Generate all GeoJSON data files for the GitHub Pages map site.
Run from the repo root: python generate_geojson.py
"""
import json, math, os
import numpy as np
import geopandas as gpd

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

# ── 3. PTZ Camera stations + cone viewsheds ──────────────────────────────────
#
# VIEWSHED METHOD: pie-slice wedge polygons oriented toward the valley.
# Each camera has a hardcoded facing azimuth based on Edmonton geography
# (NSR valley orientation + ravine alignments from 1:50,000 topo).
# 60° FOV matches IQ FireWatch pan speed and typical panoramic sector sweep.
# Range = coverage_km × 1000 m (manufacturer-rated at clear-air conditions).

LAT_M = 111_000.0  # m per degree latitude

def wedge_polygon(lon, lat, facing_az, fov_deg=60, range_m=5000, n_arc=24):
    """
    Pie-slice GeoJSON Polygon centred at (lon, lat).
    facing_az: bearing from N clockwise (0=N, 90=E, 180=S, 270=W).
    Returns GeoJSON Polygon geometry dict.
    """
    lon_m = LAT_M * math.cos(math.radians(lat))
    half  = fov_deg / 2.0
    coords = [[lon, lat]]
    for i in range(n_arc + 1):
        az_rad = math.radians(facing_az - half + fov_deg * i / n_arc)
        coords.append([
            round(lon + range_m / lon_m * math.sin(az_rad), 6),
            round(lat + range_m / LAT_M * math.cos(az_rad), 6)
        ])
    coords.append([lon, lat])
    return {'type': 'Polygon', 'coordinates': [coords]}

CAMERAS = [
    # Facing azimuths oriented toward river valley / ravine system
    # (0=N, 90=E — clockwise from north)
    {'name': 'Walterdale Hill',       'lat': 53.5268, 'lon': -113.4915,
     'facing_az': 355,   # NNW — north bank from south-side telecom structure
     'mount': 'Telecom tower / utility structure',
     'coverage_km': 8, 'corridor': 'Downtown valley + Rossdale flats, both banks'},
    {'name': 'Mill Creek Ravine Rim', 'lat': 53.4752, 'lon': -113.5031,
     'facing_az': 340,   # NNW — up ravine toward NSR confluence
     'mount': 'Utility pole cluster / park structure',
     'coverage_km': 6, 'corridor': 'Mill Creek / Whitemud confluence'},
    {'name': 'Whitemud Drive Ridge',  'lat': 53.5195, 'lon': -113.5938,
     'facing_az': 135,   # SE — toward Whitemud Creek corridor
     'mount': 'Hydro transmission tower',
     'coverage_km': 8, 'corridor': 'Whitemud Creek full length'},
    {'name': 'Terwillegar Ridge',     'lat': 53.4334, 'lon': -113.6126,
     'facing_az': 50,    # NE — toward river valley and Terwillegar Park
     'mount': 'Park service / telecom structure',
     'coverage_km': 7, 'corridor': 'SW ravines, Terwillegar, Oleskiw'},
    {'name': 'Gold Bar / Beverly Rim','lat': 53.4957, 'lon': -113.4172,
     'facing_az': 300,   # WNW — toward NSR east valley and Rundle ravines
     'mount': 'Cell tower',
     'coverage_km': 8, 'corridor': 'East valley, Rundle Park ravines'},
    {'name': 'Strathearn Heights',    'lat': 53.5211, 'lon': -113.4612,
     'facing_az': 330,   # NNW — toward downtown valley and north bank
     'mount': 'Building rooftop / hydro tower',
     'coverage_km': 6, 'corridor': 'Downtown valley east approach'},
    {'name': 'St. Albert Trail NW',   'lat': 53.5587, 'lon': -113.5441,
     'facing_az': 145,   # SE — toward NSR valley from NW upland
     'mount': 'Telecom mast',
     'coverage_km': 8, 'corridor': 'River valley NW, Big Island approach'},
    {'name': 'Victoria Trail NE',     'lat': 53.5987, 'lon': -113.3928,
     'facing_az': 225,   # SW — toward Beverly ravines and NSR valley
     'mount': 'Cell tower',
     'coverage_km': 8, 'corridor': 'Beverly ravines, north valley'},
]

cam_fc = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature',
         'geometry': {'type': 'Point', 'coordinates': [c['lon'], c['lat']]},
         'properties': {k: v for k, v in c.items()
                        if k not in ('lat', 'lon', 'facing_az')}}
        for c in CAMERAS
    ]
}
with open(f'{OUT}/cameras.geojson', 'w') as f:
    json.dump(cam_fc, f, indent=2)
print(f'cameras.geojson: {len(cam_fc["features"])} stations')

vs_features = []
for c in CAMERAS:
    geom = wedge_polygon(c['lon'], c['lat'], c['facing_az'],
                         fov_deg=60, range_m=c['coverage_km'] * 1000)
    vs_features.append({
        'type': 'Feature',
        'geometry': geom,
        'properties': {
            'name':        c['name'],
            'coverage_km': c['coverage_km'],
            'fov_deg':     60,
            'facing_az':   c['facing_az'],
            'corridor':    c['corridor'],
        }
    })
    print(f'  {c["name"]}: {c["facing_az"]}° facing, {c["coverage_km"]} km range')

vs_fc = {'type': 'FeatureCollection', 'features': vs_features}
with open(f'{OUT}/camera_viewsheds.geojson', 'w') as f:
    json.dump(vs_fc, f, indent=2)
print(f'camera_viewsheds.geojson: {len(vs_features)} cone viewsheds')

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
