import re

with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    code = f.read()

# 3. OnshoreRoute
or_repl = '''function OnshoreRoute() {
  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  const [selectedVesselIdx, setSelectedVesselIdx] = useState(0);
  const [destIdx, setDestIdx] = useState(0);
  
  const selectedVessel = (vessels || [])[selectedVesselIdx];
  const dest = ROUTE_DESTINATIONS[destIdx];

  const { data: routes } = useGenerateRoutes(
    selectedVessel?.lat || 0,
    selectedVessel?.lon || 0,
    dest?.lat || 0,
    dest?.lon || 0,
    !!selectedVessel
  );

  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="flex items-center gap-2">{['Plan New Route', 'Compare Routes', 'Route Library'].map((t, i) => <button key={i} className={cn('px-4 py-1.5 text-xs font-bold rounded-md', i === 0 ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 shrink-0 overflow-y-auto space-y-4">{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Select Vessel</label>}{<select value={selectedVesselIdx} onChange={e => setSelectedVesselIdx(Number(e.target.value))} className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{(vessels || []).map((v: any, i: number) => <option key={i} value={i}>{v.name}</option>)}</select>}</div>}{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Destination</label>}{<select value={destIdx} onChange={e => setDestIdx(Number(e.target.value))} className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{ROUTE_DESTINATIONS.map((d, i) => <option key={i} value={i}>{d.label}</option>)}</select>}</div>}{<div className="border-t border-slate-100 pt-3">{<div className="text-[10px] font-bold text-slate-700 mb-2">Optimization Priority</div>}{<div className="space-y-2">{['Lowest Fuel Consumption', 'Safest Route', 'Fastest Route', 'Avoid High Ice Areas'].map((o, i) => <label key={i} className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">{<input type="checkbox" defaultChecked={i !== 2} className="rounded accent-blue-500"></input>}{<span>{o}</span>}</label>)}</div>}</div>}{<button className="w-full bg-blue-600 text-white text-xs font-bold py-2 rounded shadow hover:bg-blue-700 transition-colors">Generate Routes</button>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} routes={routes} forecastGeoJSON={forecastGeoJSON} center={selectedVessel ? [selectedVessel.lon, selectedVessel.lat] : undefined} zoom={selectedVessel ? 4 : undefined}></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-2.5 border border-slate-200 shadow text-[10px] space-y-1.5 w-36">{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Eco Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Safe Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-red-500 border-dashed border-b-2"></div>}{<span>Fastest Route</span>}</div>}</div>}{<div className="absolute bottom-12 right-16 z-10 bg-white/90 border border-blue-300 text-[10px] font-bold text-blue-700 px-2 py-1 rounded shadow">Cape Town</div>}{<div className="absolute bottom-8 left-1/2 z-10 bg-white/90 border border-green-300 text-[10px] font-bold text-green-700 px-2 py-1 rounded shadow">Maitri Station</div>}</div>}</div>}</div>;
}'''
start_or = code.find('function OnshoreRoute() {')
end_or = code.find('function OnshoreIceberg() {')
code = code[:start_or] + or_repl + '\n  ' + code[end_or:]

