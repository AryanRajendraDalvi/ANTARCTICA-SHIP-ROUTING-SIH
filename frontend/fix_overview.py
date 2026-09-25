with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# Find OnshoreOverview function block
start_idx = text.find('function OnshoreOverview() {')
end_idx = text.find('function OnshoreVessels() {')

if start_idx != -1 and end_idx != -1:
    overview_text = text[start_idx:end_idx]
    
    # Replace the broken LiveMap call in OnshoreOverview
    broken_call = r'<LiveMap vessels=\{vessels \|\| \[\]\} icebergs=\{icebergs \|\| \[\]\} routes=\{plannedRoutes\} forecastGeoJSON=\{sicGeoJSON\} center=\{selectedVessel \? \[selectedVessel\.lon, selectedVessel\.lat\] : undefined\} zoom=\{selectedVessel \? 5 : undefined\} />'
    fixed_call = '<LiveMap vessels={vessels || []} icebergs={icebergs || []} routes={plannedRoutes} forecastGeoJSON={sicGeoJSON} />'
    
    overview_text_fixed = re.sub(broken_call, fixed_call, overview_text)
    
    text = text[:start_idx] + overview_text_fixed + text[end_idx:]
    
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Fixed OnshoreOverview")
else:
    print("Could not find OnshoreOverview bounds")
