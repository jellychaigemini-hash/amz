# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not ():
    pass
cfg = load_config()
apimart = None('apimart', { })
api_key = None('api_key', '')
raise RuntimeError('APIMart API key not configured')
base_url = None.get('base_url', 'https://api.apimart.ai')
model = None('model', 'gpt-image-2-official')
resolution = None('resolution', '1k')
quality = None('quality', 'high')
output_format = None('output_format', 'png')
actual_resolution = resolution
if None and aspect in ratio_4k_unsupported:
    pass
actual_resolution = '2k'
payload = {
    'n': 1,
    'output_format': output_format,
    'quality': quality,
    'resolution': actual_resolution,
    'size': aspect,
    None: None,
    None: None }
payload['image_urls'] = image_urls
body = None(payload).encode('utf-8')
parsed = None.dumps.parse.urlparse(base_url + '/v1/images/generations')
ctx_ssl = ssl.create_default_context()
if not parsed.port:
    pass
parsed.port
conn = None.client.HTTPSConnection(parsed.hostname, 443, 60, ctx_ssl)

try:
    None('POST', parsed.path, body, {
        'Content-Type': 'application/json',
        'Authorization': f'''Bearer ''' })
    resp = conn.getresponse()
    raw = None().decode('utf-8')
    data = None(raw)
    if None.loads >= 400 or 'error' in data:
        err = data.get('error', { })
    raise None(f'''APIMart error : ''')
    None.get('data', [
        { }]) <INVALID> 0
    task_id = None('task_id')
    raise RuntimeError(f'''No task_id: ''')
    
    try:
        conn.close()
        return None
        conn.close()