# 4. OnshoreIceberg
oi_repl = '''function OnshoreIceberg() {
  const { data: icebergs } = useIcebergs();
  const { data: stats } = useIcebergStats();
  const { data: forecastGeoJSON } = useSicForecast(0);
  
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap icebergs={icebergs} forecastGeoJSON={forecastGeoJSON}></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-1">Iceberg Size</div>}{[['All Icebergs', 'bg-slate-400'], ['Large (>1 km)', 'bg-red-500'], ['Medium (300m-1km)', 'bg-orange-400'], ['Small (<300m)', 'bg-yellow-400']].map(([l, c], i) => <div key={i} className="flex items-center gap-2">{<div className={cn('w-3 h-3 rounded-sm', c)}></div>}{<span>{l}</span>}</div>)}</div>}</div>}{<div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4 shrink-0">{<div className="flex items-center gap-3">{<div className="bg-slate-100 rounded-lg p-3 flex-1 text-center">{<div className="text-2xl font-black text-slate-800">{stats?.total || 0}</div>}{<div className="text-[9px] text-slate-500">Tracked Icebergs</div>}</div>}{<div className="bg-red-50 rounded-lg p-3 flex-1 text-center border border-red-200">{<div className="text-2xl font-black text-red-600">{stats?.new_24h || 0}</div>}{<div className="text-[9px] text-red-500">New (Last 24h)</div>}</div>}</div>}{<div className="bg-orange-50 rounded-lg p-3 border border-orange-200">{<div className="text-[9px] font-bold text-orange-700 mb-1">HIGH RISK (Near Routes)</div>}{<div className="text-2xl font-black text-orange-600">{stats?.high_risk || 0}</div>}</div>}{<div className="border-t border-slate-100 pt-3 space-y-2">{(icebergs || []).slice(0, 5).map((b: any, i: number) => <div key={i} className="flex items-center justify-between text-[10px] bg-slate-50 rounded p-2">{<span className="font-bold text-slate-700">{b.id}</span>}{<span className="text-slate-500">{b.size_cat}</span>}{<span className={cn('text-white px-2 py-0.5 rounded-full text-[9px] font-bold', b.risk === 'High' ? 'bg-red-500' : b.risk === 'Medium' ? 'bg-orange-400' : 'bg-green-500')}>{b.risk}</span>}</div>)}</div>}</div>}</div>;
}'''
start_oi = code.find('function OnshoreIceberg() {')
end_oi = code.find('function OnshoreCommandCenter(')
code = code[:start_oi] + oi_repl + '\n  ' + code[end_oi:]

