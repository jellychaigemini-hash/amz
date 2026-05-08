# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)


try:
    ()(job_id, 'collect', 15, '正在准备产品上下文…')
    context = build_context(job_id, asin, marketplace)
    None(job_id, 'collect', 30, '正在下载产品参考图片…')
    _download_product_images(asin, marketplace, context)
    emit_progress(job_id, 'mcp', 40, '产品上下文已就绪', context)
    emit_progress(job_id, 'expert', 55, '正在生成 Rufus & COSMO 专家建议…')
    from expert_suggestions import build_cosmo_title, build_cosmo_bullets, build_rufus_qa, extract_selling_points, build_data_insights
    extract_selling_points = extract_selling_points
    expert_data = {
        build_data_insights: None(context),
        None(context): 'data_insights',
        'selling_points': extract_selling_points,
        build_rufus_qa: None(context),
        None(context): 'qa_suggestions' }
    ctx_path = build_cosmo_bullets / f'''_context.json'''
    json.dumps(None(context, 2, False), 'utf-8')
    emit_progress(job_id, 'expert', 65, '专家建议已生成', expert_data)
    emit_progress(job_id, 'prompt', 75, '正在生成 GPT Image-2 提示词…')
    prompts_data = generate_prompts(asin, marketplace, context)
    'bullets_analysis'(job_id, 'prompt', 90, f'''已生成  条提示词，等待生成图片''', prompts_data)
    .emit_progress()
    
    try:
        build_cosmo_title(None(context), {
            'expert_data': expert_data,
            job_lock, None, job_lock.emit_progress, : 'done' }, None)
        return None
        with None:
            
            try:
                
                try:
                    return None
                except Exception:
                    None = None
                    None(f'''Job  failed''')
                    emit_progress(job_id, 'error', False, str(e))
                    .emit_progress()
                    None.exception(job_lock, None, job_lock.emit_progress, , 'error'(e), None)
                    None = None
                    with None:
                        e = None
                        e = None




