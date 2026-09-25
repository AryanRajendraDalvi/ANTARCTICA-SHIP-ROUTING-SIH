from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PlanRouteRequest(BaseModel):
    origin: str  # Port name or lat,lon string
    destination: str
    vessel_id: str
    departure_time: datetime

class ReplanRequest(BaseModel):
    current_lat: float
    current_lon: float
    current_sog: float
    current_cog: float
    t_now: datetime
    route_id: str
    vessel_id: str
    destination: str

class VesselInfo(BaseModel):
    name: str
    imo: str
    type: str
    loa: float
    beam: float
    draft: float
    dwt: float
    speed: float

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None

class DispatchRequest(BaseModel):
    route_id: str
