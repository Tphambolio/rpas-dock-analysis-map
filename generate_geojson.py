#!/usr/bin/env python3
"""
Generate all GeoJSON data files for the GitHub Pages map site.
Run from the repo root: python generate_geojson.py
"""
import json, math, os
import geopandas as gpd

SRC = '/home/rpas/Downloads'
OUT = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUT, exist_ok=True)

# ── 1. Wildland fire incidents heatmap ───────────────────────────────────────
with open(f'{SRC}/hm_WF.json') as f:
    wf = json.load(f)

fc = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature',
         'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]},
         'properties': {}}
        for r in wf if r.get('lat') and r.get('lon')
    ]
}
with open(f'{OUT}/wf_incidents.geojson', 'w') as f:
    json.dump(fc, f, separators=(',', ':'))
print(f'wf_incidents.geojson: {len(fc["features"])} points')

# ── 2. GeoPackage → GeoJSON helper ──────────────────────────────────────────
def gpkg_to_geojson(gpkg_path, layer, out_name):
    gdf = gpd.read_file(gpkg_path, layer=layer).to_crs('EPSG:4326')
    # Simplify ring geometries slightly for web (reduces file size)
    if gdf.geometry.geom_type.iloc[0] in ('Polygon', 'MultiPolygon'):
        gdf['geometry'] = gdf.geometry.simplify(0.0001, preserve_topology=True)
    path = f'{OUT}/{out_name}'
    gdf.to_file(path, driver='GeoJSON')
    print(f'{out_name}: {len(gdf)} features')

gpkg_to_geojson(f'{SRC}/existing6_stations.gpkg', 'existing6_stations', 'existing6_stations.geojson')
gpkg_to_geojson(f'{SRC}/existing6_rings.gpkg',    'existing6_rings',    'existing6_rings.geojson')
gpkg_to_geojson(f'{SRC}/optC_stations.gpkg',      'optC_stations',      'optC_stations.geojson')
gpkg_to_geojson(f'{SRC}/optC_rings.gpkg',         'optC_rings',         'optC_rings.geojson')

