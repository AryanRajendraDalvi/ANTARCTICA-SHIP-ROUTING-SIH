import io

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Remove canvasRef and all canvas-related code
# Replace the entire SharedMap function with the new raster image approach

start_marker = "function SharedMap({"
end_marker = "\nfunction OnshoreOverview()"

start_idx = code.index(start_marker)
end_idx = code.index(end_marker)

new_shared_map = '''function SharedMap({
  vessels, icebergs, routes, forecastGeoJSON, heatmapType = 'none', zoom = 3.5,
  center = [68.0, -66.0] as [number, number]
}: {
  vessels?: Vessel[];
  icebergs?: Iceberg[];
  routes?: Route[];
  forecastGeoJSON?: GeoJSON.FeatureCollection;
  heatmapType?: string;
  zoom?: number;
  center?: [number, number];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const inst = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const routeMarkersRef = useRef<maplibregl.Marker[]>([]);
  const icebergMarkersRef = useRef<maplibregl.Marker[]>([]);
  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];

  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const isCoordinate = (lon: unknown, lat: unknown): lon is number =>
    typeof lon === 'number' && typeof lat === 'number' &&
    Number.isFinite(lon) && Number.isFinite(lat) &&
    lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;

  // Map initialization
  useEffect(() => {
    if (inst.current) return;
    const map = new maplibregl.Map({
      container: ref.current!,
      style: {
        version: 8,
        sources: { sat: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256 } },
        layers: [{ id: 'sat', type: 'raster', source: 'sat' }]
      },
      center, zoom, pitch: 45, attributionControl: false,
    });
    inst.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('error', (event) => setMapError(event.error?.message || 'Map error'));
    map.on('style.load', () => { if (inst.current === map) { setMapReady(true); setMapError(null); } });

    const renderRoutes = () => {
      if (!svgRef.current || !map) return;
      let html = '';
      routesRef.current.forEach(route => {
        const vessel = route.vesselId ? vesselsRef.current.find(v => v.id === route.vesselId) : undefined;
        const coords: [number, number][] = route.waypoints
          .filter(wp => isCoordinate(wp.lon, wp.lat))
          .map(wp => [wp.lon, wp.lat] as [number, number]);
        if (coords.length > 0 && vessel && isCoordinate(vessel.lon, vessel.lat)) coords[0] = [vessel.lon, vessel.lat];
        if (coords.length < 2) return;
        const pts = coords.map(c => { const pt = map.project(c as [number, number]); return `${pt.x},${pt.y}`; });
        const color = route.color || '#3b82f6';
        const dash = (route.routeKind === 'eco' || route.type === 'eco') ? 'stroke-dasharray="6 6"' : '';
        html += `<path d="M ${pts.join(' L ')}" fill="none" stroke="#0f172a" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" opacity="0.75" />`;
        html += `<path d="M ${pts.join(' L ')}" fill="none" stroke="${color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.95" ${dash} />`;
      });
      svgRef.current.innerHTML = html;
    };
    map.on('render', renderRoutes);

    return () => {
      map.off('render', renderRoutes);
      markersRef.current.forEach(m => m.remove()); markersRef.current = [];
      routeMarkersRef.current.forEach(m => m.remove()); routeMarkersRef.current = [];
      icebergMarkersRef.current.forEach(m => m.remove()); icebergMarkersRef.current = [];
      map.remove(); inst.current = null; setMapReady(false);
    };
  }, []);

  // ── Raster overlay (PNG from backend) ──────────────────────────────────────
  // This is the correct approach for scientific gridded data:
  // Backend generates a colored RGBA PNG → MapLibre displays as image source
  // Zero web-worker dependency, pixel-perfect scientific visualization
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;

    const SOURCE_ID = 'env-raster';
    const LAYER_ID  = 'env-raster-layer';

    // Remove existing raster overlay
    if (map.getLayer(LAYER_ID))  map.removeLayer(LAYER_ID);
    if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);

    if (heatmapType === 'none') return;

    const layerMap: Record<string, string> = {
      'sic': 'sic', 'sea ice': 'sic',
      'weather': 'weather',
      'ocean currents': 'currents',
      'waves': 'waves',
    };
    const apiType = layerMap[heatmapType] || 'sic';
    const url = `/api/layers/${apiType}.png?step=0&_=${Date.now()}`;

    // Geographic bounds of the PNG: Southern Ocean coverage
    // MapLibre image source coordinates: [top-left, top-right, bottom-right, bottom-left] as [lon, lat]
    const coords: [[number,number],[number,number],[number,number],[number,number]] = [
      [-180, -48],  // top-left
      [ 180, -48],  // top-right
      [ 180, -82],  // bottom-right
      [-180, -82],  // bottom-left
    ];

    map.addSource(SOURCE_ID, { type: 'image', url, coordinates: coords });
    map.addLayer({
      id: LAYER_ID, type: 'raster', source: SOURCE_ID,
      paint: { 'raster-opacity': 0.82, 'raster-fade-duration': 300 }
    });

  }, [heatmapType, mapReady]);

  // ── Vessel Markers ───────────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    markersRef.current.forEach(m => m.remove()); markersRef.current = [];
    (vessels || []).filter(v => isCoordinate(v.lon, v.lat)).forEach(v => {
      const el = document.createElement('div');
      el.style.cssText = `width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 4px 6px -1px rgba(0,0,0,.4);cursor:pointer;background-color:${v.color}`;
      const popup = new maplibregl.Popup({ offset: 15, closeButton: false })
        .setHTML(`<div class="p-2 text-xs"><div class="font-bold border-b pb-1 mb-1">${v.name}</div><div class="grid grid-cols-2 gap-x-3 gap-y-1 mt-2"><span class="text-slate-500">Speed</span><span class="font-medium">${v.speed_kn} kn</span><span class="text-slate-500">Heading</span><span class="font-medium">${v.heading_deg}&deg;</span><span class="text-slate-500">Status</span><span class="font-medium text-blue-600">${v.status}</span></div></div>`);
      markersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([v.lon!, v.lat!]).setPopup(popup).addTo(map));
    });
  }, [vessels, mapReady]);

  // ── Destination Markers ──────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    routeMarkersRef.current.forEach(m => m.remove()); routeMarkersRef.current = [];
    (routes || []).forEach(route => {
      const ep = route.waypoints.at(-1);
      if (!ep || !isCoordinate(ep.lon, ep.lat)) return;
      const el = document.createElement('div');
      el.title = `${route.label} destination`;
      el.style.cssText = 'width:12px;height:12px;transform:rotate(45deg);border:2px solid white;box-shadow:0 1px 5px rgba(15,23,42,.8)';
      el.style.backgroundColor = route.color || '#3b82f6';
      routeMarkersRef.current.push(new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([ep.lon, ep.lat]).addTo(map));
    });
    if (map) map.triggerRepaint();
  }, [routes, mapReady]);

  // ── Iceberg Markers ──────────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    icebergMarkersRef.current.forEach(m => m.remove()); icebergMarkersRef.current = [];
    (icebergs || []).forEach(b => {
      if (!isCoordinate(b.lon, b.lat)) return;
      const el = document.createElement('div');
      const size = b.risk === 'High' ? 14 : b.risk === 'Medium' ? 10 : 7;
      const color = b.risk === 'High' ? '#ef4444' : b.risk === 'Medium' ? '#f97316' : '#e2e8f0';
      el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background-color:${color};border:1px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);cursor:pointer;`;
      const popup = new maplibregl.Popup({ offset: size/2 })
        .setHTML(`<div class="p-2 text-xs"><div class="font-bold">${b.id}</div><div>Size: ${b.size_cat} (${b.size_km} km)</div><div>Drift: ${b.drift_speed_kn} kn @ ${b.drift_dir_deg}&deg;</div><div class="mt-1 font-bold text-${b.risk === 'High' ? 'red' : 'orange'}-600">Risk: ${b.risk}</div></div>`);
      icebergMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([b.lon, b.lat]).setPopup(popup).addTo(map));
    });
  }, [icebergs, mapReady]);

  return (
    <div className="w-full h-full relative bg-slate-900 rounded-lg overflow-hidden">
      <div ref={ref} className="absolute inset-0 w-full h-full" />
      <svg ref={svgRef} className="absolute inset-0 w-full h-full pointer-events-none z-10" />
      {mapError && (
        <div className="absolute bottom-3 left-3 z-30 max-w-md rounded bg-red-700/95 px-3 py-2 text-[10px] font-medium text-white shadow">
          Map: {mapError}
        </div>
      )}
    </div>
  );
}

'''

code = code[:start_idx] + new_shared_map + code[end_idx + 1:]

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)
print("Raster image heatmap applied!")
print(f"File size: {len(code)} bytes")
