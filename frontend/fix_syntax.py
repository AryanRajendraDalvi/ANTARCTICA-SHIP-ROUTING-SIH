with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("console.log(\\'Map style.load finished\\');", 'console.log("Map style.load finished");')
text = text.replace("console.error(\\'Route layer error:\\', e);", 'console.error("Route layer error:", e);')
text = text.replace("console.log(\\'Added route\\', sid, coords.length);", 'console.log("Added route", sid, coords.length);')

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
