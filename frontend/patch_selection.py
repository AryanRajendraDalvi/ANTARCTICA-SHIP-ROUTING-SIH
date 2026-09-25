with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# 1. Fix OnshoreVessels
text = re.sub(
    r'const demoVessel = vessels\?\.\[0\];\s*const destCoords = getDestCoords\(demoVessel\?\.destination\);\s*const \{ routes: plannedRoutes \} = useGenerateRoutes\(demoVessel\?\.lat \|\| -66\.247, demoVessel\?\.lon \|\| 72\.341, destCoords\[0\], destCoords\[1\], !!demoVessel\);\s*const \[selected, setSelected\] = useState\(0\);',
    r'const [selected, setSelected] = useState(0);\n  const selectedVessel = vessels?.[selected];\n  const destCoords = getDestCoords(selectedVessel?.destination);\n  const { routes: plannedRoutes } = useGenerateRoutes(selectedVessel?.lat || -66.247, selectedVessel?.lon || 72.341, destCoords[0], destCoords[1], !!selectedVessel);',
    text
)

# 2. Fix the LiveMap call in OnshoreVessels
text = re.sub(
    r'<LiveMap vessels=\{vessels \|\| \[\]\} icebergs=\{icebergs \|\| \[\]\} routes=\{plannedRoutes\} forecastGeoJSON=\{sicGeoJSON\} />',
    r'<LiveMap vessels={vessels || []} icebergs={icebergs || []} routes={plannedRoutes} forecastGeoJSON={sicGeoJSON} center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined} zoom={selectedVessel ? 5 : undefined} />',
    text
)

# 3. Add explicit re-render when routes change to LiveMap
# Look for map.on('render', renderRoutes);
render_hook = r"map\.on\('render', renderRoutes\);"
render_hook_new = """map.on('render', renderRoutes);

    // Also trigger immediately when routes update to avoid waiting for a pan/zoom
    map.on('sourcedata', (e) => {
      if (e.isSourceLoaded) renderRoutes();
    });
"""
if render_hook in text and "map.on('sourcedata'" not in text:
    text = text.replace(render_hook, render_hook_new)


with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Patch applied successfully")
