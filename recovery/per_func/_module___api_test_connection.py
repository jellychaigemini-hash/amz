# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not None(True):
    pass
None(True)
incoming = { }
if ().get_json:
    am = incoming.get('apimart', { })
    key = None(am.get('api_key', ''), 'apimart', 'api_key')
    if not None('base_url', ''):
        None('base_url', '')
    base = load_config().get('apimart', { }).get('base_url', 'https://api.apimart.ai')
    if '***' in key:
        pass
    return jsonify({
        'message': 'API Key 未填写',
        'status': 'error' })

try:
    ctx = ssl.create_default_context()
    parsed = import ssl(f'''/v1/tasks/test''')
    if not parsed.port:
        pass
    parsed.port
    conn = None.client.HTTPSConnection(parsed.hostname, 443, 10, ctx)
    
    try:
        None('GET', parsed.path, {
            'Authorization': f'''Bearer ''' })
        resp = conn.getresponse()
        if None in (401, 403, 404):
            pass
        return jsonify({
            'message': 'API 可达',
            'status': 'ok' })
        
        try:
            return jsonify({
                'message': f'''Connected ()''',
                'status': 'ok' })
            if service == 'sif':
                sf = incoming.get('sif_mcp', { })
                key = None(sf.get('api_key', ''), 'sif_mcp', 'api_key')
                if not None('endpoint', ''):
                    None('endpoint', '')
                ep = load_config().get('sif_mcp', { }).get('endpoint', '')
                return jsonify({
                    'message': 'Endpoint 未填写',
                    'status': 'error' })
            parsed = None.parse.urlparse(ep.rstrip('/'))
            if parsed.port:
                pass
        base = f'''://'''''
        if None:
            pass

    path = '/mcp'
    if not parsed.path('/mcp'):
        pass

    path = path.rstrip('/') + '/mcp'
    full_url = f''''''
    if '***' not in key and '?' not in full_url:
        pass
    full_url += f'''?secret-key='''
    ssl = None
    ctx = None()
    
    try:
        parsed2 = None.parse.urlparse(full_url)
        if not parsed2.port:
            pass
        parsed2.port
        conn = None.client.HTTPSConnection(parsed2.hostname, 443, 10, ctx)
        
        try:
            if parsed2.query:
                pass
        resp = conn.getresponse()
        try:
            if None < 500:
                pass
            return jsonify({
                'message': 'SIF MCP 可达',
                'status': 'ok' })
            return jsonify({
                'message': f'''HTTP ''',
                'status': 'error' })
            if service == 'sorftime':
                st = incoming.get('sorftime_mcp', { })
                
                try:
                    key = None(st.get('api_key', ''), 'sorftime_mcp', 'api_key')
                    if not None('endpoint', ''):
                        None('endpoint', '')
                    ep = load_config().get('sorftime_mcp', { }).get('endpoint', '')
                    return jsonify({
                        'message': 'Endpoint 未填写',
                        'status': 'error' })
                    if key or '***' in key:
                        pass
                    return jsonify({
                        'message': 'API Key 未填写',
                        'status': 'error' })
                    parsed = urllib.parse.urlparse(f'''?key=''')
                    ssl = None
                    ctx = None()
                    
                    try:
                        if not parsed.port:
                            pass
                        parsed.port
                        conn = None.client.HTTPSConnection(parsed.hostname, 443, 10, ctx)
                        if parsed.query:
                            pass
                    try:
                        'GET'(parsed.path, '?' + parsed.query + '', {
                            'Accept': 'application/json' })
                        resp = conn.getresponse()
                        if None < 500:
                            
                            try:
                                return jsonify({
                                    'message': 'Sorftime MCP 可达',
                                    'status': 'ok' })
                                return jsonify({
                                    'message': f'''HTTP ''',
                                    'status': 'error' })
                                except (jsonify({
                                    'message': f'''Unknown service: ''',
                                    'status': 'error' }), 400):
                                    e = None
                                    
                                    try:
                                        del e
                                        except Exception:
                                            None = 
                                        del e
                                        except Exception:
                                            None = 
                                        del e







