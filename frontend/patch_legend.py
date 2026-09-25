import re

with open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = r"\{<div className=\"absolute top-3 left-3 z-10 bg-\[\#1e293b\]/90 text-white text-\[10px\] p-2 rounded shadow font-bold\">Sea Ice Concentration</div>\}\{<div className=\"absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-\[9px\] space-y-1 w-28\">\{<div className=\"font-bold text-slate-700 mb-1\">Concentration \(%\)</div>\}\{\[\['0-20', 'bg-blue-200'\], \['20-40', 'bg-blue-400'\], \['40-60', 'bg-blue-600'\], \['60-80', 'bg-yellow-500'\], \['80-100', 'bg-red-600'\]\]\.map\(\(\[label, color\]\) => <div className=\"flex items-center gap-2\">\{<div className=\{cn\('w-3 h-2 rounded-sm', color\)\}></div>\}\{<span className=\"text-slate-600\">\{label\}</span>\}</div>\)\}</div>\}"

# We replace it with dynamic labels and legends
new_content = """{<div className="absolute top-3 left-3 z-10 bg-[#1e293b]/90 text-white text-[10px] p-2 rounded shadow font-bold">
  {tab === 'Sea Ice' ? 'Sea Ice Concentration' : 
   tab === 'Weather' ? 'Wind Speed (knots)' : 
   tab === 'Ocean Currents' ? 'Surface Currents (m/s)' : 'Wave Height (m)'}
</div>}
{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-28">
  <div className="font-bold text-slate-700 mb-1">
    {tab === 'Sea Ice' ? 'Concentration (%)' : 
     tab === 'Weather' ? 'Wind (kn)' : 
     tab === 'Ocean Currents' ? 'Currents (m/s)' : 'Waves (m)'}
  </div>
  {
    (tab === 'Sea Ice' ? [
      ['0-20', 'bg-blue-200'], ['20-40', 'bg-blue-400'], ['40-60', 'bg-blue-600'], ['60-80', 'bg-yellow-500'], ['80-100', 'bg-red-600']
    ] : tab === 'Weather' ? [
      ['0-10', 'bg-blue-200'], ['10-20', 'bg-green-400'], ['20-30', 'bg-blue-500'], ['30-40', 'bg-indigo-500'], ['40+', 'bg-purple-500']
    ] : tab === 'Ocean Currents' ? [
      ['0.0-0.2', 'bg-orange-200'], ['0.2-0.4', 'bg-orange-400'], ['0.4-0.6', 'bg-rose-500'], ['0.6+', 'bg-rose-800']
    ] : [
      ['0-1', 'bg-teal-200'], ['1-2', 'bg-teal-400'], ['2-4', 'bg-sky-500'], ['4+', 'bg-sky-800']
    ]).map(([label, color], i) => (
      <div key={i} className="flex items-center gap-2">
        <div className={cn('w-3 h-2 rounded-sm', color)}></div>
        <span className="text-slate-600">{label}</span>
      </div>
    ))
  }
</div>}"""

if re.search(target, code):
    new_code = re.sub(target, new_content.replace('\n', ''), code)
    with open("src/app/page.tsx", "w", encoding="utf-8") as f:
        f.write(new_code)
    print("Legend fixed successfully!")
else:
    print("Target not found. Let's dump the exact lines.")
    with open("src/app/page.tsx", "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "Sea Ice Concentration" in line:
                print(f"Line {i}: {line.strip()}")
