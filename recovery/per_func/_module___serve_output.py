# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if not ()(asin):
    pass
base = (jsonify({
    'error': 'Invalid ASIN' }), 400) / asin
safe_dir = {
    'psd': base / 'psd',
    None: None }.get(subdir)
if not safe_dir.exists():
    pass
return (jsonify({
    'error': 'Invalid directory' }), 400)(str(safe_dir), filename)
