with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update OnshoreVessels
old_vessels = """  function OnshoreVessels() {
    const { data: vessels, loading } = useVessels();
    const { data: icebergs } = useIcebergs();
    const { data: sicGeoJSON } = useSicForecast(0);
    const demoVessel = vessels?.[0];
    const destCoords = getDestCoords(demoVessel?.destination);
    const { routes: plannedRoutes } = useGenerateRoutes(demoVessel?.lat || -66.247, demoVessel?.lon || 72.341, destCoords[0], destCoords[1], !!demoVessel);
    const [selected, setSelected] = useState(0);"""

new_vessels = """  function OnshoreVessels() {
    const { data: vessels, loading } = useVessels();
    const { data: icebergs } = useIcebergs();
    const { data: sicGeoJSON } = useSicForecast(0);
    const [selected, setSelected] = useState(0);
    const selectedVessel = vessels?.[selected];
    const destCoords = getDestCoords(selectedVessel?.destination);
    const { routes: plannedRoutes } = useGenerateRoutes(selectedVessel?.lat || -66.247, selectedVessel?.lon || 72.341, destCoords[0], destCoords[1], !!selectedVessel);"""

if old_vessels in text:
    text = text.replace(old_vessels, new_vessels, 1)

old_map_call = """          <LiveMap vessels={vessels || []} icebergs={icebergs || []} routes={plannedRoutes} forecastGeoJSON={sicGeoJSON} />
        </div>
      </div>
    );"""

new_map_call = """          <LiveMap 
            vessels={vessels || []} 
            icebergs={icebergs || []} 
            routes={plannedRoutes} 
            forecastGeoJSON={sicGeoJSON} 
            center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined}
            zoom={selectedVessel ? 5 : undefined}
          />
        </div>
      </div>
    );"""

if old_map_call in text:
    text = text.replace(old_map_call, new_map_call, 1)

# 2. Update LiveMap to respond to center changes
old_heat = """  // ── SIC heatmap ────────────────────────────────────────────────────────────"""

new_heat = """  // ── FlyTo Center ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapReady && inst.current && center) {
      inst.current.flyTo({ center, zoom: zoom || 3.5, essential: true, duration: 1500 });
    }
  }, [center?.[0], center?.[1], zoom, mapReady]);

  // ── SIC heatmap ────────────────────────────────────────────────────────────"""

if old_heat in text:
    text = text.replace(old_heat, new_heat, 1)

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
print("Patched OnshoreVessels and LiveMap")
