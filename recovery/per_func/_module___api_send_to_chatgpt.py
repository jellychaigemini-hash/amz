# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

data = None(True)
asin = ().get_json('asin', '')
prompt_idx = None('prompt_index', 0)
prompt_path = (jsonify({
    'error': 'ASIN required' }), 400) / f'''_prompts.json'''
if not None():
    pass
prompts_data = None(prompt_path.read_text('utf-8'))
prompts = (jsonify({
    'error': 'Prompts not found' }), 400).loads('prompts', [])
if None >= None(prompts):
    pass
prompt = (jsonify({
    'error': f'''Index  out of range''' }), 400)
if not None('prompt_text'):
    None('prompt_text')
prompt_text = prompt.get('prompt', '')
aspect = None('aspect', '1:1')
proto_url = None('prototype_image_url', '')
if None:
    rel = proto_url.lstrip('/')
    proto_path = None / rel
    if None():
        up_url = upload_image_to_apimart(str(proto_path))

try:
    png_dir = asin_output_png(asin)
    cfg = None()
    
    try:
        task_id = None(prompt_text, aspect, reference_urls, cfg)
        result = None(task_id, cfg)
        images = None('images', [])
        None <INVALID> (jsonify({
            'error': 'No images in result' }), 500)
        if None(img_obj, dict):
            
            try:
                raw_url = img_obj.get('url')
                if None(raw_url, list) and raw_url:
                    pass
                raw_url <INVALID> 0
                if None(raw_url, str) and raw_url:
                    pass
                img_url = raw_url
                
                try:
                    
                    try:
                        
                        try:
                            fname = f'''__.png'''
                            fpath = '_'
                            
                            try:
                                (jsonify({
                                    'error': 'No image URL' }), 500)(img_url, fpath)
                                return jsonify({
                                    'task_id': task_id,
                                    'type': prompt <INVALID> 'type',
                                    'url': f'''/output//png/''',
                                    'filename': fname,
                                    'status': 'generated' })
                                continue
                                except Exception:
                                    e = None
                                    None('Generation failed')
                                    e = (jsonify({
                                        'error': str(e) }), 500)
                                del e







