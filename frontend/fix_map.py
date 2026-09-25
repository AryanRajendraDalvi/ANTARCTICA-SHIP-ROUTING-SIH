with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add routeSourcesRef declaration after routeMarkersRef
OLD_REF = "  const routeMarkersRef = useRef<maplibregl.Marker[]>([]);"
NEW_REF = """  const routeMarkersRef = useRef<maplibregl.Marker[]>([]);
  const routeSourceIdsRef = useRef<string[]>([]);"""

# 2. Replace the single fleet-routes GeoJSON effect with per-route sources
OLD_EFFECT = """  // ── Fleet routes → native MapLibre GeoJSON layer ──────────────────────────
  // All routes are packed into one FeatureCollection so MapLibre renders them
  // natively — zero SVG projection, pixel-perfect alignment at every zoom level.
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;

    const features: GeoJSON.Feature[] = (routes || [])
      .map(route => {
        const vessel = route.vesselId
          ? vessels?.find(v => v.id === route.vesselId)
          : undefined;

        const coords: [number, number][] = route.waypoints
          .filter(wp => isCoordinate(wp.lon, wp.lat))
          .map(wp => [wp.lon, wp.lat] as [number, number]);

        // Pin first coordinate to live vessel position — same coord system as Marker
        if (coords.length > 0 && vessel && isCoordinate(vessel.lon, vessel.lat)) {
          coords[0] = [vessel.lon, vessel.lat];
        }

        if (coords.length < 2) return null;

        return {
          type: 'Feature' as const,
          properties: {
            routeId: route.type,
            routeColor: route.color || '#3b82f6',
            kind: route.routeKind || route.type,
            label: route.label,
          },
          geometry: { type: 'LineString' as const, coordinates: coords },
        };
      })
      .filter(Boolean) as GeoJSON.Feature[];

    (map.getSource('fleet-routes') as maplibregl.GeoJSONSource | undefined)
      ?.setData({ type: 'FeatureCollection', features });
  }, [routes, vessels, mapReady]);"""

NEW_EFFECT = """  // ── Fleet routes — one GeoJSON source per route, color hardcoded per layer ──
  // Using individual sources avoids data-driven color expressions (which can
  // silently fail in some MapLibre builds). Each route gets its own
  // source + 2 layers (casing + line) with the vessel color baked in.
  useEffect(() => {
    const map = inst.current;
    if (!map || !mapReady) return;

    // Remove previously created route layers and sources
    routeSourceIdsRef.current.forEach(sid => {
      try { if (map.getLayer(`${sid}-line`)) map.removeLayer(`${sid}-line`); } catch (_) {}
      try { if (map.getLayer(`${sid}-casing`)) map.removeLayer(`${sid}-casing`); } catch (_) {}
      try { if (map.getSource(sid)) map.removeSource(sid); } catch (_) {}
    });
    routeSourceIdsRef.current = [];

    (routes || []).forEach((route, idx) => {
      const vessel = route.vesselId
        ? vessels?.find(v => v.id === route.vesselId)
        : undefined;

      const coords: [number, number][] = route.waypoints
        .filter(wp => isCoordinate(wp.lon, wp.lat))
        .map(wp => [wp.lon, wp.lat] as [number, number]);

      // Anchor first point to exact vessel position (same WebGL frame as Marker)
      if (coords.length > 0 && vessel && isCoordinate(vessel.lon, vessel.lat)) {
        coords[0] = [vessel.lon, vessel.lat];
      }

      if (coords.length < 2) return;

      const color = route.color || '#3b82f6';
      const sid = `r-${idx}`;

      try {
        map.addSource(sid, {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              properties: { label: route.label },
              geometry: { type: 'LineString', coordinates: coords },
            }],
          },
        });
        map.addLayer({
          id: `${sid}-casing`, type: 'line', source: sid,
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#0f172a', 'line-width': 7, 'line-opacity': 0.7 },
        });
        map.addLayer({
          id: `${sid}-line`, type: 'line', source: sid,
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': color, 'line-width': 3.5, 'line-opacity': 0.95 },
        });
        routeSourceIdsRef.current.push(sid);
      } catch (e) {
        console.warn('Route layer error:', e);
      }
    });
  }, [routes, vessels, mapReady]);"""

if OLD_REF not in text:
    print('ERROR: OLD_REF not found')
elif OLD_EFFECT not in text:
    print('ERROR: OLD_EFFECT not found — showing surrounding context:')
    idx = text.find('Fleet routes')
    print(repr(text[idx:idx+500]))
else:
    text = text.replace(OLD_REF, NEW_REF, 1)
    text = text.replace(OLD_EFFECT, NEW_EFFECT, 1)
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print('SUCCESS: Replaced fleet-routes effect with per-route sources.')
