import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# Just inject maplibregl.workerCount = 0 right after the imports
if "maplibregl.workerCount = 0;" not in code:
    code = code.replace("import * as maplibregl from 'maplibre-gl';", "import * as maplibregl from 'maplibre-gl';\nmaplibregl.workerCount = 0;")
    with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
        f.write(code)
    print("Disabled MapLibre web worker!")
else:
    print("Already disabled.")
