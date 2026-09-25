import io

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = """    try {
      if (!map.getSource('sic-forecast')) {"""

replacement = """    try {
      console.log("HEATMAP EFFECT TRIGGERED", heatmapType);
      console.log("forecastGeoJSON features length:", forecastGeoJSON ? forecastGeoJSON.features?.length : "null");
      if (!map.getSource('sic-forecast')) {"""

if target in code:
    code = code.replace(target, replacement)
    with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
        f.write(code)
    print("Injected console log!")
else:
    print("Target not found.")
