import re

filepath = 'src/app/page.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update OnshoreRoute destination logic
old_onshore_route = '''          const res = await fetch('/api/routes/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_lat: vessel.lat, start_lon: vessel.lon, end_lat: -70.766, end_lon: 11.833, vessel_id: vessel.id })
          });'''
new_onshore_route = '''          const dest = getDestCoords(vessel.destination);
          const res = await fetch('/api/routes/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_lat: vessel.lat, start_lon: vessel.lon, end_lat: dest[0], end_lon: dest[1], vessel_id: vessel.id })
          });'''
text = text.replace(old_onshore_route, new_onshore_route)

# 2. Update OnshoreOverview to fetch all fast routes
old_onshore_overview = '''function OnshoreOverview() {
  const { data: overview, loading: loadingOverview } = useDashboardOverview();
  const { data: vessels, loading: loadingVessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: alerts } = useAlerts();
  const { data: sicGeoJSON } = useSicForecast(0);
  const demoVessel = vessels?.[0];
  const destCoords = getDestCoords(demoVessel?.destination);
  const { routes: plannedRoutes } = useGenerateRoutes(demoVessel?.lat || -66.247, demoVessel?.lon || 72.341, destCoords[0], destCoords[1], !!demoVessel);'''

new_onshore_overview = '''function OnshoreOverview() {
  const { data: overview, loading: loadingOverview } = useDashboardOverview();
  const { data: vessels, loading: loadingVessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: alerts } = useAlerts();
  const { data: sicGeoJSON } = useSicForecast(0);
  
  const [plannedRoutes, setPlannedRoutes] = useState<Route[]>([]);
  useEffect(() => {
    if (!vessels || vessels.length === 0) return;
    
    // Flag to prevent race conditions if effect reruns
    let active = true;
    
    Promise.all(vessels.map(async v => {
      const dest = getDestCoords(v.destination);
      try {
        const res = await fetch('/api/routes/generate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ start_lat: v.lat, start_lon: v.lon, end_lat: dest[0], end_lon: dest[1] })
        });
        const data = await res.json();
        const fastRoute = (data.routes || []).find((r: any) => r.type === 'fast');
        if (fastRoute) {
          return { ...fastRoute, type: ${v.id}-fast, routeKind: 'fast', label: ${v.name} (Fast) } as Route;
        }
      } catch (e) {
        console.error(e);
      }
      return null;
    })).then(results => {
      if (active) setPlannedRoutes(results.filter(Boolean) as Route[]);
    });
    
    return () => { active = false; };
  }, [vessels]);'''

text = text.replace(old_onshore_overview, new_onshore_overview)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated OnshoreOverview and OnshoreRoute.")
