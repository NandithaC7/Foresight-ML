"""Pydantic response contracts. Fields are nullable where a model/label is unavailable."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class Item(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    produce_class: Optional[str] = None
    produce_confidence: Optional[float] = None
    produce_probabilities: Optional[dict[str, float]] = None
    spoilage_label: Optional[str] = None
    spoilage_confidence: Optional[float] = None
    p_spoiled: Optional[float] = None
    freshness: int  # Not_spoiled softmax score x 100 (uncalibrated)
    tier: Literal["good", "warn", "bad"]
    days: Optional[int] = None
    shelf_life_status: str = "unavailable"
    decayPct: Optional[float] = None
    decay_mask_available: bool = False
    segmentation_status: str = "annotation_pending"
    action: str
    xai_overlay: Optional[str] = None
    xai_method: Optional[str] = None


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    scan_id: str
    ts: int
    status: Literal["ok", "partial"]
    source: Literal["model", "mock"]
    mock: bool
    model_version: Optional[str]
    mode: str
    warnings: list[str]
    disclaimer: str
    timing_ms: dict[str, float]
    items: list[Item]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    model_loaded: bool
    model_version: Optional[str]
    model_error: Optional[str]
    mock_mode: bool
    device: Optional[str]


class ErrorBody(BaseModel):
    code: str
    message: str
