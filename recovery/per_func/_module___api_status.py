# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

.job_lock()
jobs.get(job_id)
if not job:
    pass
return (jsonify({
    'error': 'Job not found' }), 404)({
    'error': job.get('error'),
    'result': job.get('result'),
    'message': job.get('message', ''),
    'step': job <INVALID> 'step',
    'progress': job <INVALID> 'progress',
    'status': job <INVALID> 'status',
    'asin': job.get('asin', ''),
    'job_id': job_id })
with (), None, ().job_lock, :
    continue
