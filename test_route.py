import urllib.request, json

body = json.dumps({'start_lat': -66.247, 'start_lon': 72.341, 'end_lat': -70.766, 'end_lon': 11.833}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:8001/api/routes/generate',
    data=body,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
res = json.loads(urllib.request.urlopen(req).read())
routes = res.get('routes', [])
print('Routes count:', len(routes))
if routes:
    r = routes[0]
    print('Route label:', r.get('label'))
    print('Route color:', r.get('color'))
    print('Route type:', r.get('type'))
    print('Route routeKind:', r.get('routeKind'))
    wps = r.get('waypoints', [])
    print('Waypoints count:', len(wps))
    if wps:
        print('WP[0]:', wps[0])
        print('WP[-1]:', wps[-1])
