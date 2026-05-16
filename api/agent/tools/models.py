"""Pydantic input models for tool-call validation.

Each model defines the expected schema for a tool's input parameters.
The TOOL_INPUT_MODELS registry maps tool names to their model class.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ListLayersInput(BaseModel):
    pass  # no required fields


class GetLegendInput(BaseModel):
    indicator: str


class AnalyzeAreaInput(BaseModel):
    indicator: str
    year: str
    season: str
    aoi: Dict[str, Any] = {}


class GetLayerBoundsInput(BaseModel):
    indicator: str
    year: str
    season: str


class LookupProvinceInput(BaseModel):
    name: str


class LookupMunicipalityInput(BaseModel):
    name: str
    province: str = ""


class ToggleLayerInput(BaseModel):
    indicator: str
    visible: bool = True


class CompareAreasInput(BaseModel):
    area_a: str
    area_b: str
    indicator: str
    year: str
    season: str


class FindTopNInput(BaseModel):
    metric: str
    n: int = 10
    order: str = "desc"
    filter_provinces: List[str] = []


class GenerateChartInput(BaseModel):
    chart_type: str
    title: str
    data: List[Dict[str, Any]]
    x_label: str = ""
    y_label: str = ""
    output_prefix: str = "poc/charts"
    filename: str = ""


class AnalyzeMultiLayerInput(BaseModel):
    province: str
    indicators: List[Dict[str, str]]


class QueryErosionStatsInput(BaseModel):
    query_type: str  # timeseries | ranking | seasonal
    indices: List[str]  # e.g. ["bsi", "ndvi"]
    municipality: str = ""
    year_start: int = 2018
    year_end: int = 2025


class CreateBufferInput(BaseModel):
    area_name: str
    area_type: str = "province"
    buffer_km: float
    province_hint: str = ""


class SelectFeaturesBySpatialRelationshipInput(BaseModel):
    reference_area: str = ""
    reference_type: str = "province"
    target_type: str
    spatial_predicates: List[str]
    reference_aoi: Optional[Dict[str, Any]] = None
    province_hint: str = ""


class GetCentroidsInput(BaseModel):
    area_names: List[str]
    area_type: str = "province"
    province_hint: str = ""


class RejectTaskInput(BaseModel):
    reason: str


TOOL_INPUT_MODELS: Dict[str, type] = {
    "list_layers": ListLayersInput,
    "get_legend": GetLegendInput,
    "analyze_area": AnalyzeAreaInput,
    "get_layer_bounds": GetLayerBoundsInput,
    "lookup_province": LookupProvinceInput,
    "lookup_municipality": LookupMunicipalityInput,
    "toggle_layer": ToggleLayerInput,
    "compare_areas": CompareAreasInput,
    "find_top_n": FindTopNInput,
    "generate_chart": GenerateChartInput,
    "analyze_multi_layer": AnalyzeMultiLayerInput,
    "query_erosion_stats": QueryErosionStatsInput,
    "create_buffer": CreateBufferInput,
    "select_features_by_spatial_relationship": SelectFeaturesBySpatialRelationshipInput,
    "get_centroids": GetCentroidsInput,
    "reject_task": RejectTaskInput,
}
