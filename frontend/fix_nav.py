import io

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

target = "{<div className=\"flex gap-5 text-[11px] font-medium text-slate-300\">{['Live View', 'Route Planning', 'Ice & Weather', 'Vessels', 'Analytics', 'Alerts', 'Reports'].map((t, i) => <span className={cn('flex items-center gap-1 cursor-pointer hover:text-white transition-colors', i === 0 && 'text-white')}>{t}</span>)}</div>}"

if target in code:
    code = code.replace(target, "")
    with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
        f.write(code)
    print("Fixed!")
else:
    print("Target not found.")
