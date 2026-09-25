import asyncio
import json
import torch
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List

from src.vessel_loader import load_all_vessels
from src.cost_model import QMLCostModel
from src.surrogate import SurrogateMLP
from scripts.benchmark import SurrogateWrapper
from api.routing import generate_surrogate_routes

app = FastAPI(title="MERIDIAN QML Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).parent.parent
vessel_dict = load_all_vessels(PROJECT_ROOT / "config" / "vessels")

# Load Models on startup
print("Loading Models...")

# We need the full model for the fusion layer
cost_config = {
    'F_max': 5000.0, 'R_max': 2000000.0, 'DV_max': 5.0,
    'S_max': 500000.0, 'R_wind_max': 500000.0, 'a_max': 3.0
}
model = QMLCostModel(cost_config)
model_path = PROJECT_ROOT / "checkpoints" / "qml_cost_model.pt"
if model_path.exists():
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
model.eval()

surrogate = SurrogateMLP(input_dim=98, hidden_dim=128, output_dim=10)
surrogate_path = PROJECT_ROOT / "checkpoints" / "surrogate_mlp.pt"
if surrogate_path.exists():
    surrogate.load_state_dict(torch.load(surrogate_path, map_location='cpu'))
surrogate.eval()

surrogate_wrapper = SurrogateWrapper(surrogate)
surrogate_wrapper.fusion = model.fusion
print("Models loaded successfully.")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, vessel_id: str):
        await websocket.accept()
        if vessel_id not in self.active_connections:
            self.active_connections[vessel_id] = []
        self.active_connections[vessel_id].append(websocket)

    def disconnect(self, websocket: WebSocket, vessel_id: str):
        if vessel_id in self.active_connections:
            self.active_connections[vessel_id].remove(websocket)

    async def broadcast(self, message: dict, vessel_id: str):
        if vessel_id in self.active_connections:
            for connection in self.active_connections[vessel_id]:
                await connection.send_json(message)

manager = ConnectionManager()

@app.get("/api/fleet")
async def get_fleet():
    return [
        {"id": k, "name": v.name, "type": v.type, "status": "UNDERWAY"}
        for k, v in vessel_dict.items()
    ]

from fastapi.concurrency import run_in_threadpool

@app.post("/api/qml-routes")
async def get_qml_routes(request: Request):
    data = await request.json()
    vessel_id = data.get("vessel_id", "sci_chennai")
    origin = data.get("origin", [18.94, 72.82]) # Default Mumbai
    dest = data.get("dest", [6.93, 79.85]) # Default Colombo
    weather_intensity = float(data.get("weather_intensity", 0.0))
    
    vessel = vessel_dict.get(vessel_id)
    if not vessel:
        return {"error": "Vessel not found"}
        
    routes = await run_in_threadpool(
        generate_surrogate_routes,
        origin, dest, vessel, surrogate_wrapper,
        60.0, 30.0, 24.0, 100, weather_intensity
    )
    
    return {"routes": routes}

@app.post("/api/force-dispatch")
async def force_dispatch(request: Request):
    data = await request.json()
    route_id = data.get("route_id")
    waypoints = data.get("waypoints")
    vessel_id = data.get("vessel_id", "sci_chennai") # We assume active vessel
    
    msg = {
        "event": "NEW_ROUTE_DISPATCHED",
        "route": {
            "route_id": route_id,
            "waypoints": waypoints
        }
    }
    
    await manager.broadcast(msg, vessel_id)
    return {"status": "dispatched", "vessel": vessel_id}

@app.websocket("/ws/vessel/{vessel_id}")
async def websocket_endpoint(websocket: WebSocket, vessel_id: str):
    await manager.connect(websocket, vessel_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Simple ping/pong handler
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, vessel_id)

# --- RTZ Offline Fallback Endpoints ---
LATEST_RTZ_XML = None

@app.post("/api/rtz/upload")
async def upload_rtz(request: Request):
    global LATEST_RTZ_XML
    body = await request.body()
    LATEST_RTZ_XML = body.decode('utf-8')
    return {"status": "uploaded", "size": len(LATEST_RTZ_XML)}

@app.get("/api/rtz/download")
async def download_rtz():
    if not LATEST_RTZ_XML:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No RTZ file has been exported by Onshore yet.")
    return Response(content=LATEST_RTZ_XML, media_type="application/xml")

