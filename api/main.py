"""
GeoNatureAgent API
FastAPI backend — QGIS ↔ Claude bridge for the GeoNature benchmark platform.

No authentication required — internal benchmark platform.

Dependency Breakdown:
- fastapi: Core web framework for API endpoints and request handling.
- uvicorn: ASGI server for running the application in production/dev.
- pydantic: Data validation and schema definition for requests/responses.
- google-cloud-storage: Generates signed URLs for secure GCS file access.
- rio-tiler: Reads bounds from Cloud Optimized GeoTIFFs (COGs).
- numpy: Efficient numerical array operations for raster data processing.
- rasterio: Low-level IO for geospatial raster data and coordinate warping.
"""

import logging
import os
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pathlib import Path

from cache_manager import get_cache_manager
from symbology.registry import get_symbology, get_legend_items
from services.tile_tenant import filter_layers_by_access

try:
    from rio_tiler.io import COGReader
except Exception:
    COGReader = None

logger = logging.getLogger(__name__)

try:
    import numpy as np
except Exception:
    np = None

try:
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.mask import mask as rio_mask
    from rasterio.errors import RasterioIOError
    from rasterio.warp import transform_geom
except Exception:
    rasterio = None
    MemoryFile = None
    rio_mask = None
    RasterioIOError = None
    transform_geom = None


# ========================================
# Configuration
# ========================================

LOCAL_DEV_MODE = os.getenv("LOCAL_DEV_MODE", "true").lower() == "true"
PROJECT_ID = os.getenv("GCP_PROJECT", "")
REGION = os.getenv("GCP_REGION", "europe-southwest1")
BUCKET_TILES = os.getenv("BUCKET_TILES", "")
WGS84_CRS = "EPSG:4326"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# GDAL configuration for cloud storage
GDAL_CONFIG = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.cog",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_VERSION": "2",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "536870912",
    "GDAL_CACHEMAX": 512,
}

for key, value in GDAL_CONFIG.items():
    os.environ.setdefault(key, str(value))


# GCS access-token helper for authenticated URLs.
_gcs_access_token: Optional[str] = None
_gcs_token_expires = 0.0
_gcs_token_lock = threading.Lock()


def _get_gcs_access_token() -> Optional[str]:
    """Get a valid GCS access token, refreshing if needed."""
    global _gcs_access_token, _gcs_token_expires
    if LOCAL_DEV_MODE:
        return None
    now = time.time()
    if _gcs_access_token and now < _gcs_token_expires - 120:
        return _gcs_access_token
    with _gcs_token_lock:
        now = time.time()
        if _gcs_access_token and now < _gcs_token_expires - 120:
            return _gcs_access_token
        try:
            import google.auth
            import google.auth.transport.requests
            credentials, _ = google.auth.default()
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            _gcs_access_token = credentials.token
            _gcs_token_expires = now + 3480
            logger.info("GCS access token refreshed")
            return _gcs_access_token
        except Exception as e:
            logger.error(f"Failed to refresh GCS access token: {e}")
            return _gcs_access_token


# Open-source build: no GCS-signed-URL handling. LOCAL_DEV_MODE always serves
# layers from the local filesystem; the helper below is kept as a minimal
# fallback used only if a caller passes a gs:// URL directly.
def _gs_to_authenticated_url(gs_uri: str) -> str:
    without_prefix = gs_uri[5:]
    bucket, _, blob_path = without_prefix.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{blob_path}"


def _get_gdal_header_file() -> Optional[str]:
    """Get path to a GDAL header file containing Authorization header."""
    token = _get_gcs_access_token()
    if not token:
        return None
    header_path = "/tmp/gdal_auth_header.txt"
    try:
        with open(header_path, "w") as f:
            f.write(f"Authorization: Bearer {token}\n")
        return header_path
    except Exception as e:
        logger.error(f"Failed to write GDAL header file: {e}")
        return None


if LOCAL_DEV_MODE:
    print("=" * 60)
    print("LOCAL DEVELOPMENT MODE ENABLED")
    print("   Using local files from .local-dev/")
    print("=" * 60)


def _require_admin_token(request: Request) -> None:
    """Raise 403 if the request does not carry a valid admin token."""
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin operations are disabled")
    token = request.headers.get("X-Admin-Token", "")
    if not token or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin access denied")


# ========================================
# FastAPI App
# ========================================