# 5. OnboardNavigation
obn_repl = '''function OnboardNavigation() {
  const { data: vessels } = useVessels();
  const { data: icebergs } = useIcebergs();
  const { data: forecastGeoJSON } = useSicForecast(0);
  
  // Hardcode the onboard vessel for this view
  const myVessel = (vessels || []).find((v: any) => v.name === 'RV Bharati') || (vessels || [])[0];

  const { data: routes } = useGenerateRoutes(
    myVessel?.lat || 0,
    myVessel?.lon || 0,
    ROUTE_DESTINATIONS[0].lat,
    ROUTE_DESTINATIONS[0].lon,
    !!myVessel
  );

  return <div className="flex h-full p-3 gap-3 bg-[#0f172a]">{<div className="w-56 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-4 overflow-y-auto">{<div className="text-xs font-bold text-slate-300 border-b border-slate-700 pb-2">Vessel Information</div>}{<div className="flex items-center gap-3">{<div className="w-14 h-12 bg-slate-700 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-500"></Ship>}</div>}{<div>{<div className="text-sm font-bold text-white">{myVessel?.name || 'Vessel'}</div>}{<div className="text-[10px] text-slate-400">{myVessel?.type || 'Ship'}</div>}</div>}</div>}{<div className="grid grid-cols-2 gap-1.5 text-[9px]">{[['IMO:', myVessel?.imo || '9684012'], ['Call Sign:', 'VUAA'], ['MMSI:', '419001234'], ['Ice Class:', 'PC5'], ['Length:', '104 m'], ['Beam:', '18.0 m'], ['Draft:', '6.2 m'], ['Status:', myVessel?.status || 'Underway']].map(([l, v], i) => <React.Fragment key={i}>{<span className="text-slate-500">{l}</span>}{<span className={cn('font-medium', l === 'Status:' ? 'text-green-400' : 'text-slate-300')}>{v}</span>}</React.Fragment>)}</div>}{<div className="border-t border-slate-700 pt-3">{<div className="text-xs font-bold text-slate-300 mb-3">Current Position</div>}{<div className="space-y-1.5 text-[10px]">{<div className="text-slate-300 font-bold">Lat: {myVessel?.lat?.toFixed(3) || 0}&deg; / Lon: {myVessel?.lon?.toFixed(3) || 0}&deg;</div>}{[['Speed:', (myVessel?.speed_knots || 0) + ' kn'], ['Heading:', (myVessel?.heading || 0) + 'A']].map(([l, v], i) => <div key={i} className="flex gap-3">{<span className="text-slate-500 w-14">{l}</span>}{<span className="text-slate-200 font-bold">{v}</span>}</div>)}{<div className="mt-2 pt-2 border-t border-slate-700 space-y-1">{<div className="text-[9px] text-slate-500">Next Waypoint:</div>}{<div className="text-blue-400 font-bold text-xs">WP-12</div>}{<div className="text-[9px] text-slate-400">ETA: 14 Sep 2026, 06:20 UTC</div>}{<div className="text-[9px] text-slate-400">Distance: 420 nm</div>}</div>}</div>}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-700 shadow-sm">{<SharedMap vessels={vessels} icebergs={icebergs} routes={routes} forecastGeoJSON={forecastGeoJSON} center={myVessel ? [myVessel.lon, myVessel.lat] : undefined} zoom={4}></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-[#1e293b]/95 text-[10px] text-slate-300 p-3 rounded-lg border border-slate-700 space-y-1.5 w-40">{[['w-4 h-px bg-green-500 border-dashed border-b-2', 'Planned Route'], ['w-4 h-px bg-blue-400 border-dashed border-b-2', 'Alternative Route'], ['w-3 h-3 rounded-sm border-2 border-blue-400 bg-transparent', 'Waypoints'], ['w-3 h-3 bg-white/60 rounded-sm border border-slate-400', 'Icebergs'], ['w-3 h-3 bg-blue-600 rounded-sm opacity-60', 'Sea Ice (SIC)']].map(([cls, label], i) => <div key={i} className="flex items-center gap-2">{<div className={cls}></div>}{<span>{label}</span>}</div>)}</div>}</div>}{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-4 overflow-y-auto">{<div className="text-xs font-bold text-slate-300">Route Options (to Maitri Station)</div>}{<div className="text-[10px] text-slate-500">Select a recommended route:</div>}{<div className="bg-green-900/30 border border-green-700 rounded-lg p-3 space-y-2">{<div className="flex items-center gap-2 text-green-400 font-bold text-xs">{<span className="w-2 h-2 bg-green-500 rounded-full"></span>}Eco Route</div>}{<div className="text-[9px] text-slate-400">Lowest fuel consumption</div>}{<div className="flex justify-between text-[10px] text-slate-300 font-bold">{<span>? 7.5 days</span>}{<span>> 320 MT</span>}</div>}{<div className="text-[9px] text-slate-400">o" Moderate ice</div>}{<button className="w-full bg-blue-600 text-white text-[10px] font-bold py-1.5 rounded hover:bg-blue-700">Select</button>}</div>}{<div className="grid grid-cols-2 gap-2">{[{
            label: 'Safest Route',
            sub: 'Avoids high ice',
            days: '8.2 days',
            fuel: '340 MT',
            risk: 'o" Low risk',
            riskColor: 'text-green-400'
          }, {
            label: 'Fastest Route',
            sub: 'Min travel time',
            days: '5.9 days',
            fuel: '400 MT',
            risk: 's Higher risk',
            riskColor: 'text-red-400'
          }].map((r, i) => <div key={i} className="bg-[#0f172a] border border-slate-700 rounded-lg p-2.5 space-y-1.5">{<div className="text-blue-400 font-bold text-[10px]">{r.label}</div>}{<div className="text-[9px] text-slate-500">{r.sub}</div>}{<div className="text-[9px] text-slate-300 font-bold">{r.days} ? {r.fuel}</div>}{<div className={cn('text-[9px]', r.riskColor)}>{r.risk}</div>}{<button className="w-full bg-blue-600 text-white text-[9px] font-bold py-1 rounded hover:bg-blue-700">Select</button>}</div>)}</div>}</div>}</div>;
}'''
start_obn = code.find('function OnboardNavigation() {')
end_obn = code.find('function OnboardAnalytics() {')
if end_obn == -1: end_obn = code.find('function OnboardPanel(')
code = code[:start_obn] + obn_repl + '\n  ' + code[end_obn:]

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated OnshoreRoute, OnshoreIceberg, and OnboardNavigation")
