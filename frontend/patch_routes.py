import re

filepath = 'src/app/page.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Add getDestCoords helper at the top
helper = '''
function getDestCoords(destName?: string): [number, number] {
  if (!destName) return [-70.766, 11.833];
  if (destName.includes('Bharati')) return [-69.400, 76.183];
  if (destName.includes('Cape Town')) return [-33.925, 18.423];
  if (destName.includes('Port Louis')) return [-20.160, 57.501];
  if (destName.includes('Mormugao')) return [15.40, 73.80];
  if (destName.includes('Chennai')) return [13.08, 80.27];
  return [-70.766, 11.833];
}
'''
text = text.replace("import { twMerge } from 'tailwind-merge';", "import { twMerge } from 'tailwind-merge';\n" + helper)

# Patch OnshoreOverview
old_oo = '''  const { data: sicGeoJSON } = useSicForecast(0);
  const { routes: plannedRoutes } = useGenerateRoutes(-66.247, 72.341, -70.766, 11.833, true);'''
new_oo = '''  const { data: sicGeoJSON } = useSicForecast(0);
  const demoVessel = vessels?.[0];
  const destCoords = getDestCoords(demoVessel?.destination);
  const { routes: plannedRoutes } = useGenerateRoutes(demoVessel?.lat || -66.247, demoVessel?.lon || 72.341, destCoords[0], destCoords[1], !!demoVessel);'''
text = text.replace(old_oo, new_oo)

# Patch OnshoreVessels
old_ov = '''  const { data: sicGeoJSON } = useSicForecast(0);
  const { routes: plannedRoutes } = useGenerateRoutes(-66.247, 72.341, -70.766, 11.833, true);
  const [selected, setSelected] = useState(0);'''
new_ov = '''  const { data: sicGeoJSON } = useSicForecast(0);
  const [selected, setSelected] = useState(0);
  const sel = vessels?.[selected];
  const destCoords = getDestCoords(sel?.destination);
  const { routes: plannedRoutes } = useGenerateRoutes(sel?.lat || -66.247, sel?.lon || 72.341, destCoords[0], destCoords[1], !!sel);'''
text = text.replace(old_ov, new_ov)

# Patch OnboardWaypointsPanel
old_owp = '''  const { data: vessels } = useVessels();
  const { data: sicGeoJSON } = useSicForecast(0);
  const { routes } = useGenerateRoutes(-66.247, 72.341, -70.766, 11.833, true);'''
new_owp = '''  const { data: vessels } = useVessels();
  const { data: sicGeoJSON } = useSicForecast(0);
  const v = vessels?.[0];
  const destCoords = getDestCoords(v?.destination);
  const { routes } = useGenerateRoutes(v?.lat || -66.247, v?.lon || 72.341, destCoords[0], destCoords[1], !!v);'''
text = text.replace(old_owp, new_owp)

# Also fix OnboardRouteOptimizer
old_oro = '''  const { data: vessels } = useVessels();
  const { data: sicGeoJSON } = useSicForecast(0);
  const { routes: generatedRoutes, loading: generating } = useGenerateRoutes(-66.247, 72.341, -70.766, 11.833, true);'''
new_oro = '''  const { data: vessels } = useVessels();
  const { data: sicGeoJSON } = useSicForecast(0);
  const v = vessels?.[0];
  const destCoords = getDestCoords(v?.destination);
  const { routes: generatedRoutes, loading: generating } = useGenerateRoutes(v?.lat || -66.247, v?.lon || 72.341, destCoords[0], destCoords[1], !!v);'''
text = text.replace(old_oro, new_oro)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)

print("Dynamic routes patched.")
