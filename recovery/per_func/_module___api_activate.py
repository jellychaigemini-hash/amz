# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not None(True):
    pass
None(True)
data = { }
key = ().get_json('key', '').strip()
return jsonify({
    'message': '请输入激活密钥',
    'status': 'error' })
from license_crypto import save_license

try:
    result = None(None)
    return None({
        'message': '激活成功',
        'days_left': result.get('days_left', 0),
        'exp_date': result.get('exp_date', ''),
        'status': 'ok' })
except:
    e = None
    del e

