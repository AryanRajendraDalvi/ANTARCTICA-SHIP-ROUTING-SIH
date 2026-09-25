import io
import re

with io.open("src/app/page.tsx", "r", encoding="utf-8") as f:
    code = f.read()

# Replace any <SharedMap that doesn't have heatmapType= with heatmapType="none"
# But wait, OnshoreOverview might already have heatmapType="none"
# And OnshoreIceWeather has heatmapType={tab.toLowerCase()}

def replacer(match):
    tag = match.group(0)
    if 'heatmapType' not in tag:
        # insert heatmapType="none" right after <SharedMap
        return tag.replace('<SharedMap', '<SharedMap heatmapType="none"')
    return tag

code = re.sub(r"<SharedMap[^>]*>", replacer, code)

with io.open("src/app/page.tsx", "w", encoding="utf-8") as f:
    f.write(code)
print("Disabled heatmap everywhere except IceWeather panel!")
