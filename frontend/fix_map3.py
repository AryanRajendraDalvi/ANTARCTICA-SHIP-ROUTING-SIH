import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update the renderOverlay to use polygons instead of circles
block_target_pattern = r"      // --- 1\. RENDER HEATMAP ---.*?      // --- 2\. RENDER ROUTES ---"

new_block = """      // --- 1. RENDER HEATMAP ---
      if (heatmapTypeRef.current !== 'none' && forecastRef.current && forecastRef.current.features) {
        const hType = heatmapTypeRef.current;
        const prop = hType === 'weather' ? 'wind' : hType === 'ocean currents' ? 'currents' : hType === 'waves' ? 'waves' : 'sic';
        
        let heatHtml = '';
        forecastRef.current.features.forEach((f: any) => {
          const val = f.properties[prop];
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
          
          // Grid resolution is 1.5 degrees. Calculate the 4 corners of the grid cell
          const hs = 1.5 / 2; // half size
          const tl = map.project([lon - hs, lat + hs] as [number, number]);
          const tr = map.project([lon + hs, lat + hs] as [number, number]);
          const br = map.project([lon + hs, lat - hs] as [number, number]);
          const bl = map.project([lon - hs, lat - hs] as [number, number]);
          
          heatHtml += `<polygon points="${tl.x},${tl.y} ${tr.x},${tr.y} ${br.x},${br.y} ${bl.x},${bl.y}" fill="${color}" opacity="0.65" stroke="${color}" stroke-width="1" />`;
        });
        
        // Wrap with a very slight blur for smoothing cell edges
        html += `<g filter="url(#heat-blur)">${heatHtml}</g>`;
      }

      // --- 2. RENDER ROUTES ---"""

code = re.sub(block_target_pattern, new_block, code, flags=re.DOTALL)

# 2. Fix the blur radius
code = code.replace('<feGaussianBlur stdDeviation="25" />', '<feGaussianBlur stdDeviation="4" />')

# 3. Fix the OnshoreOverview component to pass heatmapType="none"
overview_target = """<SharedMap vessels={vessels} icebergs={icebergs} routes={allRoutes} />"""
overview_replacement = """<SharedMap vessels={vessels} icebergs={icebergs} routes={allRoutes} heatmapType="none" />"""
code = code.replace(overview_target, overview_replacement)

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)

print("Applied precise polygon grid heatmap!")
