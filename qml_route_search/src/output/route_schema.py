"""
Route Output Schema (§9) — Pydantic models for API serialization.

Defines the per-waypoint record, route summary, and the full planning response
that the onshore agency panel and ship display panel consume.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from enum import Enum


class SafetyFlag(str, Enum):
    """Safety flag enum for per-waypoint status."""
    OK = "OK"
    PARAMETRIC_ROLL_RISK = "PARAMETRIC_ROLL_RISK"
    COMFORT_LIMIT = "COMFORT_LIMIT"
    ECA = "ECA"
    ELEVATED_RISK = "ELEVATED_RISK"


class SourceType(str, Enum):
    """Indicates whether the cost prediction came from the QML model or Holtrop-Mennen fallback."""
    MODEL = "MODEL"
    FALLBACK_HOLTROP = "FALLBACK_HOLTROP"


class WaypointRecord(BaseModel):
    """Per-waypoint record as specified in §9 of the technical spec."""
    lat: float
    lon: float
    eta: datetime
    heading: float          # degrees — recommended course
    speed: float            # knots — recommended SOG (V_stw − ΔV̂)
    fuel_leg_kg: float      # predicted fuel burn for this leg
    resistance_kN: float    # predicted wave + wind drag (R̂_wave + R̂_wind)
    roll_risk: float        # 0–1 from §3.4 q3
    slam_force: float       # kN from §3.4 q4
    comfort_index: float    # m/s² RMS from §3.4 q6
    green_water_risk: float # 0–1 from §3.4 q7
    prop_emergence_risk: float  # 0–1 from §3.4 q8
    confidence: float       # 0–1 from §3.4 q9
    safety_flag: SafetyFlag = SafetyFlag.OK
    source: SourceType = SourceType.MODEL


class RouteSummary(BaseModel):
    """Per-route summary record."""
    label: str              # FASTEST / CHEAPEST / MOST_COMFORTABLE
    total_distance_nm: float
    total_fuel_t: float     # total fuel in metric tonnes
    total_time_hr: float
    cii_attained: float     # Carbon Intensity Indicator
    last_update: datetime


class RouteOutput(BaseModel):
    """A single route with summary and waypoints."""
    route_id: str
    summary: RouteSummary
    waypoints: List[WaypointRecord]


class PlanningResponse(BaseModel):
    """Response from the plan-route endpoint — contains the Pareto-optimal route set."""
    routes: List[RouteOutput]
    planning_time_s: float
    vessel_name: str
