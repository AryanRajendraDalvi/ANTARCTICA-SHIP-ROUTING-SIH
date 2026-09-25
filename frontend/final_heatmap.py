import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. First, we need to locate the renderRoutes block in the current code
# Since we reset to e1cf4d0, the code has the original renderRoutes.
# Let's replace the WebGL heatmap logic and enhance renderRoutes.

# Add refs
refs_target = """  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];"""

refs_replacement = """  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  const forecastRef = useRef<any>(null);
  const heatmapTypeRef = useRef<string>('sic');
  
  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];
  forecastRef.current = forecastGeoJSON;
  heatmapTypeRef.current = heatmapType;"""

if refs_target in code:
    code = code.replace(refs_target, refs_replacement)

# Replace renderRoutes with SVG heatmap + routes
render_target = """    // High-precision SVG render loop for routes directly in DOM
    const renderRoutes = () => {
      if (!svgRef.current || !map) return;
      let html = '';

      routesRef.current.forEach(route => {"""

render_replacement = """    // High-precision SVG render loop for both routes AND environmental heatmaps
    const renderOverlay = () => {
      if (!svgRef.current || !map) return;
      let html = `<defs>
        <filter id="heat-blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="8" />
        </filter>
      </defs>`;

      // --- 1. RENDER HEATMAP ---
      if (heatmapTypeRef.current !== 'none' && forecastRef.current && forecastRef.current.features) {
        const hType = heatmapTypeRef.current;
        const prop = hType === 'weather' ? 'wind' : hType === 'ocean currents' ? 'currents' : hType === 'waves' ? 'waves' : 'sic';
        
        let heatHtml = '';
        forecastRef.current.features.forEach((f: any) => {
          const val = f.properties[prop];
          // Skip drawing if value is too low to contribute to the heatmap (creates organic edges)
          if (val === undefined || val <= 0.05) return;
          
          let color = '#bfdbfe';
          if (hType === 'weather') {
            color = val < 10 ? '#bfdbfe' : val < 20 ? '#4ade80' : val < 30 ? '#3b82f6' : val < 40 ? '#6366f1' : '#a855f7';
          } else if (hType === 'ocean currents') {
            color = val < 0.2 ? '#fed7aa' : val < 0.4 ? '#fb923c' : val < 0.6 ? '#f43f5e' : '#9f1239';
          } else if (hType === 'waves') {
            color = val < 1 ? '#99f6e4' : val < 2 ? '#2dd4bf' : val < 4 ? '#0ea5e9' : '#075985';
          } else {
            color = val < 0.2 ? '#bfdbfe' : val < 0.4 ? '#60a5fa' : val < 0.6 ? '#2563eb' : val < 0.8 ? '#eab308' : '#dc2626';
          }

          const lon = f.geometry.coordinates[0];
          const lat = f.geometry.coordinates[1];
          const pt = map.project([lon, lat] as [number, number]);
          
          // Use radius 35 to bridge the latitudinal gap without turning into a giant block
          heatHtml += `<circle cx="${pt.x}" cy="${pt.y}" r="35" fill="${color}" opacity="0.45" />`;
        });
        
        html += `<g filter="url(#heat-blur)">${heatHtml}</g>`;
      }

      // --- 2. RENDER ROUTES ---
      routesRef.current.forEach(route => {"""

code = code.replace(render_target, render_replacement)
code = code.replace("map.on('render', renderRoutes);", "map.on('render', renderOverlay);")
code = code.replace("map.off('render', renderRoutes);", "map.off('render', renderOverlay);")

# Remove WebGL heatmap useEffect
pattern = re.compile(r"    // heatmaps\n    useEffect\(\(\) => \{.*?\}, \[forecastGeoJSON, heatmapType, mapReady\]\);", re.DOTALL)
code = re.sub(pattern, "", code)

# Hide heatmap on OnshoreOverview
overview_target = """<SharedMap vessels={vessels} icebergs={icebergs} routes={allRoutes} />"""
overview_replacement = """<SharedMap vessels={vessels} icebergs={icebergs} routes={allRoutes} heatmapType="none" />"""
code = code.replace(overview_target, overview_replacement)

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)

print("Applied perfect SVG heatmap!")
