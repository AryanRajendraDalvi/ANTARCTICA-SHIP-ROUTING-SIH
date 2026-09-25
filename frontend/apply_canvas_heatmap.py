import io, re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Remove the broken setWorkerUrl CDN line
code = code.replace(
    "maplibregl.setWorkerUrl('https://unpkg.com/maplibre-gl@4.7.0/dist/maplibre-gl.js');\n",
    ""
)

# 2. Replace the entire SharedMap function with new canvas-based version
# Find where SharedMap starts and ends
start_marker = "function SharedMap({"
end_marker = "\nfunction OnshoreOverview()"

start_idx = code.index(start_marker)
end_idx = code.index(end_marker)

shared_map_block = code[start_idx:end_idx]

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
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const inst = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const routeMarkersRef = useRef<maplibregl.Marker[]>([]);
  const icebergMarkersRef = useRef<maplibregl.Marker[]>([]);

  // Use refs so the render loop always reads current values without re-binding
  const routesRef = useRef<Route[]>([]);
  const vesselsRef = useRef<Vessel[]>([]);
  const forecastRef = useRef<any>(null);
  const heatmapTypeRef = useRef<string>('none');

  routesRef.current = routes || [];
  vesselsRef.current = vessels || [];
  forecastRef.current = forecastGeoJSON;
  heatmapTypeRef.current = heatmapType;

  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const isCoordinate = (lon: unknown, lat: unknown): lon is number =>
    typeof lon === 'number' && typeof lat === 'number' &&
    Number.isFinite(lon) && Number.isFinite(lat) &&
    lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;

  // --- Color helpers for canvas heatmap ---
  function hexToRgb(hex: string) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
  }

  function getHeatColor(val: number, type: string): string {
    // Returns hex color for a normalized 0-1 value
    if (type === 'sic' || type === 'sea ice') {
      // Blue (low) → Cyan → Yellow → Orange → Red (high)
      if (val < 0.2)  return '#1e40af';
      if (val < 0.35) return '#3b82f6';
      if (val < 0.5)  return '#60a5fa';
      if (val < 0.65) return '#fde047';
      if (val < 0.8)  return '#f97316';
      return '#dc2626';
    } else if (type === 'weather') {
      // Wind speed: calm=green → moderate=blue → strong=purple
      if (val < 0.2)  return '#22c55e';
      if (val < 0.4)  return '#06b6d4';
      if (val < 0.65) return '#3b82f6';
      if (val < 0.85) return '#8b5cf6';
      return '#a855f7';
    } else if (type === 'ocean currents') {
      // Slow=light orange → fast=dark red
      if (val < 0.25) return '#fed7aa';
      if (val < 0.5)  return '#fb923c';
      if (val < 0.75) return '#ef4444';
      return '#9f1239';
    } else if (type === 'waves') {
      // Calm=teal → moderate=cyan → rough=blue
      if (val < 0.2)  return '#99f6e4';
      if (val < 0.4)  return '#22d3ee';
      if (val < 0.65) return '#0ea5e9';
      if (val < 0.85) return '#2563eb';
      return '#1e3a8a';
    }
    return '#3b82f6';
  }

  function normalizeValue(raw: number, type: string): number {
    if (type === 'sic' || type === 'sea ice') return Math.max(0, Math.min(1, raw));
    if (type === 'weather') return Math.max(0, Math.min(1, raw / 40));   // 0-40 kn
    if (type === 'ocean currents') return Math.max(0, Math.min(1, raw / 1.5)); // 0-1.5 m/s
    if (type === 'waves') return Math.max(0, Math.min(1, raw / 6));      // 0-6 m
    return Math.max(0, Math.min(1, raw));
  }

  // --- Canvas heatmap renderer ---
  const drawHeatmap = useCallback((map: maplibregl.Map) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Resize canvas to match container
    const container = map.getContainer();
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const type = heatmapTypeRef.current;
    if (type === 'none') return;

    const features = forecastRef.current?.features;
    if (!features || features.length === 0) return;

    const prop = type === 'weather' ? 'wind'
      : type === 'ocean currents' ? 'currents'
      : type === 'waves' ? 'waves'
      : 'sic';

    // First pass: draw blended gradient blobs
    ctx.globalCompositeOperation = 'source-over';

    features.forEach((f: any) => {
      const raw = f.properties[prop];
      if (raw === undefined || raw === null) return;
      const val = normalizeValue(raw, type);
      if (val <= 0.02) return; // Skip near-zero values for organic edges

      const [lon, lat] = f.geometry.coordinates;
      const pt = map.project([lon, lat] as [number, number]);

      // Calculate pixel radius by projecting a neighbor point
      // Grid is 1.5 degrees. Use east/north neighbors to get px coverage.
      const ptE = map.project([Math.min(lon + 1.5, 179.9), lat] as [number, number]);
      const ptN = map.project([lon, Math.max(lat - 1.5, -89.9)] as [number, number]);
      let rx = Math.abs(ptE.x - pt.x) * 0.85;
      let ry = Math.abs(ptN.y - pt.y) * 0.85;

      // Clamp to sensible values
      rx = Math.max(15, Math.min(rx, 200));
      ry = Math.max(15, Math.min(ry, 400));

      const hexColor = getHeatColor(val, type);
      const [r, g, b] = hexToRgb(hexColor);
      const alpha = 0.55 + val * 0.25; // 0.55 - 0.8 opacity based on intensity

      // Draw elliptical gradient blob using canvas transform
      const grd = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      grd.addColorStop(0,   `rgba(${r},${g},${b},${alpha})`);
      grd.addColorStop(0.5, `rgba(${r},${g},${b},${alpha * 0.6})`);
      grd.addColorStop(1,   `rgba(${r},${g},${b},0)`);

      ctx.save();
      ctx.translate(pt.x, pt.y);
      ctx.scale(rx, ry);
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.arc(0, 0, 1, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    });
  }, []);

  useEffect(() => {
    if (inst.current) return;
    
    const map = new maplibregl.Map({
      container: ref.current!,
      style: {
        version: 8,
        sources: { sat: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256 } },
        layers: [{ id: 'sat', type: 'raster', source: 'sat' }]
      },
      center,
      zoom,
      pitch: 45,
      attributionControl: false,
    });
    
    inst.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

    map.on('error', (event) => {
      setMapError(event.error?.message || 'Map layer failed to load');
    });

    map.on('style.load', () => {
      if (inst.current !== map) return;
      setMapReady(true);
      setMapError(null);
    });

    // Combined render loop: routes (SVG) + heatmap (Canvas)
    const renderOverlay = () => {
      if (!svgRef.current || !map) return;
      let html = '';

      routesRef.current.forEach(route => {
        const vessel = route.vesselId ? vesselsRef.current.find(v => v.id === route.vesselId) : undefined;
        const coords: [number, number][] = route.waypoints
          .filter(wp => isCoordinate(wp.lon, wp.lat))
          .map(wp => [wp.lon, wp.lat] as [number, number]);

        if (coords.length > 0 && vessel && isCoordinate(vessel.lon, vessel.lat)) {
          coords[0] = [vessel.lon, vessel.lat];
        }

        if (coords.length < 2) return;

        const pts = coords.map(c => {
          const pt = map.project(c as [number, number]);
          return `${pt.x},${pt.y}`;
        });

        const color = route.color || '#3b82f6';
        const isEco = route.routeKind === 'eco' || route.type === 'eco';
        const dash = isEco ? 'stroke-dasharray="6 6"' : '';
        
        html += `<path d="M ${pts.join(' L ')}" fill="none" stroke="#0f172a" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" opacity="0.75" />`;
        html += `<path d="M ${pts.join(' L ')}" fill="none" stroke="${color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.95" ${dash} />`;
      });

      svgRef.current.innerHTML = html;
      drawHeatmap(map);
    };

    map.on('render', renderOverlay);

    return () => {
      map.off('render', renderOverlay);
      markersRef.current.forEach(m => m.remove());
      markersRef.current = [];
      routeMarkersRef.current.forEach(m => m.remove());
      routeMarkersRef.current = [];
      icebergMarkersRef.current.forEach(m => m.remove());
      icebergMarkersRef.current = [];
      map.remove();
      inst.current = null;
      setMapReady(false);
    };
  }, []);

  // ── Vessel Markers ──────────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    markersRef.current.forEach(marker => marker.remove());
    markersRef.current = [];

    (vessels || []).filter(v => isCoordinate(v.lon, v.lat)).forEach(v => {
      const el = document.createElement('div');
      el.style.cssText = `width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 4px 6px -1px rgba(0,0,0,.4);cursor:pointer;background-color:${v.color}`;
      const popup = new maplibregl.Popup({ offset: 15, closeButton: false })
        .setHTML(`
          <div class="p-2 text-xs">
            <div class="font-bold border-b pb-1 mb-1">${v.name}</div>
            <div class="grid grid-cols-2 gap-x-3 gap-y-1 mt-2">
              <span class="text-slate-500">Speed</span><span class="font-medium">${v.speed_kn} kn</span>
              <span class="text-slate-500">Heading</span><span class="font-medium">${v.heading_deg}&deg;</span>
              <span class="text-slate-500">Status</span><span class="font-medium text-blue-600">${v.status}</span>
            </div>
          </div>
        `);
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([v.lon!, v.lat!])
        .setPopup(popup)
        .addTo(map);
      markersRef.current.push(marker);
    });
  }, [vessels, mapReady]);

  // ── Destination Markers ───────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    routeMarkersRef.current.forEach(m => m.remove());
    routeMarkersRef.current = [];

    (routes || []).forEach(route => {
      const ep = route.waypoints.at(-1);
      if (!ep || !isCoordinate(ep.lon, ep.lat)) return;
      const el = document.createElement('div');
      el.title = `${route.label} destination`;
      el.style.cssText = 'width:12px;height:12px;transform:rotate(45deg);border:2px solid white;box-shadow:0 1px 5px rgba(15,23,42,.8)';
      el.style.backgroundColor = route.color || '#3b82f6';
      const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([ep.lon, ep.lat])
        .addTo(map);
      routeMarkersRef.current.push(marker);
    });
    if (map) map.triggerRepaint();
  }, [routes, mapReady]);

  // ── Iceberg Markers ──────────────────────────────────────────────────────
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;
    icebergMarkersRef.current.forEach(m => m.remove());
    icebergMarkersRef.current = [];

    (icebergs || []).forEach(b => {
      if (!isCoordinate(b.lon, b.lat)) return;
      const el = document.createElement('div');
      const size = b.risk === 'High' ? 14 : b.risk === 'Medium' ? 10 : 7;
      const color = b.risk === 'High' ? '#ef4444' : b.risk === 'Medium' ? '#f97316' : '#e2e8f0';
      el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background-color:${color};border:1px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);cursor:pointer;`;
      
      const popup = new maplibregl.Popup({ offset: size/2 })
        .setHTML(`<div class="p-2 text-xs"><div class="font-bold">${b.id}</div><div>Size: ${b.size_cat} (${b.size_km} km)</div><div>Drift: ${b.drift_speed_kn} kn @ ${b.drift_dir_deg}&deg;</div><div class="mt-1 font-bold text-${b.risk === 'High' ? 'red' : 'orange'}-600">Risk: ${b.risk}</div></div>`);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([b.lon, b.lat])
        .setPopup(popup)
        .addTo(map);
      icebergMarkersRef.current.push(marker);
    });
  }, [icebergs, mapReady]);

  // Trigger repaint whenever forecast data or type changes so canvas redraws
  useEffect(() => {
    if (inst.current && mapReady) {
      inst.current.triggerRepaint();
    }
  }, [forecastGeoJSON, heatmapType, mapReady]);

  return (
    <div className="w-full h-full relative bg-slate-900 rounded-lg overflow-hidden">
      <div ref={ref} className="absolute inset-0 w-full h-full" />
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none z-5" style={{ mixBlendMode: 'multiply' }} />
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
print("Canvas heatmap applied successfully!")
print(f"New file size: {len(code)} bytes")
