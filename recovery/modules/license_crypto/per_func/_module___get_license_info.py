# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

status = ()()
if None:
    lf = _get_base_dir() / _LICENSE_FILE
    raw = None()
    payload = None(raw, _APP_ID)
    saved = None(payload.decode())
    exp_date = None.loads('exp_date', '')
    days = None('days_left', 0)
return {
    'mid': saved.get('mid', '') <INVALID> ('__SLICE__', None, 8, None),
    'days_left': days,
    None: None,
    None: None }
if status == 'trial':
    remaining = trial_days_left()
return {
    None: None,
    None: None }
if status == 'expired':
    pass
return {
    'status': 'expired' }
return {
    'status': 'none' }
except ImportError:
    payload = _pure_aes_decrypt(raw)
