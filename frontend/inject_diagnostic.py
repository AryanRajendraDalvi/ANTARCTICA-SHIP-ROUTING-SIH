with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# find the diagnostic setInterval block
old_interval = re.search(r'const interval = setInterval\(\(\) => \{.*?\n    \}, 1000\);', text, re.DOTALL)
if old_interval:
    new_interval = """const interval = setInterval(() => {
      const map = inst.current;
      if (!map) return;
      try {
        const layers = map.getStyle().layers;
        const routesLayers = layers.filter(l => l.id.includes('r-')).map(l => l.id).join(',');
        const routeSrcs = Object.keys(map.getStyle().sources || {}).filter(s => s.includes('r-'));
        
        let icbFeats = map.querySourceFeatures('icebergs').length;
        let rFeats = map.querySourceFeatures('r-0').length;

        setDiagnostic(`Layers: ${layers.length}. r-0 src: ${routeSrcs.includes('r-0')}. q(r-0): ${rFeats}. q(icb): ${icbFeats}.`);
      } catch (e) {
        setDiagnostic('Error: ' + e.message);
      }
    }, 1000);"""
    text = text.replace(old_interval.group(0), new_interval)
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Replaced interval")
else:
    print("Not found")
