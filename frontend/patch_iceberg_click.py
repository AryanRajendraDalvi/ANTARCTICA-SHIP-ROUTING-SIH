with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

OLD = """      el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background-color:${color};border:1px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);cursor:pointer;`;
      
      const popup = new maplibregl.Popup({ offset: size/2 })
        .setHTML(`<div class="p-2 text-xs"><div class="font-bold">${b.id}</div><div>Size: ${b.size_cat} (${b.size_km} km)</div><div>Drift: ${b.drift_speed_kn} kn @ ${b.drift_dir_deg}&deg;</div><div class="mt-1 font-bold text-${b.risk === 'High' ? 'red' : 'orange'}-600">Risk: ${b.risk}</div></div>`);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([b.lon, b.lat])
        .setPopup(popup)
        .addTo(map);"""

NEW = """      el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background-color:${color};border:1px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);cursor:pointer;pointer-events:auto;`;
      
      const popup = new maplibregl.Popup({ offset: size/2 })
        .setHTML(`<div class="p-2 text-xs"><div class="font-bold">${b.id}</div><div>Size: ${b.size_cat} (${b.size_km} km)</div><div>Drift: ${b.drift_speed_kn} kn @ ${b.drift_dir_deg}&deg;</div><div class="mt-1 font-bold text-${b.risk === 'High' ? 'red' : 'orange'}-600">Risk: ${b.risk}</div></div>`);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([b.lon, b.lat])
        .setPopup(popup)
        .addTo(map);
        
      el.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent map click
        if (!popup.isOpen()) marker.togglePopup();
      });"""

if OLD in text:
    text = text.replace(OLD, NEW)
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Patched iceberg clicks")
else:
    print("Could not find OLD block")
