import re

filepath = 'backend/ncpor_api.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Add origin and destination to the dictionary
old_dict = '''        "heading_deg": heading,
        "engine_load_pct": random.randint(50, 85),'''

new_dict = '''        "heading_deg": heading,
        "origin": random.choice(["Mormugao, IN", "Cape Town, ZA", "Port Louis, MU", "Chennai, IN"]),
        "destination": random.choice(["Bharati Station, AQ", "Maitri Station, AQ"]),
        "engine_load_pct": random.randint(50, 85),'''

text = text.replace(old_dict, new_dict)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated API with Origin and Destination.")
