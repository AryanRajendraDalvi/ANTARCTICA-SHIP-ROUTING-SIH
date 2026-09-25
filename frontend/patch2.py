import re
with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix sic-forecast
text = text.replace(
    '''      const src = map.getSource('sic-forecast') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }''',
    '''      if (!map.isStyleLoaded()) { setTimeout(update, 200); return; }
      const src = map.getSource('sic-forecast') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }'''
)

# Fix route-eco
text = text.replace(
    '''      const src = map.getSource('route-eco') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }''',
    '''      if (!map.isStyleLoaded()) { setTimeout(update, 200); return; }
      const src = map.getSource('route-eco') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }'''
)

# Fix icebergs
text = text.replace(
    '''      const src = map.getSource('icebergs') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }''',
    '''      if (!map.isStyleLoaded()) { setTimeout(update, 200); return; }
      const src = map.getSource('icebergs') as maplibregl.GeoJSONSource;
      if (!src) { setTimeout(update, 200); return; }'''
)

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
