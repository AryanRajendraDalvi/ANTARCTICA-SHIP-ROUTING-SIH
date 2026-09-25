with open('frontend/src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update LiveMap signature
old_sig = """function LiveMap({
  vessels, icebergs, routes, forecastGeoJSON, zoom = 3.5,
  center = [68.0, -66.0] as [number, number]
}: {"""
new_sig = """function LiveMap({
  vessels, icebergs, routes, forecastGeoJSON, heatmapType = 'sic', zoom = 3.5,
  center = [68.0, -66.0] as [number, number]
}: {
  heatmapType?: 'sic' | 'wind' | 'waves' | 'currents';"""
if old_sig in text:
    text = text.replace(old_sig, new_sig, 1)

# 2. Update LiveMap SIC heatmap effect to be dynamic
old_heat = """  // ── SIC heatmap ────────────────────────────────────────────────────────────
  // We keep the SIC heatmap as a native MapLibre layer because it requires
  // WebGL interpolation which SVG cannot do. Since heatmaps don't have hard edges,
  // polar projection mismatch is less noticeable.
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    
    try {
      if (!map.getSource('sic-forecast')) {
        map.addSource('sic-forecast', { type: 'geojson', data: forecastGeoJSON || { type: 'FeatureCollection', features: [] } });
      } else {
        (map.getSource('sic-forecast') as maplibregl.GeoJSONSource).setData(forecastGeoJSON || { type: 'FeatureCollection', features: [] });
      }

      if (!map.getLayer('sic-heat')) {
        map.addLayer({
          id: 'sic-heat', type: 'heatmap', source: 'sic-forecast',
          paint: {
            'heatmap-weight': ['get', 'sic'],
            'heatmap-intensity': 1.2,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
              0, 'rgba(255,255,255,0)', 0.3, '#60a5fa', 0.6, '#fde047', 1.0, '#dc2626'],
            'heatmap-radius': 45,
            'heatmap-opacity': 0.7
          }
        });
      }
    } catch(e) { console.warn('SIC layer error:', e); }
  }, [forecastGeoJSON, mapReady]);"""

new_heat = """  // ── Dynamic Heatmap ────────────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    
    try {
      if (!map.getSource('dynamic-forecast')) {
        map.addSource('dynamic-forecast', { type: 'geojson', data: forecastGeoJSON || { type: 'FeatureCollection', features: [] } });
      } else {
        (map.getSource('dynamic-forecast') as maplibregl.GeoJSONSource).setData(forecastGeoJSON || { type: 'FeatureCollection', features: [] });
      }

      if (map.getLayer('dynamic-heat')) {
        map.removeLayer('dynamic-heat');
      }

      const getPaintConfig = () => {
        switch (heatmapType) {
          case 'wind': return {
            'heatmap-weight': ['/', ['get', 'wind'], 60],
            'heatmap-intensity': 1.5,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.4, '#bae6fd', 0.7, '#0284c7', 1.0, '#4c1d95'],
            'heatmap-radius': 45, 'heatmap-opacity': 0.8
          };
          case 'waves': return {
            'heatmap-weight': ['/', ['get', 'waves'], 10],
            'heatmap-intensity': 1.2,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.4, '#99f6e4', 0.7, '#0d9488', 1.0, '#115e59'],
            'heatmap-radius': 45, 'heatmap-opacity': 0.8
          };
          case 'currents': return {
            'heatmap-weight': ['/', ['get', 'currents'], 3],
            'heatmap-intensity': 1.5,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.4, '#c7d2fe', 0.7, '#4f46e5', 1.0, '#312e81'],
            'heatmap-radius': 45, 'heatmap-opacity': 0.8
          };
          default: return { // sic
            'heatmap-weight': ['get', 'sic'],
            'heatmap-intensity': 1.2,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.3, '#60a5fa', 0.6, '#fde047', 1.0, '#dc2626'],
            'heatmap-radius': 45, 'heatmap-opacity': 0.7
          };
        }
      };

      map.addLayer({
        id: 'dynamic-heat', type: 'heatmap', source: 'dynamic-forecast',
        paint: getPaintConfig()
      });
    } catch(e) { console.warn('Heatmap layer error:', e); }
  }, [forecastGeoJSON, heatmapType, mapReady]);"""

if old_heat in text:
    text = text.replace(old_heat, new_heat, 1)

# 3. Update OnshoreIceWeather LiveMap call
old_weather_map = """          <div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">
            <LiveMap forecastGeoJSON={sicGeoJSON} />"""
new_weather_map = """          <div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">
            <LiveMap forecastGeoJSON={sicGeoJSON} heatmapType={tab === 'Sea Ice' ? 'sic' : tab === 'Weather' ? 'wind' : tab === 'Ocean Currents' ? 'currents' : 'waves'} />"""

if old_weather_map in text:
    text = text.replace(old_weather_map, new_weather_map, 1)

# 4. We also need to update the legend dynamically!
old_legend = """            <div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-28">
              <div className="font-bold text-slate-700 mb-1">SIC Concentration</div>
              {[['0–20%','bg-blue-200'],['20–40%','bg-blue-400'],['40–60%','bg-yellow-400'],['60–80%','bg-orange-400'],['80–100%','bg-red-600']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-2"><div className={cn('w-3 h-2 rounded-sm', c)} /><span className="text-slate-600">{l}</span></div>
              ))}
            </div>"""
new_legend = """            <div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-32">
              <div className="font-bold text-slate-700 mb-1">
                {tab === 'Sea Ice' ? 'SIC Concentration' : tab === 'Weather' ? 'Wind Speed (kn)' : tab === 'Ocean Currents' ? 'Currents (kn)' : 'Wave Height (m)'}
              </div>
              {tab === 'Sea Ice' && [['0–20%','bg-blue-200'],['20–40%','bg-blue-400'],['40–60%','bg-yellow-400'],['60–80%','bg-orange-400'],['80–100%','bg-red-600']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-2"><div className={cn('w-3 h-2 rounded-sm', c)} /><span className="text-slate-600">{l}</span></div>
              ))}
              {tab === 'Weather' && [['0-15','bg-sky-200'],['15-30','bg-sky-400'],['30-45','bg-sky-600'],['45-60','bg-purple-700'],['60+','bg-purple-900']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-2"><div className={cn('w-3 h-2 rounded-sm', c)} /><span className="text-slate-600">{l}</span></div>
              ))}
              {tab === 'Ocean Currents' && [['0-1','bg-indigo-200'],['1-2','bg-indigo-400'],['2-3','bg-indigo-600'],['3-4','bg-indigo-800'],['4+','bg-slate-900']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-2"><div className={cn('w-3 h-2 rounded-sm', c)} /><span className="text-slate-600">{l}</span></div>
              ))}
              {tab === 'Waves' && [['0-2m','bg-teal-200'],['2-4m','bg-teal-400'],['4-6m','bg-teal-600'],['6-8m','bg-teal-800'],['8m+','bg-slate-800']].map(([l,c]) => (
                <div key={l} className="flex items-center gap-2"><div className={cn('w-3 h-2 rounded-sm', c)} /><span className="text-slate-600">{l}</span></div>
              ))}
            </div>"""

if old_legend in text:
    text = text.replace(old_legend, new_legend, 1)


with open('frontend/src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
print("Frontend patched")
