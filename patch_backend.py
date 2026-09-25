with open('backend/ncpor_api.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_block = """            if sic > 0.05:  # Only include meaningful concentrations
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(float(lon), 2), round(float(lat), 2)]},
                    "properties": {
                        "sic": round(sic, 3),
                        "sic_pct": round(sic * 100, 1),
                        "thickness_m": round(sic * 2.2, 2),
                    }
                })"""

new_block = """            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(float(lon), 2), round(float(lat), 2)]},
                "properties": {
                    "sic": round(sic, 3),
                    "sic_pct": round(sic * 100, 1),
                    "thickness_m": round(sic * 2.2, 2),
                    "wind": round(wx["wind_speed_kn"], 1),
                    "waves": round(wx["wave_height_m"], 2),
                    "currents": round(wx["wind_speed_kn"] * 0.05, 2)
                }
            })"""

if old_block in text:
    text = text.replace(old_block, new_block, 1)
    with open('backend/ncpor_api.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Backend patched")
else:
    print("Failed to patch backend")
