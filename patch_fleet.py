import re

with open("backend/ncpor_api.py", "r") as f:
    code = f.read()

# 1. Define coords dict
coords_dict = """
DESTINATION_COORDS = {
    "Maitri Station, Antarctica": (-70.766, 11.833),
    "Bharati Station, Antarctica": (-69.400, 76.183),
    "Davis Station, Antarctica": (-68.577, 77.967),
    "Casey Station, Antarctica": (-66.282, 110.527),
    "Mawson Station, Antarctica": (-67.603, 62.876),
    "Zhongshan Station, Antarctica": (-69.373, 76.377),
    "Dumont d'Urville Station, Antarctica": (-66.663, 140.002),
    "Princess Elisabeth Station, Antarctica": (-71.950, 23.347),
    "Troll Station, Antarctica": (-72.011, 2.534),
    "SANAE IV Station, Antarctica": (-71.673, -2.842),
}
"""

# Insert it before MISSION_DESTINATIONS
code = code.replace("MISSION_DESTINATIONS = [", coords_dict + "\nMISSION_DESTINATIONS = [")

# 2. Modify generate_fleet_routes
old_func = '''@app.post("/api/routes/fleet")
def generate_fleet_routes(req: RouteRequest):
    """Generate fastest routes for all active vessels to a single destination."""
    routes = []
    for v in VESSELS:
        route = generate_polar_route(
            v["lat"], v["lon"],
            req.end_lat, req.end_lon,
            mode="fast"
        )
        route["vesselId"] = v["id"]
        route["vesselName"] = v["name"]
        route["color"] = v.get("color", "#3b82f6")
        routes.append(route)
    return {"routes": routes, "generated_at": datetime.utcnow().isoformat()}'''

new_func = '''@app.post("/api/routes/fleet")
def generate_fleet_routes(req: RouteRequest):
    """Generate fastest routes for all active vessels to their designated missions."""
    routes = []
    for v in VESSELS:
        dest_name = v.get("destination", "Maitri Station, Antarctica")
        end_lat, end_lon = DESTINATION_COORDS.get(dest_name, (-70.766, 11.833))
        
        route = generate_polar_route(
            v["lat"], v["lon"],
            end_lat, end_lon,
            mode="fast"
        )
        route["vesselId"] = v["id"]
        route["vesselName"] = v["name"]
        route["color"] = v.get("color", "#3b82f6")
        # Add a label so the frontend knows where this route is going
        route["label"] = dest_name
        routes.append(route)
    return {"routes": routes, "generated_at": datetime.utcnow().isoformat()}'''

code = code.replace(old_func, new_func)

with open("backend/ncpor_api.py", "w") as f:
    f.write(code)

print("Fleet route destinations patched!")
