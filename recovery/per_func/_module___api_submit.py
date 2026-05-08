# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

asin = ().form.get('asin', '').strip()
marketplace = None.form.get('marketplace', 'US').strip()
if not (jsonify({
    'error': 'ASIN required' }), 400)(asin):
    pass
uploaded_files = (jsonify({
    'error': 'Invalid ASIN format' }), 400).files.getlist('images')
main_dir = INPUT_DIR / asin / 'main'
None(True, True)
for f in uploaded_files:
    if not uploaded_files:
        pass
    fname = secure_filename(f.filename)
    None(str(main_dir / fname))
None().hex <INVALID> ('__SLICE__', None, 12, None)
.request()
# WARNING: Decompyle incomplete
