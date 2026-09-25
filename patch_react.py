import re

with open('frontend/src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update LiveMap JSX call in OnshoreIceWeather
text = re.sub(
    r'<LiveMap forecastGeoJSON=\{sicGeoJSON\} />\s*<ForecastSlider step=\{step\} setStep=\{setStep\} />',
    r"""<LiveMap forecastGeoJSON={sicGeoJSON} heatmapType={tab === 'Sea Ice' ? 'sic' : tab === 'Weather' ? 'wind' : tab === 'Ocean Currents' ? 'currents' : 'waves'} />
          <ForecastSlider step={step} setStep={setStep} />""",
    text
)

# 2. Update Legend
legend_start = text.find('<div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-28">')
if legend_start != -1:
    legend_end = text.find('</div>', text.find('))}</div>', legend_start)) + 6
    if legend_end != -1:
        new_legend = """<div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-32">
            <div className="font-bold text-slate-700 mb-1">
              {tab === 'Sea Ice' ? 'SIC Concentration' : tab === 'Weather' ? 'Wind Speed (kn)' : tab === 'Ocean Currents' ? 'Currents (kn)' : 'Wave Height (m)'}
            </div>
            {tab === 'Sea Ice' && [['0-20%','bg-blue-200'],['20-40%','bg-blue-400'],['40-60%','bg-yellow-400'],['60-80%','bg-orange-400'],['80-100%','bg-red-600']].map(([l,c]) => (
              <div key={l} className="flex items-center gap-2"><div className={"w-3 h-2 rounded-sm " + c} /><span className="text-slate-600">{l}</span></div>
            ))}
            {tab === 'Weather' && [['0-15','bg-sky-200'],['15-30','bg-sky-400'],['30-45','bg-sky-600'],['45-60','bg-purple-700'],['60+','bg-purple-900']].map(([l,c]) => (
              <div key={l} className="flex items-center gap-2"><div className={"w-3 h-2 rounded-sm " + c} /><span className="text-slate-600">{l}</span></div>
            ))}
            {tab === 'Ocean Currents' && [['0-1','bg-indigo-200'],['1-2','bg-indigo-400'],['2-3','bg-indigo-600'],['3-4','bg-indigo-800'],['4+','bg-slate-900']].map(([l,c]) => (
              <div key={l} className="flex items-center gap-2"><div className={"w-3 h-2 rounded-sm " + c} /><span className="text-slate-600">{l}</span></div>
            ))}
            {tab === 'Waves' && [['0-2m','bg-teal-200'],['2-4m','bg-teal-400'],['4-6m','bg-teal-600'],['6-8m','bg-teal-800'],['8m+','bg-slate-800']].map(([l,c]) => (
              <div key={l} className="flex items-center gap-2"><div className={"w-3 h-2 rounded-sm " + c} /><span className="text-slate-600">{l}</span></div>
            ))}
          </div>"""
        
        # Replace only the first occurrence (OnshoreIceWeather)
        text = text[:legend_start] + new_legend + text[legend_end:]

with open('frontend/src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)

print("Patch applied")
