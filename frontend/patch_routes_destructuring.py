import re

with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace all instances of `const { data: routes } = useGenerateRoutes` with `const { routes } = useGenerateRoutes`
new_text = text.replace('const { data: routes } = useGenerateRoutes', 'const { routes } = useGenerateRoutes')

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Replaced destructured routes")
