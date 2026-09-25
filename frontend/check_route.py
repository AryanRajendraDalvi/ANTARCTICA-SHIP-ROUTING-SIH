import urllib.request, json
req = urllib.request.Request('http://localhost:8001/api/routes/generate', data=b'{"start_lat": -68, "start_lon": 70, "end_lat": -70, "end_lon": 72}', headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req).read().decode('utf-8')
data = json.loads(res)
print(data['routes'][0]['waypoints'][:3])
