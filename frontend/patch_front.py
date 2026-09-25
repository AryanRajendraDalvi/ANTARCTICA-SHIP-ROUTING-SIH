import re

filepath = 'src/app/page.tsx'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Update Vessel Interface
old_iface = '''  status: string;
  color: string;
}'''
new_iface = '''  status: string;
  color: string;
  origin?: string;
  destination?: string;
}'''
text = text.replace(old_iface, new_iface)

# Update LiveMap Popup
old_popup = '''                <div>Lat: &deg; Lon: &deg;</div>
                <div>Speed:  kn | Hdg: &deg;</div>
                <div>Status: <span class="text-green-600 font-bold"></span></div>'''
new_popup = '''                <div>Lat: &deg; Lon: &deg;</div>
                <div>Speed:  kn | Hdg: &deg;</div>
                <div class="pt-1 border-t border-slate-200 mt-1">Route: <b></b> &rarr; <b></b></div>
                <div>Status: <span class="text-green-600 font-bold"></span></div>'''
text = text.replace(old_popup, new_popup)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated Frontend with Origin and Destination.")
