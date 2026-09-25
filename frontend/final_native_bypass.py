import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Hide heatmap on all other panels by making heatmapType='none' default in SharedMap!
target = """export default function SharedMap({
  vessels, icebergs, routes, forecastGeoJSON, heatmapType = 'sic', zoom = 3.5,
  center = [68.0, -66.0] as [number, number]
}: {"""
replacement = """export default function SharedMap({
  vessels, icebergs, routes, forecastGeoJSON, heatmapType = 'none', zoom = 3.5,
  center = [68.0, -66.0] as [number, number]
}: {"""
code = code.replace(target, replacement)

# 2. Add setWorkerUrl bypass to fix Turbopack 404 issue!
import_target = """import * as maplibregl from 'maplibre-gl';"""
import_replacement = """import * as maplibregl from 'maplibre-gl';
maplibregl.setWorkerUrl('https://unpkg.com/maplibre-gl@4.7.0/dist/maplibre-gl.js');"""
code = code.replace(import_target, import_replacement)

# 3. Fix the WebGL heatmap weights in SharedMap
heatmap_block_target = """        let weightProp = 'sic';
        let colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#60a5fa', 0.6, '#fde047', 1.0, '#dc2626'];
        
        if (heatmapType === 'weather') {
          weightProp = 'wind';
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#34d399', 0.6, '#60a5fa', 1.0, '#8b5cf6'];
        } else if (heatmapType === 'ocean currents') {
          weightProp = 'currents';
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#fb923c', 0.6, '#f43f5e', 1.0, '#9f1239'];
        } else if (heatmapType === 'waves') {
          weightProp = 'waves';
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#2dd4bf', 0.6, '#0ea5e9', 1.0, '#0369a1'];
        }

        if (map.getLayer('sic-heat')) {
          map.removeLayer('sic-heat');
        }

        map.addLayer({
          id: 'sic-heat', type: 'heatmap', source: 'sic-forecast',
          paint: {
            'heatmap-weight': ['get', weightProp],
            'heatmap-intensity': 1.2,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], ...colorStops],
            'heatmap-radius': 45,
            'heatmap-opacity': 0.7
          }
        });"""

heatmap_block_replacement = """        let weightExpr: any = ['get', 'sic'];
        let colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#60a5fa', 0.6, '#fde047', 1.0, '#dc2626'];
        
        if (heatmapType === 'weather') {
          weightExpr = ['*', ['get', 'wind'], 0.025]; // Normalize 0-40 knots to 0-1
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#34d399', 0.6, '#60a5fa', 1.0, '#8b5cf6'];
        } else if (heatmapType === 'ocean currents') {
          weightExpr = ['*', ['get', 'currents'], 0.6]; // Normalize 0-1.5 m/s to 0-0.9
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#fb923c', 0.6, '#f43f5e', 1.0, '#9f1239'];
        } else if (heatmapType === 'waves') {
          weightExpr = ['*', ['get', 'waves'], 0.2]; // Normalize 0-5 m to 0-1
          colorStops = [0, 'rgba(255,255,255,0)', 0.3, '#2dd4bf', 0.6, '#0ea5e9', 1.0, '#0369a1'];
        }

        if (map.getLayer('sic-heat')) {
          map.removeLayer('sic-heat');
        }

        if (heatmapType !== 'none') {
          map.addLayer({
            id: 'sic-heat', type: 'heatmap', source: 'sic-forecast',
            paint: {
              'heatmap-weight': weightExpr,
              'heatmap-intensity': 1.5,
              'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], ...colorStops],
              'heatmap-radius': 50,
              'heatmap-opacity': 0.8
            }
          });
        }"""
if heatmap_block_target in code:
    code = code.replace(heatmap_block_target, heatmap_block_replacement)
else:
    print("WARNING: heatmap block not found")

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)
print("Applied native MapLibre heatmap with workerUrl bypass!")
