"use client";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { twMerge } from 'tailwind-merge';
import clsx from 'clsx';
import {
  Navigation, Map as MapIcon, Thermometer, Ship, BarChart2, Bell, FileText, Search, User,
  Crosshair, Layers, Settings, AlertTriangle, Info, Wind, Droplets, Activity, Clock,
  CheckCircle2, ChevronDown, MonitorSmartphone, MessageSquare, BookOpen, Eye,
  RefreshCw, Download, Plus, Edit, Trash2, Filter, Loader2, LoaderCircle, CloudSnow, Sun, CloudRain
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar, Legend, AreaChart, Area } from 'recharts';
import jsPDF from 'jspdf';
import { useSicForecast, useDashboardOverview, useVessels, useIcebergs, useIcebergStats, useGenerateRoutes, useAlerts, useWeatherForecast, useFleetRoutes } from '@/hooks/useDashboardData';
const ROUTE_DESTINATIONS = [
  { id: 'maitri', label: 'Maitri Station, Antarctica', lat: -70.766, lon: 11.833 },
  { id: 'bharati', label: 'Bharati Station, Antarctica', lat: -69.400, lon: 76.183 },
  { id: 'davis', label: 'Davis Station, Antarctica', lat: -68.577, lon: 77.967 },
  { id: 'casey', label: 'Casey Station, Antarctica', lat: -66.282, lon: 110.527 },
  { id: 'mcmurdo', label: 'McMurdo Station, Antarctica', lat: -77.842, lon: 166.686 },
  { id: 'rothera', label: 'Rothera Station, Antarctica', lat: -67.568, lon: -68.128 },
  { id: 'mawson', label: 'Mawson Station, Antarctica', lat: -67.603, lon: 62.876 },
  { id: 'zhongshan', label: 'Zhongshan Station, Antarctica', lat: -69.373, lon: 76.377 },
  { id: 'dumont-durville', label: 'Dumont d\'Urville Station, Antarctica', lat: -66.663, lon: 140.002 },
  { id: 'neumayer', label: 'Neumayer Station III, Antarctica', lat: -70.673, lon: -8.274 },
  { id: 'princess-elisabeth', label: 'Princess Elisabeth Station, Antarctica', lat: -71.950, lon: 23.347 },
  { id: 'troll', label: 'Troll Station, Antarctica', lat: -72.011, lon: 2.534 },
  { id: 'sanae', label: 'SANAE IV Station, Antarctica', lat: -71.673, lon: -2.842 },
  { id: 'cape-town', label: 'Cape Town, South Africa', lat: -33.925, lon: 18.423 },
  { id: 'port-louis', label: 'Port Louis, Mauritius', lat: -20.160, lon: 57.501 },
];

function getDestCoords(destName) {
  const destination = ROUTE_DESTINATIONS.find(item => item.label === destName)
    || ROUTE_DESTINATIONS.find(item => destName?.includes(item.label.split(',')[0] || ''))
    || ROUTE_DESTINATIONS[0];
  return [destination.lat, destination.lon];
}

