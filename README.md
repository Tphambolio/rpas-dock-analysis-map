# Edmonton EFRS RPAS Network — Interactive Map

**Live site:** https://tphambolio.github.io/rpas-dock-analysis-map/

Interactive GitHub Pages map showing the Edmonton Fire Rescue Services drone dock placement analysis, PTZ camera station proposals, and gas/particulate sensor network design for the river valley and ravine system.

## Pages

| Page | Description |
|------|-------------|
| `index.html` | Interactive MapLibre GL map with toggleable layers |
| `methodology.html` | Full analysis methodology, configuration comparison, and placement report links |

## Layers

- **Wildland Fire Incidents** — 1,110 historical WF incident heatmap
- **Existing Dock Network (6)** — Six currently deployed M4TD dock stations with T1/T2/T3 coverage rings
- **Option C — Fixed 6 + Best 5** — Recommended 11-dock configuration (greedy optimised)
- **PTZ Camera Stations** — 8 proposed IQ FireWatch panoramic camera sites
- **Gas / Particulate Sensors** — ~156 proposed N5 sensor nodes along 5 ravine corridors

## Data Generation

```bash
pip install geopandas shapely
python generate_geojson.py
```

Reads source GeoPackages and JSON from `/home/rpas/Downloads/` and writes all GeoJSON to `data/`.

## Tech Stack

- MapLibre GL JS v3 — map rendering
- OpenFreeMap — free vector tile basemap
- GeoPandas — GeoPackage → GeoJSON conversion
- DJI M4TD — drone-in-a-box platform
- IQ FireWatch — PTZ camera system
- N5 Sensors — gas / particulate detection nodes

## Analysis Code

Full Python analysis pipeline (demand weighting, greedy set-cover, PDF/DOCX report builders):

**City of Edmonton GitLab (internal):**
`git.edmonton.ca/opm-operation-performance-and-analytics/rpas-dock-analysis`

---

City of Edmonton · EFRS RPAS Program · Analysis v3.0 · April 2026
