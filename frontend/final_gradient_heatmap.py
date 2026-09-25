import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

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

# Replace renderRoutes with SVG gradient heatmap
render_target = """    // High-precision SVG render loop for routes directly in DOM
    const renderRoutes = () => {
      if (!svgRef.current || !map) return;
      let html = '';

      routesRef.current.forEach(route => {"""

render_replacement = """    // High-precision SVG render loop for both routes AND environmental heatmaps
    const renderOverlay = () => {
      if (!svgRef.current || !map) return;
      
      // Define a radial gradient that fades from currentColor to transparent
      let html = `<defs>
        <radialGradient id="heat-grad">
          <stop offset="0%" stop-color="currentColor" stop-opacity="0.8" />
          <stop offset="50%" stop-color="currentColor" stop-opacity="0.4" />
          <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
        </radialGradient>
      </defs>`;

      // --- 1. RENDER HEATMAP ---
      if (heatmapTypeRef.current !== 'none' && forecastRef.current && forecastRef.current.features) {
        const hType = heatmapTypeRef.current;
        const prop = hType === 'weather' ? 'wind' : hType === 'ocean currents' ? 'currents' : hType === 'waves' ? 'waves' : 'sic';
        
        let heatHtml = '';
        forecastRef.current.features.forEach((f: any) => {
          const val = f.properties[prop];
          // Skip drawing if value is too low to contribute (creates organic edges)
          if (val === undefined || val <= 0.05) return;
          
          let c = '#bfdbfe';
          if (hType === 'weather') {
            c = val < 10 ? '#bfdbfe' : val < 20 ? '#4ade80' : val < 30 ? '#3b82f6' : val < 40 ? '#6366f1' : '#a855f7';
          } else if (hType === 'ocean currents') {
            c = val < 0.2 ? '#fed7aa' : val < 0.4 ? '#fb923c' : val < 0.6 ? '#f43f5e' : '#9f1239';
          } else if (hType === 'waves') {
            c = val < 1 ? '#99f6e4' : val < 2 ? '#2dd4bf' : val < 4 ? '#0ea5e9' : '#075985';
          } else {
            c = val < 0.2 ? '#bfdbfe' : val < 0.4 ? '#60a5fa' : val < 0.6 ? '#2563eb' : val < 0.8 ? '#eab308' : '#dc2626';
          }

          const lon = f.geometry.coordinates[0];
          const lat = f.geometry.coordinates[1];
          const pt = map.project([lon, lat] as [number, number]);
          
          // Use an ellipse to bridge the vertical gap caused by the polar projection distortion
          heatHtml += `<ellipse cx="${pt.x}" cy="${pt.y}" rx="35" ry="85" fill="url(#heat-grad)" color="${c}" opacity="0.65" style="mix-blend-mode: screen;" />`;
        });
        
        html += `<g>${heatHtml}</g>`;
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

print("Applied gradient ellipse SVG heatmap!")
