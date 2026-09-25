import io

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = """    // High-precision SVG render loop for both routes AND environmental heatmaps
    const renderOverlay = () => {
      if (!svgRef.current || !map) return;
      let html = '';

      // --- 1. RENDER HEATMAP ---"""

replacement = """    // High-precision SVG render loop for both routes AND environmental heatmaps
    const renderOverlay = () => {
      if (!svgRef.current || !map) return;
      let html = `<defs>
        <filter id="heat-blur" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="25" />
        </filter>
      </defs>`;

      // --- 1. RENDER HEATMAP ---"""

code = code.replace(target, replacement)

target2 = """          const lon = f.geometry.coordinates[0];
          const lat = f.geometry.coordinates[1];
          const pt = map.project([lon, lat] as [number, number]);
          
          // Draw overlapping circles for heatmap effect
          html += `<circle cx="${pt.x}" cy="${pt.y}" r="25" fill="${color}" opacity="0.4" style="mix-blend-mode: screen;" />`;
        });
      }"""

replacement2 = """          const lon = f.geometry.coordinates[0];
          const lat = f.geometry.coordinates[1];
          const pt = map.project([lon, lat] as [number, number]);
          
          // Draw overlapping circles for heatmap effect
          html += `<circle cx="${pt.x}" cy="${pt.y}" r="60" fill="${color}" opacity="0.5" />`;
        });
        
        // Wrap all heatmap circles in a blur group
        html = html.replace('// --- 1. RENDER HEATMAP ---', '// --- 1. RENDER HEATMAP ---\\n      html += `<g filter="url(#heat-blur)">`;');
        html += `</g>`;
      }"""
# Wait, replacing inside `html` string is tricky in JS. I'll just change the structure slightly.

# Let's do a regex replacement for the entire RENDER HEATMAP block
import re

block_target_pattern = r"      // --- 1\. RENDER HEATMAP ---.*?      // --- 2\. RENDER ROUTES ---"

new_block = """      // --- 1. RENDER HEATMAP ---
      if (forecastRef.current && forecastRef.current.features) {
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
          const pt = map.project([lon, lat] as [number, number]);
          
          heatHtml += `<circle cx="${pt.x}" cy="${pt.y}" r="65" fill="${color}" opacity="0.45" />`;
        });
        
        html += `<g filter="url(#heat-blur)">${heatHtml}</g>`;
      }

      // --- 2. RENDER ROUTES ---"""

code = re.sub(block_target_pattern, new_block, code, flags=re.DOTALL)

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)

print("Smoothed out SVG heatmap!")
