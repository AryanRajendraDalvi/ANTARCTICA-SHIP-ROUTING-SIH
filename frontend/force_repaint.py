with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Insert routes repainter
repaint_effect = """  // ── Force repaints when routes update ──────────────────────────────────────────
  useEffect(() => {
    routesRef.current = routes || [];
    if (mapReady && inst.current) {
      inst.current.triggerRepaint();
    }
  }, [routes, mapReady]);

  // ── FlyTo Center ──────────────────────────────────────────────────────────"""

if "── FlyTo Center ──" in text:
    text = text.replace("  // ── FlyTo Center ──────────────────────────────────────────────────────────", repaint_effect, 1)

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
print("Added routes repaint effect")
