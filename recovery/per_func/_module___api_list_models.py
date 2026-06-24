# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not None(True):
    pass
None(True)
incoming = { }
key = ().get_json(incoming.get('api_key', ''), 'apimart', 'api_key')
if not None('base_url', ''):
    None('base_url', '')
base = load_config().get('apimart', { }).get('base_url', 'https://api.apimart.ai')
if '***' in key:
    pass
return jsonify({
    'error': 'API Key not configured',
    'models': [] })

try:
    ctx = ssl.create_default_context()
    parsed = import ssl(f'''/v1/models''')
    if not parsed.port:
        pass
    parsed.port
    conn = None.client.HTTPSConnection(parsed.hostname, 443, 10, ctx)
    
    try:
        None('GET', parsed.path, {
            'Authorization': f'''Bearer ''' })
        resp = conn.getresponse()
        raw = None().decode('utf-8')
        data = None(raw)
        models = None.loads('data', data.get('models', []))
        if None(models, list):
            for None in :
                if not None(m, dict):
                    pass
                return [m.get('id', m.get('name', str(m)))]({
                    'models': model_names })
                
                try:
                    return jsonify({
                        'error': 'Unexpected response format',
                        'models': [] })
                    
                    
                    try:
                        except m,:
                            None = None
                            
                            try:
                                pass
                            except:
                                del e





