import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

code = code.replace("maplibregl.workerCount = 0;", "maplibregl.setWorkerCount(0);")

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)
print("Fixed setWorkerCount!")