# ── 3. PTZ Camera stations (8 sites) ────────────────────────────────────────
CAMERAS = [
    {'name': 'Walterdale Hill',       'lat': 53.5268, 'lon': -113.4915,
     'mount': 'Telecom tower / utility structure',
     'coverage_km': 20, 'corridor': 'Downtown valley + Rossdale flats, both banks'},
    {'name': 'Mill Creek Ravine Rim', 'lat': 53.4752, 'lon': -113.5031,
     'mount': 'Utility pole cluster / park structure',
     'coverage_km': 15, 'corridor': 'Mill Creek / Whitemud confluence'},
    {'name': 'Whitemud Drive Ridge',  'lat': 53.5195, 'lon': -113.5938,
     'mount': 'Hydro transmission tower',
     'coverage_km': 18, 'corridor': 'Whitemud Creek full length'},
    {'name': 'Terwillegar Ridge',     'lat': 53.4334, 'lon': -113.6126,
     'mount': 'Park service / telecom structure',
     'coverage_km': 15, 'corridor': 'SW ravines, Terwillegar, Oleskiw'},
    {'name': 'Gold Bar / Beverly Rim','lat': 53.4957, 'lon': -113.4172,
     'mount': 'Cell tower',
     'coverage_km': 18, 'corridor': 'East valley, Rundle Park ravines'},
    {'name': 'Strathearn Heights',    'lat': 53.5211, 'lon': -113.4612,
     'mount': 'Building rooftop / hydro tower',
     'coverage_km': 15, 'corridor': 'Downtown valley east approach'},
    {'name': 'St. Albert Trail NW',   'lat': 53.5587, 'lon': -113.5441,
     'mount': 'Telecom mast',
     'coverage_km': 20, 'corridor': 'River valley NW, Big Island approach'},
    {'name': 'Victoria Trail NE',     'lat': 53.5987, 'lon': -113.3928,
     'mount': 'Cell tower',
     'coverage_km': 18, 'corridor': 'Beverly ravines, north valley'},
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

# ── 4. Gas/particulate sensor nodes ─────────────────────────────────────────
# Generate points along ravine corridor polylines at ~700m spacing.
# Points alternate floor / rim within each corridor.

def interpolate_corridor(waypoints, spacing_deg=0.006):
    """Return list of [lon, lat] at ~spacing_deg intervals along polyline."""
    pts = []
    for i in range(len(waypoints) - 1):
        lat1, lon1 = waypoints[i]
        lat2, lon2 = waypoints[i+1]
        seg_len = math.hypot(lat2-lat1, lon2-lon1)
        n = max(1, round(seg_len / spacing_deg))
        for j in range(n):
            t = j / n
            pts.append([lon1 + t*(lon2-lon1), lat1 + t*(lat2-lat1)])
    pts.append([waypoints[-1][1], waypoints[-1][0]])
    return pts

CORRIDORS = [
    {
        # River enters from west, curves east then northeast through downtown
        'name': 'North Saskatchewan Main Valley',
        'floor': [
            (53.5450, -113.6260),  # W entrance near Quesnell Bridge
            (53.5380, -113.5980),  # Laurier Park
            (53.5340, -113.5690),  # Groat Bridge
            (53.5300, -113.5440),  # McKinnon Ravine junction
            (53.5270, -113.5240),  # High Level Bridge
            (53.5220, -113.4970),  # Cloverdale / Riverdale
            (53.5270, -113.4700),  # Dawson Park — river curves N
            (53.5400, -113.4430),  # Gold Bar
            (53.5560, -113.4130),  # Beverly
            (53.5690, -113.3900),  # NE exit
        ],
        # South escarpment rim (Saskatchewan Drive / Connors Road ridge)
        'rim': [
            (53.5290, -113.6230),  # Whitemud/Wedgewood ridge top
            (53.5240, -113.5940),  # Laurier Heights rim
            (53.5210, -113.5660),  # Groat top
            (53.5190, -113.5400),  # 99 Ave escarpment
            (53.5180, -113.5200),  # Saskatchewan Drive
            (53.5150, -113.4950),  # Connors Hill
            (53.5190, -113.4680),  # Rundle rim
            (53.5300, -113.4400),  # Gold Bar rim
            (53.5440, -113.4130),  # Beverly rim
            (53.5570, -113.3940),  # NE rim
        ],
    },
    {
        # N-S ravine through Mill Creek Park, south-central Edmonton
        'name': 'Mill Creek Ravine',
        'floor': [
            (53.4770, -113.4995),  # S end near 34 Ave
            (53.4830, -113.4993),
            (53.4880, -113.4992),
            (53.4940, -113.4992),
            (53.5000, -113.4991),
            (53.5065, -113.4991),
            (53.5140, -113.4990),  # N end meets main valley near 98 Ave
        ],
        # East escarpment rim
        'rim': [
            (53.4770, -113.4890),
            (53.4830, -113.4893),
            (53.4880, -113.4895),
            (53.4940, -113.4895),
            (53.5000, -113.4894),
            (53.5065, -113.4893),
            (53.5140, -113.4892),
        ],
    },
    {
        # Flows SW→NE from Terwillegar toward Mill Creek confluence
        'name': 'Whitemud Creek',
        'floor': [
            (53.4320, -113.6110),  # SW near Terwillegar S
            (53.4380, -113.5960),  # Wedgewood
            (53.4430, -113.5800),
            (53.4490, -113.5630),
            (53.4560, -113.5460),  # Near Whitemud Drive
            (53.4620, -113.5290),
            (53.4680, -113.5140),
            (53.4740, -113.5040),  # Near valley confluence
        ],
        # NW bank rim
        'rim': [
            (53.4340, -113.6200),
            (53.4400, -113.6050),
            (53.4460, -113.5890),
            (53.4520, -113.5720),
            (53.4570, -113.5550),
            (53.4630, -113.5380),
            (53.4690, -113.5230),
            (53.4750, -113.5120),
        ],
    },
    {
        # Ravine system NE of the main valley — Rundle/Beverly ravines
        'name': 'Beverly Ravines',
        'floor': [
            (53.5530, -113.4330),  # Gold Bar ravine entrance
            (53.5590, -113.4160),
            (53.5650, -113.4000),
            (53.5710, -113.3840),
            (53.5760, -113.3680),  # Beverly NE
        ],
        # Upper escarpment
        'rim': [
            (53.5460, -113.4290),
            (53.5520, -113.4120),
            (53.5580, -113.3960),
            (53.5640, -113.3800),
            (53.5700, -113.3650),
        ],
    },
    {
        # River valley floor SW — along Terwillegar / Oleskiw bend
        'name': 'Terwillegar / Oleskiw',
        'floor': [
            (53.4510, -113.6380),  # Terwillegar park W
            (53.4450, -113.6260),
            (53.4390, -113.6150),  # Oleskiw area
            (53.4330, -113.6080),
            (53.4270, -113.6040),  # S tip of river bend
        ],
        # SW escarpment rim
        'rim': [
            (53.4500, -113.6480),
            (53.4440, -113.6360),
            (53.4380, -113.6250),
            (53.4320, -113.6180),
            (53.4260, -113.6140),
        ],
    },
]

sensor_features = []
node_id = 1
for corridor in CORRIDORS:
    for placement, waypoints in [('floor', corridor['floor']), ('rim', corridor['rim'])]:
        pts = interpolate_corridor(waypoints, spacing_deg=0.006)
        for lon, lat in pts:
            sensor_features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [round(lon, 5), round(lat, 5)]},
                'properties': {
                    'id': f'SN{node_id:03d}',
                    'corridor': corridor['name'],
                    'placement': placement,
                    'detects': 'CO, PM2.5, PM10, H₂, Temp, RH',
                    'comms': 'LoRaWAN mesh',
                    'power': 'Solar + LiFePO₄',
                    'alert_latency_min': 5,
                    'platform': 'N5-class sensor node',
                }
            })
            node_id += 1

sensor_fc = {'type': 'FeatureCollection', 'features': sensor_features}
with open(f'{OUT}/sensors.geojson', 'w') as f:
    json.dump(sensor_fc, f, separators=(',', ':'))
print(f'sensors.geojson: {len(sensor_features)} nodes')

print('\nAll GeoJSON files written to', OUT)
