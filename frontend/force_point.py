import io

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = """        if (map.getLayer('sic-points')) map.removeLayer('sic-points');
        map.addLayer({
          id: 'sic-points', type: 'circle', source: 'sic-forecast',
          paint: {
            'circle-color': '#ff0000',
            'circle-radius': 5
          }
        });"""

replacement = """        if (map.getLayer('sic-points')) map.removeLayer('sic-points');
        if (!map.getSource('test-source')) {
          map.addSource('test-source', {
            type: 'geojson',
            data: {
              type: 'FeatureCollection',
              features: [{
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [68.0, -66.0] },
                properties: {}
              }]
            }
          });
        }
        map.addLayer({
          id: 'sic-points', type: 'circle', source: 'test-source',
          paint: {
            'circle-color': '#ff0000',
            'circle-radius': 15
          }
        });"""

if target in code:
    code = code.replace(target, replacement)
    with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
        f.write(code)
    print("Forced test point injected!")
else:
    print("Target not found.")
