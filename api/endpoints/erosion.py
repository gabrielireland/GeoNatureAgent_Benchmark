"""Erosion data endpoints — serves spectral index zonal statistics.

Reads the pre-computed Parquet from GCS (cached locally with TTL) and
provides timeseries, ranking, and municipality listing endpoints.

These endpoints are stateless and horizontally scalable — the Parquet
is the only data dependency.
"""

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/erosion", tags=["erosion"])

# ----------------------------------------
# Parquet Cache
# ----------------------------------------

_PARQUET_BUCKET = os.getenv("PARQUET_BUCKET", "geonatureagent_benchmark")
_PARQUET_BLOB = os.getenv("PARQUET_BLOB", "data/murcia/indices/murcia_zonal_stats.parquet")
_CACHE_TTL_SECONDS = 3600  # 1 hour

_df_cache: Optional[pd.DataFrame] = None
_df_cache_ts: float = 0.0
_df_cache_lock = threading.Lock()


def _load_parquet() -> pd.DataFrame:
    """Load the zonal stats Parquet, with local file cache and TTL."""
    global _df_cache, _df_cache_ts

    now = time.time()
    if _df_cache is not None and (now - _df_cache_ts) < _CACHE_TTL_SECONDS:
        return _df_cache

    with _df_cache_lock:
        # Double-check after acquiring lock
        now = time.time()
        if _df_cache is not None and (now - _df_cache_ts) < _CACHE_TTL_SECONDS:
            return _df_cache

        # Prefer the parquet bundled with the repo (api/data/) so reproduction needs no GCS.
        bundled = Path(__file__).resolve().parents[1] / "data" / "murcia_zonal_stats.parquet"
        if bundled.exists():
            df = pd.read_parquet(bundled)
            _df_cache = df
            _df_cache_ts = time.time()
            logger.info("Parquet loaded from bundled file: %d rows, %d columns", len(df), len(df.columns))
            return df

        local_path = Path(tempfile.gettempdir()) / "murcia_zonal_stats.parquet"

        # Try GCS download (only when the bundled file is absent)
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(_PARQUET_BUCKET)
            blob = bucket.blob(_PARQUET_BLOB)
            blob.download_to_filename(str(local_path))
            logger.info("Downloaded Parquet from gs://%s/%s", _PARQUET_BUCKET, _PARQUET_BLOB)
        except Exception as exc:
            # Fall back to existing local file if available
            if local_path.exists():
                logger.warning("GCS download failed, using cached local file: %s", exc)
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Erosion data not available: {exc}",
                )

        df = pd.read_parquet(local_path)
        _df_cache = df
        _df_cache_ts = time.time()
        logger.info("Parquet loaded: %d rows, %d columns", len(df), len(df.columns))
        return df


# ----------------------------------------
# Month ordering for consistent sorting
# ----------------------------------------

MONTH_ORDER = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_RANK = {m: i for i, m in enumerate(MONTH_ORDER)}

# Valid index names
VALID_INDICES = {"ndvi", "bsi", "ndwi", "ndbi", "msi", "savi", "nbr", "fvc"}


def _validate_index(index: str) -> str:
    if index not in VALID_INDICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid index '{index}'. Valid: {sorted(VALID_INDICES)}",
        )
    return index


# ----------------------------------------
# Endpoints
# ----------------------------------------


@router.get("/timeseries")
async def timeseries(
    municipality: str = Query(..., description="Municipality name (e.g., 'Lorca')"),
    index: str = Query(..., description="Spectral index (e.g., 'bsi', 'ndvi')"),
    year_start: int = Query(2018, description="Start year"),
    year_end: int = Query(2025, description="End year"),
):
    """Get monthly timeseries of a spectral index for a municipality."""
    _validate_index(index)
    df = _load_parquet()

    # Case-insensitive municipality match
    mask = df["nombre"].str.lower() == municipality.lower()
    if not mask.any():
        # Try partial match
        mask = df["nombre"].str.lower().str.contains(municipality.lower(), na=False)
    if not mask.any():
        available = sorted(df["nombre"].unique().tolist())
        raise HTTPException(
            status_code=404,
            detail=f"Municipality '{municipality}' not found. Available: {available[:10]}...",
        )

    subset = df[mask & (df["year"] >= year_start) & (df["year"] <= year_end)].copy()
    subset["_month_rank"] = subset["month"].map(MONTH_RANK)
    subset = subset.sort_values(["year", "_month_rank"])

    # Select relevant columns
    stat_cols = [f"{index}_{s}" for s in ("mean", "std", "p10", "p50", "p90")]
    result_cols = ["nombre", "year", "month"] + [c for c in stat_cols if c in subset.columns] + ["pixel_count"]
    result = subset[result_cols].to_dict(orient="records")

    return {
        "municipality": subset["nombre"].iloc[0] if len(subset) > 0 else municipality,
        "index": index,
        "year_range": [year_start, year_end],
        "count": len(result),
        "data": result,
    }


@router.get("/ranking")
async def ranking(
    index: str = Query(..., description="Spectral index (e.g., 'bsi')"),
    year: int = Query(2024, description="Year to rank"),
    aggregation: str = Query("annual", description="'annual' or specific month (e.g., 'jun')"),
    limit: int = Query(45, description="Max results"),
):
    """Rank municipalities by a spectral index value."""
    _validate_index(index)
    df = _load_parquet()

    subset = df[df["year"] == year].copy()
    if subset.empty:
        raise HTTPException(status_code=404, detail=f"No data for year {year}")

    mean_col = f"{index}_mean"
    if mean_col not in subset.columns:
        raise HTTPException(status_code=400, detail=f"Column {mean_col} not found")

    if aggregation == "annual":
        # Average across all months for the year
        agg = subset.groupby("nombre")[mean_col].mean().reset_index()
    else:
        month_data = subset[subset["month"] == aggregation.lower()]
        if month_data.empty:
            raise HTTPException(status_code=404, detail=f"No data for month '{aggregation}'")
        agg = month_data[["nombre", mean_col]].copy()

    agg = agg.sort_values(mean_col, ascending=False).head(limit)
    agg["rank"] = range(1, len(agg) + 1)

    return {
        "index": index,
        "year": year,
        "aggregation": aggregation,
        "count": len(agg),
        "data": agg.rename(columns={mean_col: f"{index}_mean"}).to_dict(orient="records"),
    }


@router.get("/municipalities")
async def municipalities():
    """List all municipalities with their latest available stats."""
    df = _load_parquet()

    # Get the latest year with data
    latest_year = df["year"].max()
    latest = df[df["year"] == latest_year]

    # Annual average for each municipality
    numeric_cols = [c for c in latest.columns if any(c.endswith(s) for s in ("_mean", "_std", "_p10", "_p50", "_p90"))]
    agg = latest.groupby(["cod_municipio", "nombre"])[numeric_cols].mean().reset_index()

    return {
        "year": int(latest_year),
        "count": len(agg),
        "municipalities": agg.to_dict(orient="records"),
    }