app = FastAPI(
    title="GeoNatureAgent API",
    description="QGIS ↔ Claude bridge for the GeoNature benchmark platform",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ========================================
# Startup: pre-warm caches
# ========================================

_gdal_env_ctx: Optional[Any] = None


@app.on_event("startup")
async def _startup():
    """Pre-warm expensive resources so the first real request is fast."""
    global _gdal_env_ctx

    if rasterio is not None:
        _gdal_env_ctx = rasterio.Env(**GDAL_CONFIG)
        _gdal_env_ctx.__enter__()
        logger.info("Persistent GDAL environment activated")

    try:
        from symbology.registry import load_catalog
        load_catalog()
        logger.info("Symbology catalog pre-loaded at startup")
    except Exception as exc:
        logger.warning(f"Symbology pre-load failed (will retry on first request): {exc}")


# ========================================
# Request/Response Models
# ========================================


class HealthResponse(BaseModel):
    status: str
    timestamp: str


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="User question in natural language")
    aoi: Optional[Dict[str, Any]] = Field(None, description="GeoJSON geometry for the area of interest")
    session_id: Optional[str] = Field(None, max_length=64, description="Session ID for conversation memory")


class IndicatorsRequest(BaseModel):
    indicator: str
    year: str
    season: str
    geometry: Dict[str, Any] = Field(..., description="GeoJSON geometry for zonal stats")


# ========================================
# COG helpers
# ========================================


def _resolve_cog_source(
    indicator: str | None,
    year: str | None,
    season: str | None,
) -> str:
    """Resolve a COG gs:// URI or local path for a given layer."""
    if not indicator or year is None or not season:
        raise HTTPException(status_code=400, detail="Missing indicator/year/season")
    cache = get_cache_manager()
    layer_info = cache.get_layer_info(indicator, str(year), season)
    if not layer_info:
        raise HTTPException(status_code=404, detail="Layer not found or unavailable")
    tile_url = cache.get_tile_url(indicator, year, season)
    if not tile_url:
        raise HTTPException(status_code=404, detail="Layer not found or unavailable")
    if LOCAL_DEV_MODE:
        return tile_url
    if tile_url.startswith("gs://"):
        header_file = _get_gdal_header_file()
        if header_file:
            os.environ["GDAL_HTTP_HEADER_FILE"] = header_file
        return f"/vsicurl/{_gs_to_authenticated_url(tile_url)}"
    return tile_url


@lru_cache(maxsize=128)
def get_cog_bounds_cached(src: str) -> Optional[Tuple[float, float, float, float]]:
    if COGReader is None:
        return None
    try:
        with COGReader(src) as cog:
            return cog.geographic_bounds
    except Exception:
        return None


# ========================================
# API Endpoints
# ========================================


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/cache/status")
async def cache_status():
    """Get cache status and statistics."""
    try:
        cache = get_cache_manager()
        stats = cache.get_statistics()
        return {"cache_available": True, "statistics": stats}
    except Exception as e:
        return {"cache_available": False, "error": str(e)}


@app.get("/cache/layers")
async def cache_layers():
    """List all available layers in cache."""
    try:
        cache = get_cache_manager()
        indicators = cache.list_available_indicators()
        layers_info = []
        for indicator in indicators:
            years = cache.list_available_years(indicator)
            for year in years:
                seasons = cache.list_available_seasons(indicator, year)
                for season in seasons:
                    layer_info = cache.get_layer_info(indicator, year, season)
                    if not layer_info:
                        continue
                    layers_info.append({
                        "indicator": indicator, "year": year, "season": season,
                        "available": layer_info.get("available", False),
                        "tile_count": layer_info.get("tile_count", 0),
                        "metadata": layer_info.get("metadata"),
                        "access_tier": layer_info.get("access_tier", "guest"),
                    })
        return {"total_layers": len(layers_info), "layers": layers_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving cache layers: {str(e)}")


@app.get("/cache/layer-url")
async def cache_layer_url(indicator: str, year: str, season: str):
    """Return the GCS URI for a given layer (for QGIS direct access)."""
    cache = get_cache_manager()
    tile_url = cache.get_tile_url(indicator, year, season)
    if not tile_url:
        raise HTTPException(status_code=404, detail="Layer not found or unavailable")
    return {"url": tile_url, "indicator": indicator, "year": year, "season": season}


@app.post("/cache/refresh")
async def cache_refresh(request: Request):
    """Force refresh of cache index. Requires X-Admin-Token header."""
    _require_admin_token(request)
    cache = get_cache_manager()
    cache.refresh()
    return {"status": "success", "message": "Cache index refreshed"}


@app.get("/legend")
def legend(indicator: str, year: str | None = None, season: str | None = None):
    """Return the legend for a given indicator."""
    items = get_legend_items(indicator)
    return {"indicator": indicator, "year": year, "season": season, "items": items}


@app.get("/cog/bounds")
def cog_bounds(indicator: str | None = None, year: str | None = None, season: str | None = None):
    """Return COG bounds in WGS84."""
    if COGReader is None:
        raise HTTPException(status_code=500, detail="rio-tiler/rasterio not installed on API")
    src = _resolve_cog_source(indicator, year, season)
    if LOCAL_DEV_MODE and src and not str(src).startswith("http"):
        p = Path(src)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"COG not found: {p}")
    bounds = get_cog_bounds_cached(src)
    if not bounds:
        raise HTTPException(status_code=404, detail="Could not read COG bounds")
    return {"bounds": list(bounds), "crs": "EPSG:4326"}


