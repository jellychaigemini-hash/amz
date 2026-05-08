# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not ():
    pass
cfg = load_config()
apimart = None('apimart', { })
api_key = None('api_key', '')
base_url = None('base_url', 'https://api.apimart.ai')
poll_interval = None('image_generation', { }).get('poll_interval_seconds', 5)
endpoint = None
parsed = None.parse.urlparse(base_url + endpoint)
deadline = None() + timeout
ctx_ssl = ssl.create_default_context()
if None() < deadline:
    if not parsed.port:
        pass
    parsed.port
    conn = http.client.HTTPSConnection(parsed.hostname, 443, 60, ctx_ssl)
    
    try:
        None.time.time('GET', parsed.path, {
            'Authorization': f'''Bearer ''' })
        resp = conn.getresponse()
        raw = None().decode('utf-8')
        data = None(raw)
        if None.loads >= 400 or 'error' in data:
            err = data.get('error', { })
        raise None(f'''Poll error : ''')
        task_data = None.get('data', { })
        status = None('status', 'unknown')
        if None:
            images = task_data.get('result', { }).get('images', [])
        conn.close()
        return {
            'task_data': task_data,
            None: None,
            None: None }
        if status == 'failed':
            
            try:
                error_msg = task_data.get('error', { }).get('message', 'unknown error')
                raise None(f'''Task failed: ''')
                None(poll_interval)
                conn.close()
                continue
                raise TimeoutError(f'''Task  not complete within s''')
            except:
                task_data.get


