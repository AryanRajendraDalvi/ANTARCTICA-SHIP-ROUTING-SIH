import re
with open('src/app/page.tsx', 'r', encoding='utf-8') as f:
    text = f.read()

injection = '''
  const [debugErr, setDebugErr] = useState('');
  useEffect(() => {
    const handleErr = (e) => setDebugErr(prev => prev + ' | ' + (e.message || e.reason || 'error'));
    window.addEventListener('error', handleErr);
    window.addEventListener('unhandledrejection', handleErr);
    return () => {
      window.removeEventListener('error', handleErr);
      window.removeEventListener('unhandledrejection', handleErr);
    };
  }, []);
'''

text = re.sub(r'(function LiveMap\([^)]+\) \{\n)', r'\g<1>' + injection, text, count=1)
text = text.replace('return (\n    <>', 'return (\n    <>\n      {debugErr && <div className="absolute top-0 left-0 z-50 bg-red-600 text-white p-4 max-w-full text-xs font-mono">ERR: {debugErr}</div>}')

with open('src/app/page.tsx', 'w', encoding='utf-8') as f:
    f.write(text)
