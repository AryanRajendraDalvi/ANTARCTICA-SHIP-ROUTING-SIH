with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# Find the map.on('style.load') and add a check for inst.current
old = "map.on('style.load', () => {"
new = "map.on('style.load', () => {\n      if (inst.current !== map) return;"

if old in text:
    text = text.replace(old, new, 1)
    with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Fixed style.load race condition")
else:
    print("Could not find style.load")
