import io
with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = """        map.addLayer({
          id: 'sic-heat', type: 'heatmap', source: 'sic-forecast',
          paint: {
            'heatmap-weight': weightProp,
            'heatmap-intensity': 1.2,
            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], ...colorStops],
            'heatmap-radius': 45,
            'heatmap-opacity': 0.7
          }
        });"""
replacement = """        if (heatmapType !== 'none') {
          map.addLayer({
            id: 'sic-heat', type: 'heatmap', source: 'sic-forecast',
            paint: {
              'heatmap-weight': weightProp,
              'heatmap-intensity': 1.2,
              'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], ...colorStops],
              'heatmap-radius': 45,
              'heatmap-opacity': 0.8
            }
          });
        }"""
code = code.replace(target, replacement)

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)