@app.post("/api/report/cii")
async def generate_cii_report(request: Request):
    data = await request.json()
    vessel_id = data.get("vessel_id", "unknown")
    route_name = data.get("route_name", "Autonomous Route")
    fuel_kg = float(data.get("total_fuel_kg", 0))
    dist_nm = float(data.get("distance_nm", 1))
    hours = float(data.get("duration_hrs", 1))
    
    vessel = vessel_dict.get(vessel_id)
    dwt = vessel.dwt_mt if vessel else 50000
    name = vessel.name if vessel else vessel_id.upper()
    imo = vessel.imo if vessel else "9XXXXXX"
    
    # Math: 3.114 kg CO2 per kg of marine diesel
    co2_tons = (fuel_kg * 3.114) / 1000
    # CII formula: grams CO2 per DWT-nautical mile
    cii_val = (fuel_kg * 3114) / (dwt * dist_nm)
    
    if cii_val < 3.5: rating, color = "A", "#2de1c2"
    elif cii_val < 4.5: rating, color = "B", "#39ff88"
    elif cii_val < 5.5: rating, color = "C", "#ffb238"
    elif cii_val < 6.5: rating, color = "D", "#ff5a3c"
    else: rating, color = "E", "#ff3333"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>IMO CII Compliance Report - {name}</title>
      <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background: #f4f7f6; color: #333; margin: 0; padding: 40px; }}
        .container {{ max-width: 800px; margin: 0 auto; background: #fff; padding: 40px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 6px solid #0c2432; }}
        .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ margin: 0 0 10px 0; color: #0c2432; font-size: 28px; }}
        .meta {{ color: #777; font-size: 14px; line-height: 1.5; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
        .box {{ background: #f9fbfb; padding: 20px; border-radius: 4px; border: 1px solid #e1e8ed; }}
        .box h3 {{ margin: 0 0 15px 0; font-size: 14px; text-transform: uppercase; color: #555; letter-spacing: 1px; }}
        .stat {{ display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 15px; }}
        .stat strong {{ color: #111; }}
        .rating-box {{ text-align: center; padding: 40px 20px; background: #0c2432; color: #fff; border-radius: 6px; margin-bottom: 30px; }}
        .rating-box h2 {{ margin: 0 0 10px 0; font-size: 18px; font-weight: 400; letter-spacing: 1px; color: #a0b2bd; }}
        .grade {{ font-size: 72px; font-weight: 800; line-height: 1; margin: 10px 0; color: {color}; }}
        .val {{ font-size: 18px; color: #ccc; }}
        .footer {{ text-align: center; font-size: 12px; color: #999; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div>
            <h1>IMO CII Compliance Statement</h1>
            <div class="meta">Automated Generation via Meridian AI System</div>
          </div>
          <div style="text-align: right;" class="meta">
            Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
            Reference: MER-{route_name[:8].upper()}-{int(__import__('time').time())}
          </div>
        </div>
        
        <div class="rating-box">
          <h2>OFFICIAL CARBON INTENSITY INDICATOR (CII) RATING</h2>
          <div class="grade">{rating}</div>
          <div class="val">{cii_val:.2f} gCO₂ / DWT-nm</div>
        </div>

        <div class="grid">
          <div class="box">
            <h3>Vessel Particulars</h3>
            <div class="stat"><span>Vessel Name:</span> <strong>{name}</strong></div>
            <div class="stat"><span>IMO Number:</span> <strong>{imo}</strong></div>
            <div class="stat"><span>Deadweight (DWT):</span> <strong>{dwt:,.0f} MT</strong></div>
          </div>
          <div class="box">
            <h3>Voyage Telemetry</h3>
            <div class="stat"><span>Route:</span> <strong>{route_name}</strong></div>
            <div class="stat"><span>Distance Sailed:</span> <strong>{dist_nm:.1f} nm</strong></div>
            <div class="stat"><span>Duration:</span> <strong>{hours:.1f} hrs</strong></div>
          </div>
        </div>

        <div class="box">
          <h3>Environmental Impact</h3>
          <div class="stat"><span>Total Marine Diesel Consumed:</span> <strong>{fuel_kg:,.0f} kg</strong></div>
          <div class="stat"><span>Estimated CO₂ Emissions:</span> <strong>{co2_tons:,.2f} Metric Tons</strong></div>
        </div>

        <div class="footer">
          This report was generated automatically by the Meridian Quantum Machine Learning Surrogate. <br>
          Compliant with MARPOL Annex VI regulations for continuous monitoring.
        </div>
      </div>
    </body>
    </html>
    """
    return {"html": html}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
