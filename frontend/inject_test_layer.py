with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

TEST_BLOCK = """
      // INJECTED TEST LAYER
      try {
        map.addSource('test-line-src', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              properties: {},
              geometry: { type: 'LineString', coordinates: [[70, -66], [75, -68]] }
            }]
          }
        });
        map.addLayer({
          id: 'test-line-layer',
          type: 'line',
          source: 'test-line-src',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#ff00ff', 'line-width': 10 }
        });
      } catch (e) { console.error(e); }
"""

import re
old = "console.log(\"Map style.load finished\"); setMapReady(true);"
new = TEST_BLOCK + "\n      " + old

if old in text:
    text = text.replace(old, new, 1)
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Injected test layer")
else:
    print("Could not find insertion point")
