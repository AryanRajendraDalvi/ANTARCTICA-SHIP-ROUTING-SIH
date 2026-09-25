import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Revert the SVG modifications in renderOverlay
# We will just replace renderOverlay entirely back with renderRoutes for routes only.
block_target_pattern = r"    // High-precision SVG render loop for both routes AND environmental heatmaps.*?      // --- 2\. RENDER ROUTES ---"

new_block = """    // High-precision SVG render loop for routes directly in DOM
    const renderRoutes = () => {
      if (!svgRef.current || !map) return;
      let html = '';

      routesRef.current.forEach(route => {"""
code = re.sub(block_target_pattern, new_block, code, flags=re.DOTALL)

# 2. Revert the refs
refs_target = """  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  const forecastRef = useRef<any>(null);
  const heatmapTypeRef = useRef<string>('sic');
  
  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];
  forecastRef.current = forecastGeoJSON;
  heatmapTypeRef.current = heatmapType;"""

refs_replacement = """  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];"""
code = code.replace(refs_target, refs_replacement)

# 3. Rename renderOverlay back to renderRoutes in events
code = code.replace("map.on('render', renderOverlay);", "map.on('render', renderRoutes);")
code = code.replace("map.off('render', renderOverlay);", "map.off('render', renderRoutes);")

# 4. Remove the `html += \`</g>\`;` and `}` at the end of the old renderOverlay
cleanup_pattern = r"        html \+= `<g filter=\"url\(#heat-blur\)\">\$\{heatHtml\}</g>`;\n      \}\n\n      routesRef\.current\.forEach\(route => \{"
code = re.sub(cleanup_pattern, r"      routesRef.current.forEach(route => {", code)

# Just to be safe, I'll regex the whole render function.
# Let's restore the exact original renderRoutes function:
func_pattern = r"    const renderRoutes = \(\) => \{.*?\};\n\n    map\.on\('render', renderRoutes\);"
# Wait, let's just do it manually with a full replace.
# Actually, it's safer to just read the file from the git history before my commit.
