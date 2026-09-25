import re

with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. OnshoreOverview
ov_repl = '''function OnshoreOverview() {
  const { data: stats } = useDashboardOverview();
  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: routes } = useGenerateRoutes(0,0,0,0,false);
  const { data: forecastGeoJSON } = useSicForecast(0);
  const { data: alerts } = useAlerts();

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
}'''

start_ov = code.find('function OnshoreOverview() {')
end_ov = code.find('function OnshoreVessels() {')
code = code[:start_ov] + ov_repl + '\n  ' + code[end_ov:]

# 2. OnshoreVessels
ovs_repl = '''function OnshoreVessels() {
  const [selected, setSelected] = useState(0);
  const { data: vesselsData } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const vessels = vesselsData || [];
  const selectedVessel = vessels[selected];
  
  // Try to generate routes for the selected vessel
  const { data: routes } = useGenerateRoutes(
    selectedVessel?.lat || 0,
    selectedVessel?.lon || 0,
    ROUTE_DESTINATIONS[0].lat,
    ROUTE_DESTINATIONS[0].lon,
    !!selectedVessel
  );

  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="w-72 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col shrink-0">{<div className="p-3 border-b border-slate-100 flex items-center justify-between">{<span className="text-xs font-bold text-slate-800">Vessels ({vessels.length})</span>}</div>}{<div className="p-2 border-b border-slate-100">{<div className="relative">{<Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"></Search>}{<input className="w-full text-[11px] pl-7 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded" placeholder="Search vessel..."></input>}</div>}</div>}{<div className="flex-1 overflow-y-auto">{vessels.map((v: any, i: number) => <div key={i} onClick={() => setSelected(i)} className={cn('p-3 border-b border-slate-100 cursor-pointer flex items-center gap-3 hover:bg-slate-50', selected === i && 'bg-blue-50 border-l-4 border-blue-500')}>{<div className="w-14 h-12 bg-slate-200 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-400"></Ship>}</div>}{<div className="min-w-0">{<div className="flex items-center gap-1">{<div className={cn('w-1.5 h-1.5 rounded-full shrink-0', v.color || 'bg-blue-500')}></div>}{<span className="text-xs font-bold text-slate-800 truncate">{v.name}</span>}</div>}{<div className="text-[9px] text-slate-500">{v.type || 'Vessel'}</div>}{<div className="text-[9px] text-slate-600 mt-0.5">Lat: {v.lat?.toFixed(3)} Lon: {v.lon?.toFixed(3)}</div>}{<div className="text-[9px] text-slate-600">Speed: {v.speed_knots} kn Heading: {v.heading}&deg;</div>}</div>}</div>)}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} forecastGeoJSON={forecastGeoJSON} routes={routes} center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined} zoom={selectedVessel ? 5 : undefined}></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-2">Legend</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Planned Route (Fast)</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Alternative Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-3 h-3 border border-blue-500 rounded-full"></div>}{<span>Fast Track</span>}</div>}</div>}</div>}</div>;
}'''

start_ovs = code.find('function OnshoreVessels() {')
end_ovs = code.find('function OnshoreIceWeather() {')
code = code[:start_ovs] + ovs_repl + '\n  ' + code[end_ovs:]

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated OnshoreOverview and OnshoreVessels")