async def _run_analyze_area(indicator: str, year: str, season: str, geometry: Dict) -> Dict:
    """Shared helper: run zonal statistics via exec_analyze_area."""
    from agent.tools.executors import exec_analyze_area
    cache = get_cache_manager()
    return await run_in_threadpool(
        lambda: exec_analyze_area(indicator, year, season, geometry, cache)
    )


@app.post("/indicators")
async def indicators(request_data: IndicatorsRequest):
    """Zonal statistics for an indicator over a geometry."""
    result = await _run_analyze_area(
        request_data.indicator, request_data.year, request_data.season, request_data.geometry,
    )
    return JSONResponse(content=result)


# ========================================
# Admin Boundaries (CCAA / Province / Municipality)
# ========================================

from admin_manager import get_admin_manager

# Erosion data endpoints (spectral index zonal statistics)
try:
    # Erosion subsystem (Murcia Parquet stats) is not part of the open-source
    # benchmark — it depends on a private GCS Parquet not shipped here.
    pass
except ImportError:
    logger.warning("Erosion endpoints not available (missing pandas or dependencies)")


@app.get("/admin/index")
async def admin_index():
    """Return the full admin hierarchy index for the geographic selector."""
    mgr = get_admin_manager()
    return JSONResponse(content=mgr.get_index())


@app.get("/admin/geometry")
async def admin_geometry(type: str, code: str):
    """Return GeoJSON Feature for a CCAA, province, or municipality."""
    if type not in ("ccaa", "province", "municipality"):
        raise HTTPException(400, "type must be ccaa, province, or municipality")
    mgr = get_admin_manager()
    feature = mgr.get_geometry(type, code)
    if not feature:
        raise HTTPException(404, f"{type} with code '{code}' not found")
    return JSONResponse(content=feature)


@app.post("/admin/analyze")
async def admin_analyze(request: Request):
    """Direct zonal statistics — no LLM, no agent. For pre-computing rankings."""
    body = await request.json()
    indicator = body.get("indicator")
    year = body.get("year")
    season = body.get("season")
    geometry = body.get("geometry")
    if not all([indicator, year, season, geometry]):
        raise HTTPException(400, "indicator, year, season, geometry required")
    result = await _run_analyze_area(indicator, year, season, geometry)
    return JSONResponse(content=result)


# ========================================
# Agent Endpoint
# ========================================


@app.post("/agent/ask")
async def agent_ask(request_data: AgentQueryRequest):
    """Ask the GeoNature Agent a question about available geospatial data."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="Agent not configured (missing ANTHROPIC_API_KEY).")

    try:
        from rate_limiter import check_rate_limit
        allowed, rl_info = check_rate_limit(None, None)
        if not allowed:
            retry_after = rl_info.get("retry_after", 60)
            return JSONResponse(
                status_code=429,
                content={"detail": rl_info.get("reason", "Rate limit exceeded."), "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
    except Exception:
        pass

    from agent.agent import run_agent
    cache = get_cache_manager()
    result = await run_in_threadpool(
        lambda: run_agent(
            question=request_data.question,
            aoi=request_data.aoi,
            cache_manager=cache,
            user=None,
            session_id=request_data.session_id,
        )
    )
    if "error" in result and result.get("answer") is None:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.get("/")
async def root():
    """Root endpoint — API info."""
    return {
        "name": "GeoNatureAgent API",
        "version": "0.1.0",
        "description": "QGIS ↔ Claude bridge for the GeoNature benchmark platform",
        "endpoints": {
            "health": "/health",
            "cache_status": "/cache/status",
            "cache_layers": "/cache/layers",
            "cache_layer_url": "/cache/layer-url",
            "agent_ask": "/agent/ask",
            "admin_index": "/admin/index",
        },
    }


# ========================================
# Main Entry Point
# ========================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=LOCAL_DEV_MODE)
