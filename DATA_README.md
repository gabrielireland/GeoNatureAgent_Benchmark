# GeoNatureAgent Benchmark — Data Archive

This document describes every file in the GeoNatureAgent Benchmark **dataset** record
(Zenodo concept DOI `10.5281/zenodo.20450995`) and how each maps onto the paths the
self-hostable API expects. Together with the **software** record
(`10.5281/zenodo.20450997`) it is sufficient to reproduce the experiments from zero
context — see `REPRODUCIBILITY.md`.

## Indicator rasters (COGs)

Place both under `api/data/cogs/` (the API resolves them there). `scripts/download_data.sh`
does this automatically.

### `co2_spain.tif` — CO₂ absorption suitability (Spain)
| Property | Value |
|---|---|
| Indicator key | `co2_spain_legislation` / year `2026` / season `annual` |
| Format | Cloud-Optimized GeoTIFF, single band, `uint8` |
| CRS | EPSG:3035 (ETRS89-LAEA Europe) |
| Resolution | 100 m |
| Dimensions | 26,536 × 17,546 |
| NoData | 255 |
| Values | `0` = Not Eligible, `1` = Eligible with Conditions, `2` = Eligible (3 classes) |
| Source | MITECO legislative pre-screening criteria (RD 214/2025), processed by the authors |

### `gully_europe.tif` — Gully erosion probability (Europe)
| Property | Value |
|---|---|
| Indicator key | `rf_gully_probability` / year `2022` / season `annual` |
| Format | Cloud-Optimized GeoTIFF, single band, `float32` |
| CRS | ETRS89-LAEA (EPSG:3035) |
| Resolution | 100 m |
| Dimensions | 38,912 × 38,823 |
| NoData | 256 |
| Values | 0–100 (percent probability of gully presence) |
| Source | JRC LUCAS 2022 Gully Erosion Survey + a Random Forest model trained by the authors |

## Tabular / JSON data

| File | Description |
|---|---|
| `benchmark_v5_tasks.json` / `tasks.jsonl` | The 93 benchmark tasks (18 categories). Maps to `geoagentbench/cases/benchmark_v5.json`. |
| `bigearthnet_portugal_stats.json` | 7-class land-cover distribution per Portuguese district (BigEarthNet V2). Maps to `api/data/bigearthnet_portugal_stats.json`. |
| `results_per_case.jsonl` | 1,860 per-(model × case × seed) scored results for the 7 final models. Reproduces the leaderboard. |
| `leaderboard.csv`, `per_category.csv`, `per_case.csv` | Compiled results — the single source of truth for every number in the paper. |
| `sources.yaml` | Manifest mapping each leaderboard cell to its Cloud Run output directory. |
| `admin_boundaries.zip` | Spanish autonomous communities / municipalities and Portuguese districts (GeoJSON). Unzips to `api/data/`. Defines the AOIs for zonal statistics. |
| `raw_traces.zip` | *(Added in a subsequent version.)* Full raw agent conversation logs (`*.jsonl`) from the experiment runs — the deepest reproducibility layer behind the scored results. Not required to re-run the benchmark; provided for audit of the original runs. |

## Third-party source datasets (cited, not redistributed)

- **BigEarthNet V2** — Clasen et al. 2024 (CDLA-Permissive-1.0). https://bigearth.net
- **LUCAS 2022 Gully Erosion Survey** — ESDAC / JRC. https://esdac.jrc.ec.europa.eu/content/gully-erosion-europe-lucas-2022
- **MITECO** carbon-footprint registry criteria (RD 214/2025).
- **Sentinel-2 / Copernicus** imagery.

## Reproduction

1. `scripts/download_data.sh` (fetches the two COGs into `api/data/cogs/`).
2. `unzip admin_boundaries.zip -d api/data/` if not already present in the repo.
3. Follow `REPRODUCIBILITY.md` (Docker API → `python -m geoagentbench`).

## License

Data: CC-BY-4.0. Code (software record): Apache-2.0.