function cn(...inputs) {
  return (0, twMerge)((0, clsx)(inputs));
}
function SharedMap({
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

    // Geographic bounds match backend PNG exactly.
    // IMPORTANT: -90° = y=Infinity in Mercator — must use -85.051 (Web Mercator south limit)
    const coords: [[number,number],[number,number],[number,number],[number,number]] = [
      [-180, -48],     // top-left
      [ 180, -48],     // top-right
      [ 180, -85.051], // bottom-right
      [-180, -85.051], // bottom-left
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

function OnshoreOverview() {
  const { data: stats } = useDashboardOverview();
  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const { data: alerts } = useAlerts();
  const firstVessel = (vessels || [])[0];
  const { routes } = useFleetRoutes(
    ROUTE_DESTINATIONS[0].lat,
    ROUTE_DESTINATIONS[0].lon,
    !!firstVessel
  );

  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="grid grid-cols-4 gap-3 shrink-0">{[{
          icon: <Ship size={20} className="text-blue-500"></Ship>,
          val: (stats?.active_vessels || 0).toString(),
          label: 'Active Vessels',
          bg: 'bg-blue-50'
        }, {
          icon: <MapIcon size={20} className="text-slate-500"></MapIcon>,
          val: (stats?.tracked_icebergs || 0).toString(),
          label: 'Tracked Icebergs',
          bg: 'bg-slate-50'
        }, {
          icon: <Layers size={20} className="text-indigo-500"></Layers>,
          val: (stats?.avg_sic_percent || 0).toFixed(0) + '%',
          sub: 'Sea Ice Concentration',
          bg: 'bg-indigo-50'
        }, {
          icon: <AlertTriangle size={20} className="text-red-500"></AlertTriangle>,
          val: (stats?.active_alerts || 0).toString(),
          label: 'Active Alerts',
          bg: 'bg-red-50'
        }].map((k, i) => <div className="bg-white rounded-lg shadow-sm border border-slate-200 flex items-center p-3 gap-3" key={i}>{<div className={cn('w-10 h-10 rounded-lg flex items-center justify-center shrink-0', k.bg)}>{k.icon}</div>}{<div>{<div className="text-xl font-black text-slate-800">{k.val}</div>}{<div className="text-[10px] text-slate-500">{k.label || k.sub}</div>}</div>}</div>)}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} routes={routes} forecastGeoJSON={forecastGeoJSON}></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-white/95 rounded-md px-3 py-1.5 text-xs font-bold border border-slate-200 shadow flex items-center gap-2 cursor-pointer">Southern Ocean {<ChevronDown size={12}></ChevronDown>}</div>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-36">{['Vessels', 'Icebergs', 'Sea Ice (SIC)'].map((l, i) => <label key={i} className="flex items-center gap-1.5 cursor-pointer">{<input type="checkbox" defaultChecked={true} className="rounded accent-blue-500"></input>}{<span>{l}</span>}</label>)}{<div className="h-px bg-slate-200 my-1"></div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Planned Route</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Alt Route</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-3 h-3 border border-red-400 bg-red-100 rounded-sm"></div>}{<span>Risk Area</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-slate-600 border-dashed border-b-2"></div>}{<span>Iceberg Drift</span>}</div>}</div>}</div>}{<div className="flex-1 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col overflow-hidden">{<div className="p-3 border-b border-slate-100 text-xs font-bold text-slate-800">Recent Activity</div>}{<div className="p-4 space-y-5 overflow-y-auto flex-1">{(alerts || []).slice(0, 4).map((a: any, i: number) => <div key={i} className="relative pl-4 border-l-2" style={{ borderColor: '#3b82f6' }}>{<div className={cn('absolute -left-1.5 top-0 w-2.5 h-2.5 rounded-full', 'bg-blue-500')}></div>}{<div className="text-xs font-bold text-slate-800">{a.vessel_name || a.type}</div>}{<div className="text-[10px] text-slate-500">{a.message}</div>}{<div className="text-[9px] text-slate-400 mt-0.5">{a.time || 'Just now'}</div>}</div>)}</div>}</div>}</div>}</div>;
}
function OnshoreVessels({ onSwitchToOnboard }: { onSwitchToOnboard?: (id: string) => void }) {
  const [selected, setSelected] = useState(0);
  const { data: vesselsData } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const vessels = vesselsData || [];
  const selectedVessel = vessels[selected];

  // Use fleet routes — same source as Operational Overview — so each vessel
  // gets its own unique destination rather than everyone going to ROUTE_DESTINATIONS[0]
  const firstVessel = vessels[0];
  const { routes: allFleetRoutes } = useFleetRoutes(
    ROUTE_DESTINATIONS[0].lat,
    ROUTE_DESTINATIONS[0].lon,
    !!firstVessel
  );

  // For the selected vessel, show only its route (or all if none selected)
  const selectedRoutes = selectedVessel
    ? (allFleetRoutes || []).filter((r: any) => r.vesselId === selectedVessel.id)
    : (allFleetRoutes || []);

  // Find the destination label for the selected vessel
  const selectedRoute = (allFleetRoutes || []).find((r: any) => r.vesselId === selectedVessel?.id);
  const destLabel = selectedRoute?.label || '—';

  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="w-72 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col shrink-0">{<div className="p-3 border-b border-slate-100 flex items-center justify-between">{<span className="text-xs font-bold text-slate-800">Vessels ({vessels.length})</span>}</div>}{<div className="p-2 border-b border-slate-100">{<div className="relative">{<Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"></Search>}{<input className="w-full text-[11px] pl-7 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded" placeholder="Search vessel..."></input>}</div>}</div>}{<div className="flex-1 overflow-y-auto">{vessels.map((v: any, i: number) => {
    const vRoute = (allFleetRoutes || []).find((r: any) => r.vesselId === v.id);
    const vDest = vRoute?.label || '—';
    return <div key={i} onClick={() => setSelected(i)} className={cn('p-3 border-b border-slate-100 cursor-pointer flex items-center gap-3 hover:bg-slate-50', selected === i && 'bg-blue-50 border-l-4 border-blue-500')}>{<div className="w-14 h-12 bg-slate-200 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-400"></Ship>}</div>}{<div className="min-w-0">{<div className="flex items-center gap-1">{<div className={cn('w-1.5 h-1.5 rounded-full shrink-0')} style={{backgroundColor: v.color || '#3b82f6'}}></div>}{<span className="text-xs font-bold text-slate-800 truncate">{v.name}</span>}</div>}{<div className="text-[9px] text-slate-500">{v.type || 'Vessel'}</div>}{<div className="text-[9px] text-slate-600 mt-0.5">Lat: {v.lat?.toFixed(3)} Lon: {v.lon?.toFixed(3)}</div>}{<div className="text-[9px] text-slate-600">Speed: {v.speed_kn} kn Heading: {v.heading_deg}&deg;</div>}{<div className="text-[9px] text-blue-600 font-medium mt-0.5 truncate" title={vDest}>→ {vDest}</div>}</div>}</div>;
  })}</div>}</div>}{<div className="flex-1 flex flex-col gap-3 min-h-0">{selectedVessel && <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 shrink-0 flex items-center gap-4">{<div className="flex items-center gap-2">{<div className="w-2 h-2 rounded-full" style={{backgroundColor: selectedVessel.color || '#3b82f6'}}></div>}{<span className="text-xs font-bold text-slate-800">{selectedVessel.name}</span>}</div>}{<div className="h-4 w-px bg-slate-200"></div>}{<div className="text-[10px] text-slate-500">Destination: <span className="font-bold text-blue-700">{destLabel}</span></div>}{<div className="h-4 w-px bg-slate-200"></div>}{<div className="text-[10px] text-slate-500">Speed: <span className="font-bold text-slate-800">{selectedVessel.speed_kn} kn</span></div>}{<div className="text-[10px] text-slate-500">Heading: <span className="font-bold text-slate-800">{selectedVessel.heading_deg}&deg;</span></div>}{<div className="text-[10px] text-slate-500">Status: <span className="font-bold text-green-600">{selectedVessel.status}</span></div>}{onSwitchToOnboard && <button onClick={() => onSwitchToOnboard(selectedVessel.id)} className="ml-auto text-[10px] font-bold bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded transition-colors flex items-center gap-1.5"><MonitorSmartphone size={11} /> Go to Onboard Panel</button>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} forecastGeoJSON={forecastGeoJSON} routes={selectedRoutes} center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined} zoom={selectedVessel ? 5 : undefined}></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-2">Legend</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Fastest Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Eco Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-3 h-3 border border-blue-500 rounded-full"></div>}{<span>Destination</span>}</div>}</div>}</div>}</div>}</div>;
}

  function OnshoreIceWeather() {
  const [tab, setTab] = (0, useState)('Sea Ice');
  const tabs = ['Sea Ice', 'Weather', 'Ocean Currents', 'Waves'];
  const { data: forecastGeoJSON } = useSicForecast(0);
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-[2] flex flex-col gap-3">{<div className="flex items-center gap-2">{tabs.map(t => <button key={t} onClick={() => setTab(t)} className={cn('px-4 py-1.5 text-xs font-bold rounded-md transition-colors', tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}{<div className="ml-auto text-[10px] text-slate-400 font-medium">12 Sep 2026, 10:45 UTC</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap forecastGeoJSON={forecastGeoJSON} heatmapType={tab.toLowerCase()}></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-[#1e293b]/90 text-white text-[10px] p-2 rounded shadow font-bold">{tab === 'Sea Ice' ? 'Sea Ice Concentration' : tab === 'Weather' ? 'Wind Speed (knots)' : tab === 'Ocean Currents' ? 'Surface Currents (m/s)' : 'Wave Height (m)'}</div>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-28">{<div className="font-bold text-slate-700 mb-1">{tab === 'Sea Ice' ? 'Concentration (%)' : tab === 'Weather' ? 'Wind (kn)' : tab === 'Ocean Currents' ? 'Currents (m/s)' : 'Waves (m)'}</div>}{(tab === 'Sea Ice' ? [['0-20', 'bg-blue-200'], ['20-40', 'bg-blue-400'], ['40-60', 'bg-blue-600'], ['60-80', 'bg-yellow-500'], ['80-100', 'bg-red-600']] : tab === 'Weather' ? [['0-10', 'bg-blue-200'], ['10-20', 'bg-green-400'], ['20-30', 'bg-blue-500'], ['30-40', 'bg-indigo-500'], ['40+', 'bg-purple-500']] : tab === 'Ocean Currents' ? [['0.0-0.2', 'bg-orange-200'], ['0.2-0.4', 'bg-orange-400'], ['0.4-0.6', 'bg-rose-500'], ['0.6+', 'bg-rose-800']] : [['0-1', 'bg-teal-200'], ['1-2', 'bg-teal-400'], ['2-4', 'bg-sky-500'], ['4+', 'bg-sky-800']]).map(([label, color], i) => <div key={i} className="flex items-center gap-2">{<div className={cn('w-3 h-2 rounded-sm', color)}></div>}{<span className="text-slate-600">{label}</span>}</div>)}</div>}</div>}{<div className="h-16 grid grid-cols-4 gap-3 shrink-0">{[{
          icon: <Layers size={18} className="text-blue-500"></Layers>,
          label: 'Ice Thickness',
          val: '0.8 m'
        }, {
          icon: <Thermometer size={18} className="text-cyan-500"></Thermometer>,
          label: 'Air Temperature',
          val: '-11 °C'
        }, {
          icon: <Wind size={18} className="text-sky-500"></Wind>,
          label: 'Wind Speed',
          val: '22 kn (SW)'
        }, {
          icon: <Activity size={18} className="text-indigo-500"></Activity>,
          label: 'Wave Height',
          val: '1.4 m'
        }].map((k, i) => <div className="bg-white rounded-lg border border-slate-200 shadow-sm flex items-center p-2 gap-2">{k.icon}{<div>{<div className="text-[9px] text-slate-500">{k.label}</div>}{<div className="text-sm font-bold text-slate-800">{k.val}</div>}</div>}</div>)}</div>}</div>}</div>;
}
function OnshoreRoute() {

  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const [activeTab, setActiveTab] = useState<'plan'|'compare'|'library'>('plan');
  const [selectedVesselIdx, setSelectedVesselIdx] = useState(0);
  const [destIdx, setDestIdx] = useState(0);
  const [generated, setGenerated] = useState(false);
  const [triggerCount, setTriggerCount] = useState(0);
  const [routeLibrary, setRouteLibrary] = useState<Array<{
    id: number; vesselName: string; destination: string; routes: any[]; generatedAt: string;
  }>>([]);
  const [libraryCounter, setLibraryCounter] = useState(0);

  const selectedVessel = (vessels || [])[selectedVesselIdx];
  const dest = ROUTE_DESTINATIONS[destIdx];

  const { routes, loading: routeLoading } = useGenerateRoutes(
    selectedVessel?.lat || 0, selectedVessel?.lon || 0,
    dest?.lat || 0, dest?.lon || 0,
    generated && !!selectedVessel, triggerCount
  );

  const prevRoutesRef = useRef<any[]>([]);
  useEffect(() => {
    if (generated && routes.length > 0 && routes !== prevRoutesRef.current) {
      prevRoutesRef.current = routes;
      const entry = {
        id: libraryCounter,
        vesselName: selectedVessel?.name || 'Unknown',
        destination: dest?.label || 'Unknown',
        routes,
        generatedAt: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      };
      setRouteLibrary(prev => {
        const existing = prev.findIndex(e => e.vesselName === entry.vesselName && e.destination === entry.destination);
        if (existing >= 0) { const next = [...prev]; next[existing] = entry; return next; }
        return [entry, ...prev];
      });
      setLibraryCounter(c => c + 1);
    }
  }, [routes, generated]);

  function handleVesselChange(e: React.ChangeEvent<HTMLSelectElement>) { setSelectedVesselIdx(Number(e.target.value)); setGenerated(false); }
  function handleDestChange(e: React.ChangeEvent<HTMLSelectElement>) { setDestIdx(Number(e.target.value)); setGenerated(false); }
  function handleGenerate() {
    if (!selectedVessel) return;
    setTriggerCount(c => c + 1);
    setGenerated(true);
    setActiveTab('plan');
  }

  const displayRoutes = generated ? routes : [];
  const isGenerating = generated && routeLoading;

  const ROUTE_META: Record<string, { label: string; color: string; border: string; bg: string; dot: string }> = {
    eco:     { label: 'Eco Route',     color: '#22c55e', border: 'border-green-400', bg: 'bg-green-50',  dot: 'bg-green-500' },
    safe:    { label: 'Safe Route',    color: '#3b82f6', border: 'border-blue-400',  bg: 'bg-blue-50',   dot: 'bg-blue-500' },
    fastest: { label: 'Fastest Route', color: '#ef4444', border: 'border-red-400',   bg: 'bg-red-50',    dot: 'bg-red-500' },
  };
  function routeMeta(r: any) { return ROUTE_META[r.routeKind || r.type] || ROUTE_META['eco']; }

  const planPanel = (
    <div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 shrink-0 overflow-y-auto space-y-4">
      <div>
        <label className="text-[10px] font-bold text-slate-700 block mb-1">Select Vessel</label>
        <select value={selectedVesselIdx} onChange={handleVesselChange} className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">
          {(vessels || []).map((v: any, i: number) => <option key={i} value={i}>{v.name}</option>)}
        </select>
      </div>
      <div>
        <label className="text-[10px] font-bold text-slate-700 block mb-1">Destination</label>
        <select value={destIdx} onChange={handleDestChange} className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">
          {ROUTE_DESTINATIONS.map((d, i) => <option key={i} value={i}>{d.label}</option>)}
        </select>
      </div>
      <div className="border-t border-slate-100 pt-3">
        <div className="text-[10px] font-bold text-slate-700 mb-2">Optimization Priority</div>
        <div className="space-y-2">
          {['Lowest Fuel Consumption', 'Safest Route', 'Fastest Route', 'Avoid High Ice Areas'].map((o, i) => (
            <label key={i} className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
              <input type="checkbox" defaultChecked={i !== 2} className="rounded accent-blue-500" /><span>{o}</span>
            </label>
          ))}
        </div>
      </div>
      <button onClick={handleGenerate} disabled={!selectedVessel || isGenerating}
        className={cn('w-full text-white text-xs font-bold py-2 rounded shadow transition-colors flex items-center justify-center gap-2',
          (!selectedVessel || isGenerating) ? 'bg-slate-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 cursor-pointer')}>
        {isGenerating ? <><LoaderCircle size={13} className="animate-spin" />Generating…</> : 'Generate Routes'}
      </button>
      {generated && !isGenerating && displayRoutes.length > 0 && (
        <div className="text-[10px] text-green-600 font-medium flex items-center gap-1">
          <CheckCircle2 size={11} /> {displayRoutes.length} routes generated
        </div>
      )}
    </div>
  );

  const compareTab = (
    <div className="flex flex-1 flex-col gap-3 min-h-0 overflow-y-auto">
      {displayRoutes.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-white border border-slate-200 rounded-xl shadow px-8 py-6 text-center max-w-sm">
            <BarChart2 size={32} className="text-slate-300 mx-auto mb-2" />
            <div className="text-sm font-bold text-slate-600 mb-1">No Routes to Compare</div>
            <div className="text-[11px] text-slate-400">Go to <span className="font-bold text-blue-600">Plan New Route</span> and click Generate Routes first.</div>
          </div>
        </div>
      ) : (
        <>
          <div className="text-xs font-bold text-slate-700 shrink-0">
            Comparing routes — <span className="text-blue-600">{selectedVessel?.name}</span> → <span className="text-green-600">{dest?.label?.split(',')[0]}</span>
          </div>
          <div className={cn('grid gap-3 shrink-0', displayRoutes.length >= 3 ? 'grid-cols-3' : 'grid-cols-2')}>
            {displayRoutes.map((r: any, i: number) => {
              const meta = routeMeta(r);
              const isWinner = (key: string) => {
                const vals = displayRoutes.map((x: any) => Number(x[key]) || 0);
                const v = Number(r[key]) || 0;
                return key === 'eta_days' || key === 'fuel_mt' || key === 'co2_mt' ? v === Math.min(...vals) : v === Math.max(...vals);
              };
              return (
                <div key={i} className={cn('bg-white rounded-xl border-2 shadow-sm p-4 space-y-3', meta.border)}>
                  <div className="flex items-center gap-2">
                    <div className={cn('w-3 h-3 rounded-full', meta.dot)} />
                    <div className="text-xs font-black text-slate-800">{meta.label}</div>
                  </div>
                  {[
                    { key: 'distance_nm', label: 'Distance', unit: 'nm',   icon: '📍' },
                    { key: 'eta_days',    label: 'ETA',      unit: 'days', icon: '⏱' },
                    { key: 'fuel_mt',     label: 'Fuel',     unit: 'MT',   icon: '⛽' },
                    { key: 'co2_mt',      label: 'CO₂',      unit: 'MT',   icon: '🌱' },
                    { key: 'ice_risk',    label: 'Ice Risk',  unit: '',    icon: '🧊' },
                    { key: 'hull_stress', label: 'Hull Stress', unit: '', icon: '⚙️' },
                  ].map(({ key, label, unit, icon }) => {
                    const val = r[key]; const win = isWinner(key);
                    return (
                      <div key={key} className={cn('rounded-lg p-2 flex items-center justify-between', win ? meta.bg : 'bg-slate-50')}>
                        <span className="text-[10px] text-slate-500">{icon} {label}</span>
                        <span className={cn('text-[11px] font-bold', win ? 'text-green-700' : 'text-slate-700')}>
                          {typeof val === 'number' ? val.toFixed(val < 10 ? 1 : 0) : val}{unit && ` ${unit}`}
                          {win && <span className="ml-1 text-[9px] bg-green-500 text-white rounded px-1">BEST</span>}
                        </span>
                      </div>
                    );
                  })}
                  <button className="w-full text-[10px] font-bold py-1.5 rounded border-2" style={{ borderColor: meta.color, color: meta.color }}>
                    Select This Route
                  </button>
                </div>
              );
            })}
          </div>
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm shrink-0">
            <div className="p-3 border-b border-slate-100 text-xs font-bold text-slate-700">Summary Table</div>
            <table className="w-full text-[10px]">
              <thead><tr className="border-b border-slate-100">
                <th className="text-left p-2 text-slate-500 font-semibold">Metric</th>
                {displayRoutes.map((r: any, i: number) => <th key={i} className="p-2 text-center font-bold" style={{ color: routeMeta(r).color }}>{routeMeta(r).label}</th>)}
              </tr></thead>
              <tbody>
                {[['Distance (nm)', 'distance_nm'],['ETA (days)', 'eta_days'],['Fuel (MT)', 'fuel_mt'],['CO₂ (MT)', 'co2_mt'],['Ice Risk', 'ice_risk'],['Hull Stress', 'hull_stress']].map(([label, key]) => (
                  <tr key={key} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="p-2 text-slate-600">{label}</td>
                    {displayRoutes.map((r: any, i: number) => {
                      const val = r[key]; const numVal = Number(val) || 0;
                      const allNums = displayRoutes.map((x: any) => Number(x[key]) || 0);
                      const best = key === 'eta_days' || key === 'fuel_mt' || key === 'co2_mt' ? numVal === Math.min(...allNums) : numVal === Math.max(...allNums);
                      return <td key={i} className={cn('p-2 text-center font-bold', best ? 'text-green-600' : 'text-slate-700')}>
                        {typeof val === 'number' ? val.toFixed(val < 10 ? 1 : 0) : val}
                      </td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );

  const libraryTab = (
    <div className="flex flex-1 flex-col gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0">
        <div className="text-xs font-bold text-slate-700">Route Library <span className="text-slate-400 font-normal">({routeLibrary.length} entries)</span></div>
        {routeLibrary.length > 0 && (
          <button onClick={() => setRouteLibrary([])} className="text-[10px] text-red-500 hover:text-red-700 font-medium flex items-center gap-1">
            <Trash2 size={10} /> Clear All
          </button>
        )}
      </div>
      {routeLibrary.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="bg-white border border-slate-200 rounded-xl shadow px-8 py-6 text-center max-w-sm">
            <FileText size={32} className="text-slate-300 mx-auto mb-2" />
            <div className="text-sm font-bold text-slate-600 mb-1">Route Library is Empty</div>
            <div className="text-[11px] text-slate-400">Routes you generate will be automatically saved here.</div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {routeLibrary.map((entry) => (
            <div key={entry.id} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="p-3 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-slate-800 flex items-center gap-2">
                    <Ship size={12} className="text-blue-500" /> {entry.vesselName}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">→ {entry.destination} · {entry.generatedAt}</div>
                </div>
                <span className="text-[9px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">{entry.routes.length} routes</span>
              </div>
              <div className="grid grid-cols-3 divide-x divide-slate-100">
                {entry.routes.map((r: any, ri: number) => {
                  const meta = routeMeta(r);
                  return (
                    <div key={ri} className="p-3 space-y-1.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <div className={cn('w-2 h-2 rounded-full', meta.dot)} />
                        <span className="text-[10px] font-bold text-slate-700">{meta.label}</span>
                      </div>
                      {[['Dist', (r.distance_nm || 0).toFixed(0) + ' nm'],['ETA', (r.eta_days || 0).toFixed(1) + ' d'],['Fuel', (r.fuel_mt || 0).toFixed(0) + ' MT'],['Risk', r.ice_risk || '—']].map(([l, v]) => (
                        <div key={l} className="flex justify-between text-[9px]">
                          <span className="text-slate-400">{l}</span><span className="font-medium text-slate-700">{v}</span>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">
      <div className="flex items-center gap-2 shrink-0">
        {(['plan', 'compare', 'library'] as const).map((t) => {
          const labels = { plan: 'Plan New Route', compare: 'Compare Routes', library: 'Route Library' };
          const active = activeTab === t;
          return (
            <button key={t} onClick={() => setActiveTab(t)}
              className={cn('px-4 py-1.5 text-xs font-bold rounded-md transition-colors',
                active ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>
              {labels[t]}
              {t === 'library' && routeLibrary.length > 0 && (
                <span className={cn('ml-1.5 text-[9px] px-1.5 py-0.5 rounded-full font-bold', active ? 'bg-white/30 text-white' : 'bg-blue-100 text-blue-700')}>
                  {routeLibrary.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {activeTab === 'plan' && (
        <div className="flex flex-1 gap-3 min-h-0">
          {planPanel}
          <div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">
            <SharedMap vessels={vessels} icebergs={icebergs} routes={displayRoutes} forecastGeoJSON={forecastGeoJSON}
              center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined} zoom={selectedVessel ? 4 : undefined} />
            {!generated && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-20">
                <div className="bg-white/90 border border-slate-200 rounded-xl shadow-lg px-6 py-4 text-center max-w-xs">
                  <Navigation size={28} className="text-blue-400 mx-auto mb-2" />
                  <div className="text-sm font-bold text-slate-700 mb-1">No Routes Generated</div>
                  <div className="text-[11px] text-slate-500">Select a vessel and destination, then click <span className="font-bold text-blue-600">Generate Routes</span></div>
                </div>
              </div>
            )}
            {isGenerating && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-20">
                <div className="bg-white/90 border border-slate-200 rounded-xl shadow-lg px-6 py-4 text-center">
                  <LoaderCircle size={28} className="text-blue-500 mx-auto mb-2 animate-spin" />
                  <div className="text-sm font-bold text-slate-700">Calculating optimal routes…</div>
                  <div className="text-[11px] text-slate-500 mt-1">{selectedVessel?.name} → {dest?.label}</div>
                </div>
              </div>
            )}
            {generated && displayRoutes.length > 0 && !isGenerating && (
              <>
                <div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-2.5 border border-slate-200 shadow text-[10px] space-y-1.5 w-36">
                  <div className="flex items-center gap-2"><div className="w-4 h-px bg-green-500 border-dashed border-b-2" /><span>Eco Route</span></div>
                  <div className="flex items-center gap-2"><div className="w-4 h-px bg-blue-500 border-dashed border-b-2" /><span>Safe Route</span></div>
                  <div className="flex items-center gap-2"><div className="w-4 h-px bg-red-500 border-dashed border-b-2" /><span>Fastest Route</span></div>
                </div>
                <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 bg-white/90 border border-green-300 text-[10px] font-bold text-green-700 px-2 py-1 rounded shadow">
                  {dest?.label?.split(',')[0]}
                </div>
                <button onClick={() => setActiveTab('compare')}
                  className="absolute bottom-3 right-3 z-10 bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-bold px-3 py-1.5 rounded-lg shadow flex items-center gap-1.5 transition-colors">
                  <BarChart2 size={11} /> Compare Routes
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === 'compare' && (
        <div className="flex flex-1 gap-3 min-h-0">
          {planPanel}
          <div className="flex-1 overflow-y-auto">{compareTab}</div>
        </div>
      )}

      {activeTab === 'library' && (
        <div className="flex flex-1 gap-3 min-h-0">
          {planPanel}
          <div className="flex-1 overflow-y-auto">{libraryTab}</div>
        </div>
      )}
    </div>
  );
}

  function OnshoreIceberg() {
  const { data: icebergs } = useIcebergs();
  const { data: stats } = useIcebergStats();
  const { data: forecastGeoJSON } = useSicForecast(0);
  
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap icebergs={icebergs} forecastGeoJSON={forecastGeoJSON}></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-1">Iceberg Size</div>}{[['All Icebergs', 'bg-slate-400'], ['Large (>1 km)', 'bg-red-500'], ['Medium (300m-1km)', 'bg-orange-400'], ['Small (<300m)', 'bg-yellow-400']].map(([l, c], i) => <div key={i} className="flex items-center gap-2">{<div className={cn('w-3 h-3 rounded-sm', c)}></div>}{<span>{l}</span>}</div>)}</div>}</div>}{<div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4 shrink-0">{<div className="flex items-center gap-3">{<div className="bg-slate-100 rounded-lg p-3 flex-1 text-center">{<div className="text-2xl font-black text-slate-800">{stats?.total || 0}</div>}{<div className="text-[9px] text-slate-500">Tracked Icebergs</div>}</div>}{<div className="bg-red-50 rounded-lg p-3 flex-1 text-center border border-red-200">{<div className="text-2xl font-black text-red-600">{stats?.new_24h || 0}</div>}{<div className="text-[9px] text-red-500">New (Last 24h)</div>}</div>}</div>}{<div className="bg-orange-50 rounded-lg p-3 border border-orange-200">{<div className="text-[9px] font-bold text-orange-700 mb-1">HIGH RISK (Near Routes)</div>}{<div className="text-2xl font-black text-orange-600">{stats?.high_risk || 0}</div>}</div>}{<div className="border-t border-slate-100 pt-3 space-y-2">{(icebergs || []).slice(0, 5).map((b: any, i: number) => <div key={i} className="flex items-center justify-between text-[10px] bg-slate-50 rounded p-2">{<span className="font-bold text-slate-700">{b.id}</span>}{<span className="text-slate-500">{b.size_cat}</span>}{<span className={cn('text-white px-2 py-0.5 rounded-full text-[9px] font-bold', b.risk === 'High' ? 'bg-red-500' : b.risk === 'Medium' ? 'bg-orange-400' : 'bg-green-500')}>{b.risk}</span>}</div>)}</div>}</div>}</div>;
}
function OnshoreAlerts() {
  const { data: initialAlerts } = useAlerts();
  const [filter, setFilter] = useState('All');
  
  // Use a local state to allow users to "Acknowledge" alerts without needing a backend endpoint
  const [alerts, setAlerts] = useState<any[]>([]);
  useEffect(() => {
    if (initialAlerts && alerts.length === 0) setAlerts(initialAlerts);
  }, [initialAlerts, alerts.length]);

  const filters = ['All', 'High Risk', 'Weather', 'Iceberg', 'Sea Ice'];
  const filteredAlerts = alerts.filter(a => {
    if (filter === 'All') return true;
    if (filter === 'High Risk') return a.severity === 'High';
    if (filter === 'Weather') return a.type === 'Weather';
    if (filter === 'Iceberg') return a.type === 'Iceberg';
    if (filter === 'Sea Ice') return a.type === 'Sea Ice';
    return true;
  });

  const getSeverityColor = (sev: string) => {
    if (sev === 'High') return 'text-red-600 bg-red-100 border-red-200';
    if (sev === 'Medium') return 'text-orange-600 bg-orange-100 border-orange-200';
    return 'text-blue-600 bg-blue-100 border-blue-200';
  };

  const getIcon = (type: string) => {
    if (type === 'Weather') return <Wind size={16} className="text-blue-500" />;
    if (type === 'Iceberg') return <MapIcon size={16} className="text-slate-500" />;
    if (type === 'Sea Ice') return <Layers size={16} className="text-cyan-500" />;
    return <AlertTriangle size={16} className="text-red-500" />;
  };

  return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-hidden">
    <div className="flex items-center justify-between shrink-0">
      <div className="text-lg font-black text-slate-800">Alerts & Notifications</div>
      <div className="flex items-center gap-2">
        {filters.map(f => (
          <button key={f} onClick={() => setFilter(f)} 
            className={cn('px-3 py-1.5 text-[10px] font-bold rounded-full transition-colors border', 
              filter === f ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50')}>
            {f}
          </button>
        ))}
      </div>
    </div>
    
    <div className="flex-1 overflow-y-auto bg-white border border-slate-200 shadow-sm rounded-xl p-4">
      {filteredAlerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-slate-400">
          <CheckCircle2 size={40} className="mb-3 opacity-20" />
          <div className="text-sm font-bold">No active alerts</div>
          <div className="text-xs">Your fleet is operating safely.</div>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredAlerts.map(alert => (
            <div key={alert.id} className={cn('p-4 rounded-lg border flex items-start gap-4 transition-all', alert.status === 'Acknowledged' ? 'opacity-60 bg-slate-50 border-slate-200' : 'bg-white shadow-sm border-slate-200')}>
              <div className="mt-1 bg-slate-100 p-2 rounded-lg">{getIcon(alert.type)}</div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-800">{alert.vessel}</span>
                    <span className="text-[10px] text-slate-400 font-medium">{alert.time_utc} UTC</span>
                    <span className={cn('text-[9px] font-bold px-2 py-0.5 rounded-full border', getSeverityColor(alert.severity))}>
                      {alert.severity} Risk
                    </span>
                  </div>
                  {alert.status !== 'Acknowledged' && (
                    <button onClick={() => setAlerts(alerts.map(a => a.id === alert.id ? { ...a, status: 'Acknowledged' } : a))} className="text-[10px] font-bold bg-white border border-slate-200 px-3 py-1.5 rounded text-slate-600 hover:bg-slate-50 transition-colors">
                      Acknowledge
                    </button>
                  )}
                  {alert.status === 'Acknowledged' && (
                    <span className="text-[10px] font-bold text-green-600 flex items-center gap-1">
                      <CheckCircle2 size={12} /> Acknowledged
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-700 font-medium mb-1">{alert.message}</div>
                <div className="text-[10px] text-slate-500 font-medium flex items-center gap-3">
                  <span className="flex items-center gap-1"><Navigation size={10} /> {alert.location}</span>
                  <span className="flex items-center gap-1"><AlertTriangle size={10} /> Type: {alert.type}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  </div>;
}

function OnshoreDataForecasts() {
  const [locIdx, setLocIdx] = useState(1); // Default to Bharati Station
  const dest = ROUTE_DESTINATIONS[locIdx];
  const { data: forecastData } = useWeatherForecast(dest.lat, dest.lon);
  
  const forecasts = forecastData?.forecasts || [];

  return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-hidden">
    <div className="flex items-center justify-between shrink-0">
      <div className="text-lg font-black text-slate-800">Data & 7-Day Forecasts</div>
      <div className="flex items-center gap-3">
        <span className="text-xs font-bold text-slate-600">Location:</span>
        <select value={locIdx} onChange={(e) => setLocIdx(Number(e.target.value))} className="text-xs border border-slate-300 rounded p-1.5 bg-white font-medium outline-none">
          {ROUTE_DESTINATIONS.map((d, i) => <option key={i} value={i}>{d.label}</option>)}
        </select>
      </div>
    </div>
    
    <div className="flex flex-1 gap-4 min-h-0">
      <div className="flex-[3] flex flex-col gap-4 overflow-y-auto">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col">
          <div className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><Thermometer size={16} className="text-orange-500"/> Temperature & Wind Forecast</div>
          <div className="flex-1 min-h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={forecasts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorTemp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{fontSize: 10}} tickFormatter={(val) => val.substring(5)} stroke="#94a3b8" />
                <YAxis tick={{fontSize: 10}} stroke="#94a3b8" />
                <RechartsTooltip contentStyle={{ fontSize: '11px', borderRadius: '8px' }} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Area type="monotone" dataKey="temperature_c" name="Temp (°C)" stroke="#f97316" fillOpacity={1} fill="url(#colorTemp)" />
                <Line type="monotone" dataKey="wind_speed_kn" name="Wind (knots)" stroke="#3b82f6" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col">
          <div className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><Layers size={16} className="text-cyan-500"/> Sea Ice Concentration (SIC) & Waves</div>
          <div className="flex-1 min-h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={forecasts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{fontSize: 10}} tickFormatter={(val) => val.substring(5)} stroke="#94a3b8" />
                <YAxis yAxisId="left" tick={{fontSize: 10}} stroke="#94a3b8" />
                <YAxis yAxisId="right" orientation="right" tick={{fontSize: 10}} stroke="#94a3b8" />
                <RechartsTooltip contentStyle={{ fontSize: '11px', borderRadius: '8px' }} />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Bar yAxisId="left" dataKey="sic_pct" name="SIC (%)" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="wave_height_m" name="Wave Height (m)" stroke="#10b981" strokeWidth={2} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="flex-[2] bg-white border border-slate-200 rounded-xl p-4 shadow-sm overflow-y-auto">
        <div className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><Clock size={16} className="text-slate-500"/> Daily Summary</div>
        <div className="space-y-3">
          {forecasts.map((f: any) => (
            <div key={f.day} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
              <div>
                <div className="text-xs font-bold text-slate-800">{f.date}</div>
                <div className="text-[10px] text-slate-500 font-medium mt-0.5">{f.visibility} Visibility</div>
              </div>
              <div className="flex gap-4">
                <div className="text-right">
                  <div className="text-[10px] text-slate-500">Temp</div>
                  <div className={cn("text-xs font-bold", f.temperature_c < -10 ? "text-blue-600" : "text-orange-600")}>{f.temperature_c}°C</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-slate-500">Wind</div>
                  <div className={cn("text-xs font-bold", f.wind_speed_kn > 30 ? "text-red-500" : "text-slate-700")}>{f.wind_speed_kn} kn</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-slate-500">SIC</div>
                  <div className="text-xs font-bold text-cyan-600">{f.sic_pct}%</div>
                </div>
              </div>
            </div>
          ))}
          {forecasts.length === 0 && <div className="text-center text-slate-400 text-xs py-10 flex flex-col items-center justify-center gap-2"><Loader2 size={24} className="animate-spin opacity-50" />Loading forecast data...</div>}
        </div>
      </div>
    </div>
  </div>;
}

function OnshoreReports() {
  const { data: vessels } = useVessels();
  const { data: alerts } = useAlerts();
  const { data: stats } = useDashboardOverview();

  const [reports, setReports] = useState([
    { id: 'REP-1042', type: 'Fleet Status Overview', date: '19 Sep 2026', format: 'PDF', status: 'Ready', author: 'System Auto' },
    { id: 'REP-1041', type: 'Ice & Weather Summary', date: '18 Sep 2026', format: 'PDF', status: 'Ready', author: 'System Auto' },
    { id: 'REP-1040', type: 'Environmental Compliance (CO2)', date: '15 Sep 2026', format: 'CSV', status: 'Ready', author: 'John Doe' },
    { id: 'REP-1039', type: 'Voyage Post-Analysis', date: '12 Sep 2026', format: 'PDF', status: 'Ready', author: 'Sarah Smith' },
  ]);
  
  const [generating, setGenerating] = useState(false);
  const [reportType, setReportType] = useState('Fleet Status Overview');
  const [format, setFormat] = useState('PDF');
  
  const handleGenerate = () => {
    setGenerating(true);
    setTimeout(() => {
      setReports([{
        id: `REP-${Math.floor(Math.random() * 1000) + 2000}`,
        type: reportType,
        date: new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }),
        format,
        status: 'Ready',
        author: 'You (Admin)'
      }, ...reports]);
      setGenerating(false);
    }, 1500);
  };

  const handleDownload = (r: any) => {
    const activeVessels = vessels?.length || 0;
    const activeAlerts = alerts?.length || 0;
    const trackedIcebergs = stats?.icebergs_tracked || 0;

    if (r.format === 'PDF') {
      const doc = new jsPDF();
      doc.setFontSize(22);
      doc.text("NCPOR OPERATIONAL REPORT", 20, 30);
      
      doc.setFontSize(12);
      doc.text(`Report ID: ${r.id}`, 20, 50);
      doc.text(`Report Type: ${r.type}`, 20, 60);
      doc.text(`Date Generated: ${r.date}`, 20, 70);
      doc.text(`Generated By: ${r.author}`, 20, 80);
      doc.text(`Status: ${r.status}`, 20, 90);
      
      doc.setFontSize(14);
      doc.text("Executive Summary", 20, 110);
      
      doc.setFontSize(11);
      doc.text(`Active Fleet: ${activeVessels} vessels currently monitored in the Southern Ocean.`, 20, 120);
      doc.text(`Icebergs Tracked: ${trackedIcebergs} icebergs monitored within operational bounds.`, 20, 128);
      doc.text(`Active Alerts: ${activeAlerts} high-priority navigational alerts active.`, 20, 136);

      let yPos = 156;

      if (r.type === 'Fleet Status Overview') {
        doc.setFontSize(14);
        doc.text("Vessel Status Breakdown", 20, yPos);
        yPos += 10;
        doc.setFontSize(10);
        (vessels || []).slice(0, 10).forEach((v: any) => {
          doc.text(`- ${v.name} (${v.type}) | Route: ${v.origin} to ${v.destination} | Spd: ${v.speed_knots}kn`, 20, yPos);
          yPos += 7;
        });
      } else if (r.type.includes('Ice') || r.type.includes('Alert')) {
        doc.setFontSize(14);
        doc.text("Recent Navigational Alerts", 20, yPos);
        yPos += 10;
        doc.setFontSize(10);
        if (activeAlerts === 0) {
          doc.text("No active alerts at this time.", 20, yPos);
        } else {
          (alerts || []).slice(0, 10).forEach((a: any) => {
            doc.text(`- [${a.severity}] ${a.type}: ${a.message} (Vessel: ${a.vessel})`, 20, yPos);
            yPos += 7;
          });
        }
      } else {
        doc.setFontSize(14);
        doc.text("Operational Metrics", 20, yPos);
        yPos += 10;
        doc.setFontSize(10);
        doc.text("Environmental compliance targets and CO2 emissions remain within nominal", 20, yPos);
        doc.text("operational thresholds for all active fleet deployments this quarter.", 20, yPos + 7);
      }
      
      doc.setFontSize(10);
      doc.text("--- End of Report ---", 20, 280);
      
      doc.save(`${r.id}_${r.type.replace(/\s+/g, '_')}.pdf`);
    } else if (r.format === 'CSV') {
      let csvContent = `Report ID,${r.id}\nType,${r.type}\nDate,${r.date}\nAuthor,${r.author}\nStatus,${r.status}\n\n`;
      
      csvContent += `Metric,Value\n`;
      csvContent += `Active Vessels,${activeVessels}\n`;
      csvContent += `Tracked Icebergs,${trackedIcebergs}\n`;
      csvContent += `Active Alerts,${activeAlerts}\n\n`;

      if (r.type === 'Fleet Status Overview' && vessels) {
        csvContent += `Vessel Name,Type,Origin,Destination,Speed(kn),Heading\n`;
        vessels.forEach((v: any) => {
          csvContent += `${v.name},${v.type},"${v.origin}","${v.destination}",${v.speed_knots},${v.heading}\n`;
        });
      } else if (alerts && alerts.length > 0) {
        csvContent += `Alert ID,Severity,Type,Vessel,Message,Time UTC\n`;
        alerts.forEach((a: any) => {
          csvContent += `${a.id},${a.severity},${a.type},${a.vessel},"${a.message}",${a.time_utc}\n`;
        });
      }
      
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${r.id}_${r.type.replace(/\s+/g, '_')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-hidden">
    <div className="text-lg font-black text-slate-800 shrink-0">Reports & Analytics</div>
    
    <div className="flex flex-1 gap-4 min-h-0">
      <div className="flex-1 bg-white border border-slate-200 rounded-xl p-4 shadow-sm overflow-y-auto">
        <div className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><FileText size={16} className="text-blue-500"/> Document Library</div>
        
        <div className="space-y-2">
          {reports.map(r => (
            <div key={r.id} className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition-colors">
              <div className="flex items-center gap-3">
                <div className={cn("w-8 h-8 rounded flex items-center justify-center font-bold text-[10px]", r.format === 'PDF' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600')}>
                  {r.format}
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-800">{r.type}</div>
                  <div className="text-[10px] text-slate-500">ID: {r.id} • {r.date} • {r.author}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-green-600 flex items-center gap-1 bg-green-50 px-2 py-0.5 rounded-full border border-green-200"><CheckCircle2 size={10}/> {r.status}</span>
                <button onClick={() => handleDownload(r)} className="text-slate-500 hover:text-blue-600 transition-colors bg-white border border-slate-200 p-1.5 rounded" title={`Download ${r.format}`}><Download size={14}/></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="w-80 bg-white border border-slate-200 rounded-xl p-4 shadow-sm shrink-0 h-fit space-y-4">
        <div className="text-sm font-bold text-slate-800 border-b border-slate-100 pb-2">Generate New Report</div>
        
        <div>
          <label className="text-[10px] font-bold text-slate-700 block mb-1">Report Type</label>
          <select value={reportType} onChange={e => setReportType(e.target.value)} className="w-full text-xs border border-slate-300 rounded p-2 bg-slate-50 outline-none">
            <option>Fleet Status Overview</option>
            <option>Ice & Weather Summary</option>
            <option>Environmental Compliance (CO2)</option>
            <option>Voyage Post-Analysis</option>
            <option>Incident & Alerts Log</option>
          </select>
        </div>

        <div>
          <label className="text-[10px] font-bold text-slate-700 block mb-1">Date Range</label>
          <select className="w-full text-xs border border-slate-300 rounded p-2 bg-slate-50 outline-none">
            <option>Last 7 Days</option>
            <option>Last 30 Days</option>
            <option>This Quarter</option>
            <option>Year to Date</option>
            <option>Custom Range...</option>
          </select>
        </div>

        <div>
          <label className="text-[10px] font-bold text-slate-700 block mb-1">Output Format</label>
          <div className="flex gap-2">
            <label className={cn("flex-1 text-center text-xs font-bold py-1.5 border rounded cursor-pointer transition-colors", format === 'PDF' ? 'bg-red-50 border-red-200 text-red-600' : 'bg-white border-slate-200 text-slate-500')}><input type="radio" className="hidden" checked={format === 'PDF'} onChange={() => setFormat('PDF')}/>PDF Document</label>
            <label className={cn("flex-1 text-center text-xs font-bold py-1.5 border rounded cursor-pointer transition-colors", format === 'CSV' ? 'bg-green-50 border-green-200 text-green-600' : 'bg-white border-slate-200 text-slate-500')}><input type="radio" className="hidden" checked={format === 'CSV'} onChange={() => setFormat('CSV')}/>CSV Data</label>
          </div>
        </div>

        <button onClick={handleGenerate} disabled={generating} className={cn("w-full py-2 text-xs font-bold rounded text-white flex items-center justify-center gap-2 transition-colors mt-2", generating ? "bg-slate-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700")}>
          {generating ? <><LoaderCircle size={14} className="animate-spin" /> Generating...</> : <><Plus size={14} /> Generate Report</>}
        </button>
      </div>
    </div>
  </div>;
}

function OnshoreCommandCenter({
  onSwitchToOnboard
}) {
  const [tab, setTab] = (0, useState)('overview');
  const menuItems = [{
    id: 'overview',
    icon: <Layers size={15}></Layers>,
    label: 'Operational Overview'
  }, {
    id: 'vessels',
    icon: <Crosshair size={15}></Crosshair>,
    label: 'Vessel Tracking'
  }, {
    id: 'ice-weather',
    icon: <Thermometer size={15}></Thermometer>,
    label: 'Ice & Weather Monitoring'
  }, {
    id: 'route',
    icon: <Navigation size={15}></Navigation>,
    label: 'Route Planning'
  }, {
    id: 'iceberg',
    icon: <MapIcon size={15}></MapIcon>,
    label: 'Iceberg Tracking'
  }, {
    id: 'alerts',
    icon: <Bell size={15}></Bell>,
    label: 'Alerts & Notifications',
    badge: 3
  }, {
    id: 'data',
    icon: <BarChart2 size={15}></BarChart2>,
    label: 'Data & Forecasts'
  }, {
    id: 'reports',
    icon: <FileText size={15}></FileText>,
    label: 'Reports'
  }];
  const content = {
    overview: <OnshoreOverview></OnshoreOverview>,
    vessels: <OnshoreVessels onSwitchToOnboard={onSwitchToOnboard}></OnshoreVessels>,
    'ice-weather': <OnshoreIceWeather></OnshoreIceWeather>,
    route: <OnshoreRoute></OnshoreRoute>,
    iceberg: <OnshoreIceberg></OnshoreIceberg>,
    alerts: <OnshoreAlerts></OnshoreAlerts>,
    data: <OnshoreDataForecasts></OnshoreDataForecasts>,
    reports: <OnshoreReports></OnshoreReports>,
    settings: <div className="p-4">Settings Coming Soon</div>
  };
  return <div className="flex flex-col h-full bg-slate-100 overflow-hidden">{<div className="h-12 bg-[#1e293b] text-white flex items-center justify-between px-4 shrink-0 shadow-md z-50">{<div className="flex items-center gap-6">{<div className="flex items-center gap-2">{<div className="w-7 h-7 bg-white rounded-full flex items-center justify-center text-[#1e293b] font-black text-sm">N</div>}{<div>{<div className="font-bold text-sm leading-tight">NCPOR</div>}{<div className="text-[8px] text-slate-400 leading-none">National Centre for Polar and Ocean Research · Ministry of Earth Sciences</div>}</div>}</div>}{<div className="h-5 w-px bg-slate-600"></div>}</div>}{<div className="flex items-center gap-3">{<button onClick={onSwitchToOnboard} className="text-[10px] font-bold flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded-full transition-colors">{<Ship size={11}></Ship>}Switch to Onboard</button>}{<div className="relative">{<Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"></Search>}{<input className="bg-[#334155] text-[11px] text-white pl-8 pr-3 py-1.5 rounded w-56 border border-slate-600 focus:outline-none" placeholder="Search vessel, location..."></input>}</div>}{<div className="relative cursor-pointer">{<Bell size={16} className="text-slate-300"></Bell>}{<div className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-red-500 rounded-full flex items-center justify-center text-[8px] text-white font-bold">3</div>}</div>}{<div className="w-7 h-7 bg-slate-600 rounded-full flex items-center justify-center cursor-pointer">{<User size={14}></User>}</div>}</div>}</div>}{<div className="flex flex-1 overflow-hidden">{<div className="w-52 bg-white border-r border-slate-200 flex flex-col shadow-sm z-40 shrink-0">{<div className="px-4 py-3 border-b border-slate-100 text-xs font-bold text-slate-800">Onshore Command Center</div>}{<div className="flex-1 py-2 overflow-y-auto">{menuItems.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={cn('w-full flex items-center justify-between px-4 py-2.5 text-[11px] font-medium transition-colors', tab === item.id ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900')}>{<div className="flex items-center gap-2.5">{item.icon}{<span>{item.label}</span>}</div>}{item.badge && <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">{item.badge}</span>}</button>)}</div>}{<div className="p-3 border-t border-slate-200">{<button onClick={() => setTab('settings')} className={cn('w-full flex items-center gap-2.5 px-4 py-2 text-[11px] font-medium rounded-md', tab === 'settings' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50')}>{<Settings size={15}></Settings>}{<span>Settings</span>}</button>}</div>}</div>}{<div className="flex-1 overflow-hidden">{content[tab] || content['overview']}</div>}</div>}</div>;
}
function OnboardNavigation({ vessel }: { vessel: any }) {
  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const [selectedRouteKind, setSelectedRouteKind] = useState<string | null>(null);
  
  const myVessel = vessel;

  // Determine the correct destination from the vessel's metadata
  const destName = myVessel?.destination || 'Maitri Station, Antarctica';
  const dest = ROUTE_DESTINATIONS.find(item => destName.includes(item.label.split(',')[0])) || ROUTE_DESTINATIONS[0];

  const { routes } = useGenerateRoutes(
    myVessel?.lat || 0,
    myVessel?.lon || 0,
    dest.lat,
    dest.lon,
    !!myVessel
  );

  // Filter routes based on selection; show all when none selected
  const displayedRoutes = selectedRouteKind
    ? routes.filter((r: any) => (r.routeKind || r.type) === selectedRouteKind)
    : routes;

  const routeOptions = [
    { kind: 'eco',  label: 'Eco Route', sub: 'Lowest fuel consumption', days: routes.find((r:any) => (r.routeKind||r.type)==='eco')?.eta_days?.toFixed(1) || '7.5', fuel: routes.find((r:any) => (r.routeKind||r.type)==='eco')?.fuel_mt?.toFixed(0) || '320', risk: 'Moderate ice', riskColor: 'text-yellow-600', borderColor: 'border-green-400', bg: 'bg-green-50', dotColor: 'bg-green-500', textColor: 'text-green-700' },
    { kind: 'safe', label: 'Safest Route', sub: 'Avoids high ice', days: routes.find((r:any) => (r.routeKind||r.type)==='safe')?.eta_days?.toFixed(1) || '8.2', fuel: routes.find((r:any) => (r.routeKind||r.type)==='safe')?.fuel_mt?.toFixed(0) || '340', risk: 'Low risk', riskColor: 'text-green-600', borderColor: 'border-blue-400', bg: 'bg-slate-50', dotColor: 'bg-blue-500', textColor: 'text-blue-700' },
    { kind: 'fast', label: 'Fastest Route', sub: 'Min travel time', days: routes.find((r:any) => (r.routeKind||r.type)==='fast')?.eta_days?.toFixed(1) || '5.9', fuel: routes.find((r:any) => (r.routeKind||r.type)==='fast')?.fuel_mt?.toFixed(0) || '400', risk: 'Higher risk', riskColor: 'text-red-600', borderColor: 'border-red-400', bg: 'bg-slate-50', dotColor: 'bg-red-500', textColor: 'text-red-700' },
  ];

  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="w-56 bg-white rounded-lg border border-slate-200 p-4 shrink-0 space-y-4 overflow-y-auto">{<div className="text-xs font-bold text-slate-800 border-b border-slate-100 pb-2">Vessel Information</div>}{<div className="flex items-center gap-3">{<div className="w-14 h-12 bg-slate-100 border border-slate-200 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-400"></Ship>}</div>}{<div>{<div className="text-sm font-bold text-slate-900">{myVessel?.name || 'Vessel'}</div>}{<div className="text-[10px] text-slate-500">{myVessel?.type || 'Ship'}</div>}</div>}</div>}{<div className="grid grid-cols-2 gap-1.5 text-[9px]">{[['IMO:', myVessel?.imo || '9684012'], ['Call Sign:', myVessel?.call_sign || 'VUAA'], ['MMSI:', myVessel?.mmsi || '419001234'], ['Ice Class:', myVessel?.ice_class || 'PC5'], ['Length:', (myVessel?.length_m || 104) + ' m'], ['Beam:', (myVessel?.beam_m || 18.0) + ' m'], ['Draft:', (myVessel?.draft_m || 6.2) + ' m'], ['Status:', myVessel?.status || 'Underway']].map(([l, v], i) => <React.Fragment key={i}>{<span className="text-slate-500">{l}</span>}{<span className={cn('font-medium', l === 'Status:' ? 'text-green-600' : 'text-slate-700')}>{v}</span>}</React.Fragment>)}</div>}{<div className="border-t border-slate-100 pt-3">{<div className="text-xs font-bold text-slate-800 mb-3">Current Position</div>}{<div className="space-y-1.5 text-[10px]">{<div className="text-slate-800 font-bold">Lat: {myVessel?.lat?.toFixed(3) || 0}&deg; / Lon: {myVessel?.lon?.toFixed(3) || 0}&deg;</div>}{[['Speed:', (myVessel?.speed_kn || 0) + ' kn'], ['Heading:', (myVessel?.heading_deg || 0) + '°']].map(([l, v], i) => <div key={i} className="flex gap-3">{<span className="text-slate-500 w-14">{l}</span>}{<span className="text-slate-800 font-bold">{v}</span>}</div>)}{<div className="mt-2 pt-2 border-t border-slate-100 space-y-1">{<div className="text-[9px] text-slate-500">Next Waypoint:</div>}{<div className="text-blue-600 font-bold text-xs">{myVessel?.next_waypoint || 'WP-12'}</div>}{<div className="text-[9px] text-slate-500">ETA: {myVessel?.eta_next || '14 Sep 2026, 06:20 UTC'}</div>}{<div className="text-[9px] text-slate-500">Distance: {myVessel?.distance_to_next_nm || 420} nm</div>}</div>}</div>}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-200 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} routes={displayedRoutes} forecastGeoJSON={forecastGeoJSON} center={myVessel ? [myVessel.lon, myVessel.lat] : undefined} zoom={4}></SharedMap>}{selectedRouteKind && <div className="absolute top-3 left-3 z-10 bg-white/95 text-[10px] text-slate-800 px-3 py-1.5 rounded-lg border border-slate-200 shadow-sm flex items-center gap-2 font-medium">{<span>Showing: {routeOptions.find(r => r.kind === selectedRouteKind)?.label}</span>}{<button onClick={() => setSelectedRouteKind(null)} className="ml-1 text-slate-400 hover:text-red-500 font-bold">✕</button>}</div>}</div>}{<div className="w-72 bg-white rounded-lg border border-slate-200 p-4 shrink-0 space-y-3 overflow-y-auto">{<div className="text-xs font-bold text-slate-800">Route Options (to {dest.label.split(',')[0]})</div>}{<div className="text-[10px] text-slate-500">Select a route to highlight it on the map:</div>}{routeOptions.map((r) => <div key={r.kind} onClick={() => setSelectedRouteKind(selectedRouteKind === r.kind ? null : r.kind)} className={cn('border-2 rounded-lg p-3 space-y-2 cursor-pointer transition-all', selectedRouteKind === r.kind ? r.borderColor + ' shadow-md' : 'border-slate-200 hover:border-slate-300', r.bg)}>{<div className="flex items-center gap-2 font-bold text-xs">{<span className={cn('w-2 h-2 rounded-full', r.dotColor)}></span>}{<span className={r.textColor}>{r.label}</span>}{selectedRouteKind === r.kind && <span className="ml-auto text-[9px] bg-blue-600 text-white px-1.5 py-0.5 rounded-full">Active</span>}</div>}{<div className="text-[9px] text-slate-500">{r.sub}</div>}{<div className="flex justify-between text-[10px] text-slate-800 font-bold">{<span>~ {r.days} days</span>}{<span>{r.fuel} MT fuel</span>}</div>}{<div className={cn('text-[9px]', r.riskColor)}>{r.risk}</div>}{<button onClick={e => { e.stopPropagation(); setSelectedRouteKind(selectedRouteKind === r.kind ? null : r.kind); }} className={cn('w-full text-[10px] font-bold py-1.5 rounded transition-colors', selectedRouteKind === r.kind ? 'bg-blue-700 text-white' : 'bg-blue-600 hover:bg-blue-700 text-white')}>{selectedRouteKind === r.kind ? '✓ Selected' : 'Select'}</button>}</div>)}</div>}</div>;
}
  function OnboardPanel({
  onSwitchToOnshore,
  activeVesselId
}: {
  onSwitchToOnshore: () => void,
  activeVesselId?: string
}) {
  const [tab, setTab] = useState('nav');
  const { data: vessels } = useVessels();
  const [localVesselId, setLocalVesselId] = useState(activeVesselId);
  
  useEffect(() => {
    if (activeVesselId) setLocalVesselId(activeVesselId);
  }, [activeVesselId]);

  const currentVessel = (vessels || []).find((v: any) => v.id === localVesselId) || (vessels || [])[0];

  const menuItems = [{
    id: 'nav',
    icon: <Crosshair size={14}></Crosshair>,
    label: 'Navigation'
  }, {
    id: 'waypoints',
    icon: <Navigation size={14}></Navigation>,
    label: 'Route & Waypoints'
  }, {
    id: 'weather',
    icon: <Thermometer size={14}></Thermometer>,
    label: 'Weather & Ice'
  }, {
    id: 'vessel-status',
    icon: <Activity size={14}></Activity>,
    label: 'Vessel Status'
  }, {
    id: 'alerts',
    icon: <Bell size={14}></Bell>,
    label: 'Alerts',
    badge: 2
  }, {
    id: 'comms',
    icon: <MessageSquare size={14}></MessageSquare>,
    label: 'Communications'
  }, {
    id: 'logs',
    icon: <BookOpen size={14}></BookOpen>,
    label: 'Logs'
  }];
  const destName = currentVessel?.destination || 'Maitri Station, Antarctica';
  const dest = ROUTE_DESTINATIONS.find((item: any) => destName.includes(item.label.split(',')[0])) || ROUTE_DESTINATIONS[0];
  const { routes: onboardRoutes } = useGenerateRoutes(currentVessel?.lat || 0, currentVessel?.lon || 0, dest.lat, dest.lon, !!currentVessel);
  const { data: allAlerts } = useAlerts();
  const vesselAlerts = (allAlerts || []).filter((a: any) => a.vessel === currentVessel?.name);
  const { data: weatherData } = useWeatherForecast(currentVessel?.lat || -69.4, currentVessel?.lon || 76.183);
  const forecasts = weatherData?.forecasts || [];

  const OnboardWaypoints = () => {
    const ecoRoute = onboardRoutes.find((r: any) => (r.routeKind || r.type) === 'eco') || onboardRoutes[0];
    const wps = ecoRoute?.waypoints?.slice(0, 8) || [];
    return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-y-auto">
      <div className="text-sm font-black text-slate-800">Route & Waypoints</div>
      <div className="grid grid-cols-3 gap-3">
        {[{ label: 'Destination', val: dest.label.split(',')[0], icon: <Navigation size={16} className="text-blue-500"/> },
          { label: 'ETA', val: ecoRoute ? `${ecoRoute.eta_days?.toFixed(1)} days` : '—', icon: <Activity size={16} className="text-green-500"/> },
          { label: 'Distance', val: ecoRoute ? `${ecoRoute.distance_nm?.toFixed(0)} nm` : '—', icon: <Crosshair size={16} className="text-purple-500"/> }
        ].map((k, i) => <div key={i} className="bg-white rounded-lg border border-slate-200 p-3 flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-500">{k.icon}{k.label}</div>
          <div className="text-sm font-bold text-slate-800">{k.val}</div>
        </div>)}
      </div>
      <div className="bg-white rounded-xl border border-slate-200 p-4 flex-1">
        <div className="text-xs font-bold text-slate-800 mb-3 flex items-center gap-2"><Navigation size={14} className="text-blue-500"/>Planned Waypoints (Eco Route)</div>
        {wps.length === 0 ? <div className="text-slate-400 text-xs">Generating route...</div> :
        <div className="space-y-2">
          {wps.map((wp: any, i: number) => <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 border border-slate-100">
            <div className={cn('w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0', i === 0 ? 'bg-green-500' : i === wps.length - 1 ? 'bg-red-500' : 'bg-blue-500')}>{i + 1}</div>
            <div className="flex-1 text-[10px]">
              <div className="font-bold text-slate-800">WP-{String(i + 1).padStart(2, '0')}</div>
              <div className="text-slate-500">Lat: {wp.lat?.toFixed(3)}° / Lon: {wp.lon?.toFixed(3)}°</div>
            </div>
            <div className="text-right text-[9px] text-slate-500">
              <div>SIC: {(wp.sic * 100).toFixed(0)}%</div>
              <div>Wind: {wp.wind_kn?.toFixed(0)} kn</div>
            </div>
          </div>)}
        </div>}
      </div>
    </div>;
  };

  const OnboardWeather = () => {
    const wx = currentVessel?.weather_at_position || {};
    return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-y-auto">
      <div className="text-sm font-black text-slate-800">Weather & Ice</div>
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: 'Wind Speed', val: wx.wind_speed_ms ? `${(wx.wind_speed_ms * 1.944).toFixed(1)} kn` : '—', icon: <CloudRain size={16} className="text-blue-500"/>, bg: 'bg-blue-50' },
          { label: 'Temperature', val: wx.temperature_c !== undefined ? `${wx.temperature_c?.toFixed(1)}°C` : '—', icon: <Thermometer size={16} className="text-orange-500"/>, bg: 'bg-orange-50' },
          { label: 'Wave Height', val: wx.wave_height_m ? `${wx.wave_height_m?.toFixed(1)} m` : '—', icon: <Activity size={16} className="text-teal-500"/>, bg: 'bg-teal-50' },
          { label: 'Sea Ice (SIC)', val: wx.sic_fraction !== undefined ? `${(wx.sic_fraction * 100).toFixed(0)}%` : '—', icon: <CloudSnow size={16} className="text-indigo-500"/>, bg: 'bg-indigo-50' },
        ].map((k, i) => <div key={i} className={cn('rounded-lg border border-slate-200 p-3 flex items-center gap-3', k.bg)}>
          <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center shadow-sm shrink-0">{k.icon}</div>
          <div><div className="text-[10px] text-slate-500">{k.label}</div><div className="text-lg font-black text-slate-800">{k.val}</div></div>
        </div>)}
      </div>
      <div className="bg-white rounded-xl border border-slate-200 p-4 flex-1">
        <div className="text-xs font-bold text-slate-800 mb-3">7-Day Forecast</div>
        {forecasts.length === 0 ? <div className="text-slate-400 text-xs">Loading forecast...</div> :
        <div className="space-y-2">
          {forecasts.map((f: any, i: number) => <div key={i} className="grid grid-cols-5 gap-2 items-center p-2 rounded-lg bg-slate-50 border border-slate-100 text-[10px]">
            <div className="font-bold text-slate-700">{f.date}</div>
            <div className="text-center"><div className="text-slate-500">Temp</div><div className="font-bold text-orange-600">{f.temperature_c?.toFixed(1)}°C</div></div>
            <div className="text-center"><div className="text-slate-500">Wind</div><div className="font-bold text-blue-600">{f.wind_speed_kn?.toFixed(0)} kn</div></div>
            <div className="text-center"><div className="text-slate-500">Wave</div><div className="font-bold text-teal-600">{f.wave_height_m?.toFixed(1)} m</div></div>
            <div className="text-center"><div className="text-slate-500">SIC</div><div className="font-bold text-indigo-600">{f.sic_pct?.toFixed(0)}%</div></div>
          </div>)}
        </div>}
      </div>
    </div>;
  };

  const OnboardVesselStatus = () => {
    const v = currentVessel || {};
    const stats = [
      { label: 'Vessel Name', val: v.name || '—' },
      { label: 'Type', val: v.type || '—' },
      { label: 'IMO', val: v.imo || '9684012' },
      { label: 'Status', val: v.status || 'Underway' },
      { label: 'Origin', val: v.origin || '—' },
      { label: 'Destination', val: v.destination || dest.label },
      { label: 'Speed', val: `${v.speed_knots || 0} kn` },
      { label: 'Heading', val: `${v.heading || 0}°` },
      { label: 'Latitude', val: `${v.lat?.toFixed(4) || 0}°` },
      { label: 'Longitude', val: `${v.lon?.toFixed(4) || 0}°` },
    ];
    const systems = [
      { name: 'Main Engine', status: 'Nominal', pct: 94, color: 'bg-green-500' },
      { name: 'Navigation', status: 'Active', pct: 100, color: 'bg-blue-500' },
      { name: 'VSAT Comms', status: 'Online', pct: 87, color: 'bg-green-500' },
      { name: 'Ice Sonar', status: 'Active', pct: 100, color: 'bg-blue-500' },
      { name: 'Fuel', status: `${(onboardRoutes[0]?.fuel_mt || 320).toFixed(0)} MT rem`, pct: 72, color: 'bg-yellow-500' },
      { name: 'Ballast', status: 'Nominal', pct: 55, color: 'bg-slate-400' },
    ];
    return <div className="flex h-full p-4 gap-4 bg-slate-100 overflow-hidden">
      <div className="flex flex-col gap-4 w-56 shrink-0">
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <div className="text-xs font-bold text-slate-800 mb-3 flex items-center gap-2"><Ship size={14} className="text-blue-500"/>Vessel Details</div>
          <div className="space-y-2">
            {stats.map((s, i) => <div key={i} className="flex justify-between text-[10px]"><span className="text-slate-500">{s.label}</span><span className="font-bold text-slate-800 text-right max-w-[100px] truncate">{s.val}</span></div>)}
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="bg-white rounded-xl border border-slate-200 p-4 h-full">
          <div className="text-xs font-bold text-slate-800 mb-3 flex items-center gap-2"><Activity size={14} className="text-green-500"/>Systems Status</div>
          <div className="space-y-4">
            {systems.map((s, i) => <div key={i}>
              <div className="flex justify-between text-[10px] mb-1"><span className="font-bold text-slate-700">{s.name}</span><span className="text-slate-500">{s.status}</span></div>
              <div className="w-full bg-slate-100 rounded-full h-2"><div className={cn('h-2 rounded-full', s.color)} style={{width: `${s.pct}%`}}></div></div>
            </div>)}
          </div>
        </div>
      </div>
    </div>;
  };

  const OnboardAlertsPanel = () => {
    const [ack, setAck] = useState<string[]>([]);
    return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100 overflow-hidden">
      <div className="flex items-center justify-between shrink-0">
        <div className="text-sm font-black text-slate-800">Alerts for {currentVessel?.name || 'Vessel'}</div>
        <span className={cn('text-[10px] font-bold px-2 py-0.5 rounded-full', vesselAlerts.length > 0 ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600')}>{vesselAlerts.length} active</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-2">
        {vesselAlerts.length === 0 ? <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2"><Bell size={32} className="opacity-20"/><div className="text-sm">No alerts for this vessel</div></div> :
        vesselAlerts.map((a: any) => <div key={a.id} className={cn('bg-white rounded-lg border p-3 flex items-start gap-3', ack.includes(a.id) ? 'opacity-50 border-slate-200' : a.severity === 'High' ? 'border-red-300' : 'border-yellow-300')}>
          <div className={cn('w-2 h-2 rounded-full mt-1 shrink-0', a.severity === 'High' ? 'bg-red-500' : 'bg-yellow-500')}></div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded', a.severity === 'High' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700')}>{a.severity}</span>
              <span className="text-[10px] font-bold text-slate-800">{a.type}</span>
            </div>
            <div className="text-[10px] text-slate-600 mt-1">{a.message}</div>
            <div className="text-[9px] text-slate-400 mt-1">{a.time_utc} UTC • {a.location}</div>
          </div>
          {!ack.includes(a.id) && <button onClick={() => setAck(p => [...p, a.id])} className="text-[9px] bg-slate-100 hover:bg-slate-200 text-slate-600 px-2 py-1 rounded shrink-0">Ack</button>}
        </div>)}
      </div>
    </div>;
  };

  const OnboardComms = () => {
    const [msg, setMsg] = useState('');
    const [messages, setMessages] = useState([
      { from: 'NCPOR Shore', text: 'Weather window confirmed for next 48h. Proceed as planned.', time: '08:14', dir: 'in' },
      { from: 'You', text: 'Understood. Speed maintained at 12 kn. ETA unchanged.', time: '08:17', dir: 'out' },
      { from: 'Maitri Station', text: 'Supply berth ready. Confirm ETA at -70.766°S.', time: '09:32', dir: 'in' },
      { from: 'Fleet Coord', text: 'Ice alert issued for sector B-7. Recommend heading adjustment +5°.', time: '10:05', dir: 'in' },
    ]);
    return <div className="flex flex-col h-full p-4 gap-3 bg-slate-100">
      <div className="text-sm font-black text-slate-800 shrink-0">Communications</div>
      <div className="bg-white rounded-xl border border-slate-200 flex-1 flex flex-col overflow-hidden">
        <div className="p-3 border-b border-slate-100 flex items-center gap-2 shrink-0">
          <div className="w-2 h-2 bg-green-400 rounded-full"></div>
          <span className="text-[11px] font-bold text-slate-700">VSAT Channel — NCPOR Network</span>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {messages.map((m, i) => <div key={i} className={cn('flex', m.dir === 'out' ? 'justify-end' : 'justify-start')}>
            <div className={cn('max-w-[75%] px-3 py-2 rounded-xl text-[10px]', m.dir === 'out' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-800')}>
              <div className={cn('font-bold text-[9px] mb-0.5', m.dir === 'out' ? 'text-blue-200' : 'text-slate-500')}>{m.from} · {m.time}</div>
              {m.text}
            </div>
          </div>)}
        </div>
        <div className="p-3 border-t border-slate-100 flex gap-2 shrink-0">
          <input value={msg} onChange={e => setMsg(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && msg.trim()) { setMessages(p => [...p, { from: 'You', text: msg, time: new Date().toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit'}), dir: 'out' }]); setMsg(''); }}} className="flex-1 text-[11px] px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-blue-400" placeholder="Type a message..."/>
          <button onClick={() => { if(msg.trim()) { setMessages(p => [...p, { from: 'You', text: msg, time: new Date().toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit'}), dir: 'out' }]); setMsg(''); }}} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-bold rounded-lg">Send</button>
        </div>
      </div>
    </div>;
  };

  const OnboardLogs = () => {
    const events = [
      { time: '06:00', type: 'Position', msg: `Position updated: ${currentVessel?.lat?.toFixed(3)}°S / ${currentVessel?.lon?.toFixed(3)}°E`, severity: 'info' },
      { time: '06:30', type: 'Weather', msg: `Wind: ${currentVessel?.weather_at_position?.wind_speed_ms ? (currentVessel.weather_at_position.wind_speed_ms * 1.944).toFixed(1) : '—'} kn, Temp: ${currentVessel?.weather_at_position?.temperature_c?.toFixed(1) || '—'}°C`, severity: 'info' },
      { time: '07:15', type: 'Alert', msg: 'Iceberg detected within 50nm — heading adjusted +3°', severity: 'warn' },
      { time: '08:00', type: 'Comms', msg: 'NCPOR shore command check-in completed', severity: 'info' },
      { time: '08:45', type: 'Route', msg: `Waypoint WP-04 passed. Next: WP-05 (${dest.label.split(',')[0]})`, severity: 'info' },
      { time: '09:30', type: 'Engine', msg: 'Engine check completed. All systems nominal.', severity: 'info' },
      { time: '10:05', type: 'Alert', msg: 'Fleet coordination message received — ice sector B-7', severity: 'warn' },
      { time: '10:45', type: 'Position', msg: 'Daily position report transmitted to NCPOR HQ', severity: 'info' },
    ];
    return <div className="flex flex-col h-full p-4 gap-4 bg-slate-100">
      <div className="text-sm font-black text-slate-800 shrink-0">Voyage Logs — {currentVessel?.name}</div>
      <div className="bg-white rounded-xl border border-slate-200 flex-1 overflow-y-auto">
        <div className="divide-y divide-slate-100">
          {events.map((e, i) => <div key={i} className="flex items-start gap-3 p-3 hover:bg-slate-50">
            <div className="text-[9px] text-slate-400 font-mono w-10 shrink-0 mt-0.5">{e.time}</div>
            <div className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0', e.severity === 'warn' ? 'bg-yellow-100 text-yellow-700' : 'bg-blue-50 text-blue-600')}>{e.type}</div>
            <div className="text-[10px] text-slate-700">{e.msg}</div>
          </div>)}
        </div>
      </div>
    </div>;
  };


  const content = {
    nav: <OnboardNavigation vessel={currentVessel}></OnboardNavigation>,
    waypoints: <OnboardWaypoints/>,
    weather: <OnboardWeather/>,
    'vessel-status': <OnboardVesselStatus/>,
    alerts: <OnboardAlertsPanel/>,
    comms: <OnboardComms/>,
    logs: <OnboardLogs/>,
  };
  return <div className="flex flex-col h-full bg-slate-100 overflow-hidden">{<div className="h-12 bg-[#1e293b] text-white flex items-center justify-between px-4 shrink-0 shadow-md z-50">{<div className="flex items-center gap-6">{<div className="flex items-center gap-2">{<Ship size={18} className="text-blue-300"></Ship>}{<div>{<div className="font-bold text-sm leading-tight">SHIP (ONBOARD) PANEL</div>}</div>}</div>}{<div className="h-4 w-px bg-slate-600"></div>}{<select className="bg-transparent text-slate-300 text-xs font-bold outline-none cursor-pointer border-none" value={currentVessel?.id || ''} onChange={e => setLocalVesselId(e.target.value)}>{(vessels || []).map((v: any) => <option key={v.id} value={v.id} className="text-slate-800">{v.name}</option>)}</select>}{<div className="flex items-center gap-1.5 text-[10px]">{<div className="w-2 h-2 bg-green-400 rounded-full shadow-[0_0_4px_#4ade80]"></div>}{<span className="text-green-300 font-medium">Online</span>}</div>}{<div className="flex gap-5 text-[11px] text-slate-400">{['Navigate Safely', 'Stay Informed', 'Report'].map((t, i) => <React.Fragment key={i}>{<span className="cursor-pointer hover:text-white">{t}</span>}{i < 2 && <span>•</span>}</React.Fragment>)}</div>}</div>}{<div className="flex items-center gap-5 text-[11px] text-slate-300">{<span>12 Sep 2026 | 10:45 UTC</span>}{<div className="flex items-center gap-1">{<div className="w-2 h-2 bg-green-500 rounded-full"></div>}{<span className="text-[10px]">VSAT</span>}</div>}{<button onClick={onSwitchToOnshore} className="text-[10px] font-bold flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded-full transition-colors">{<MonitorSmartphone size={11}></MonitorSmartphone>}Switch to Onshore</button>}{<div className="w-7 h-7 bg-white/10 rounded-full flex items-center justify-center cursor-pointer">{<User size={14}></User>}</div>}</div>}</div>}{<div className="flex flex-1 overflow-hidden">{<div className="w-44 bg-white border-r border-slate-200 flex flex-col shrink-0 z-40">{<div className="flex-1 py-4 space-y-0.5">{menuItems.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={cn('w-full flex items-center justify-between px-4 py-3 text-[11px] font-medium transition-colors', tab === item.id ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900')}>{<div className="flex items-center gap-2.5">{item.icon}{<span>{item.label}</span>}</div>}{item.badge && <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">{item.badge}</span>}</button>)}</div>}</div>}{<div className="flex-1 overflow-hidden">{content[tab as keyof typeof content] || content['nav']}</div>}</div>}</div>;
}
export default function Dashboard() {
  const [view, setView] = useState<{type: string, vesselId?: string}>({ type: 'onshore' });
  return <div className="h-screen w-full bg-slate-900 overflow-hidden font-sans">
    {view.type === 'onshore' 
      ? <OnshoreCommandCenter onSwitchToOnboard={(vId?: string) => setView({ type: 'onboard', vesselId: vId })}></OnshoreCommandCenter> 
      : <OnboardPanel activeVesselId={view.vesselId} onSwitchToOnshore={() => setView({ type: 'onshore' })}></OnboardPanel>
    }
  </div>;
}
