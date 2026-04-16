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
        'name': 'Mill Creek Ravine',
        'floor': [(53.4885, -113.5060), (53.4870, -113.5045), (53.4842, -113.5022),
                  (53.4810, -113.5010), (53.4785, -113.5005), (53.4760, -113.5020)],
        'rim':   [(53.4900, -113.5080), (53.4865, -113.5060), (53.4835, -113.5040),
                  (53.4808, -113.5030), (53.4780, -113.5025), (53.4755, -113.5038)],
    },
    {
        'name': 'Whitemud Creek',
        'floor': [(53.5190, -113.5920), (53.5150, -113.5860), (53.5100, -113.5750),
                  (53.5050, -113.5650), (53.4990, -113.5550), (53.4920, -113.5430),
                  (53.4860, -113.5310), (53.4800, -113.5190)],
        'rim':   [(53.5200, -113.5950), (53.5160, -113.5880), (53.5110, -113.5770),
                  (53.5060, -113.5670), (53.5000, -113.5570), (53.4930, -113.5450),
                  (53.4870, -113.5330), (53.4810, -113.5210)],
    },
    {
        'name': 'North Saskatchewan Main Valley',
        'floor': [(53.5480, -113.6200), (53.5460, -113.5900), (53.5430, -113.5600),
                  (53.5390, -113.5300), (53.5340, -113.5000), (53.5290, -113.4700),
                  (53.5260, -113.4400), (53.5230, -113.4100), (53.5200, -113.3800)],
        'rim':   [(53.5510, -113.6220), (53.5490, -113.5920), (53.5460, -113.5620),
                  (53.5420, -113.5320), (53.5370, -113.5020), (53.5320, -113.4720),
                  (53.5290, -113.4420), (53.5260, -113.4120), (53.5230, -113.3820)],
    },
    {
        'name': 'Beverly Ravines',
        'floor': [(53.5620, -113.4250), (53.5680, -113.4080), (53.5740, -113.3920),
                  (53.5800, -113.3780)],
        'rim':   [(53.5640, -113.4270), (53.5700, -113.4100), (53.5760, -113.3940),
                  (53.5820, -113.3800)],
    },
    {
        'name': 'Terwillegar / Oleskiw',
        'floor': [(53.4380, -113.6020), (53.4420, -113.6180), (53.4470, -113.6310),
                  (53.4520, -113.6380)],
        'rim':   [(53.4360, -113.6000), (53.4400, -113.6160), (53.4450, -113.6290),
                  (53.4500, -113.6360)],
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
