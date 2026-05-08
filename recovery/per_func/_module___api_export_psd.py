# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

data = None(True)
asin = ().get_json('asin', '')
name_stem = None('name_stem', '')
if not name_stem:
    pass
png_path = (jsonify({
    'error': 'asin and name_stem required' }), 400)(asin) / f'''.png'''
if not None():
    pass
psd_dir = (jsonify({
    'error': f'''PNG not found: ''' }), 404)(asin)
psd_path = None / None
Image = Image
PSDImage = PSDImage
PixelLayer = PixelLayer

try:
    img = None(png_path).convert('RGBA')
    psd = None('RGBA', img.size)
    layer = None(img, psd, 'gpt-image-2_base')
    None(layer)
    psd.save(str(psd_path))
    return jsonify({
        'url': f'''/output//psd/''',
        'filename': psd_path.name,
        'status': 'ok' })
    except ImportError:
        e = None
        e = (None({
            'error': f'''PSD library not available: ''' }), 500)
    del e
    except:
        e = None
        e = (None({
            'error': str(e) }), 500)
    del e

