# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

result = ()(key_input)
content = None(key_input.encode()).hexdigest()({
    int: time.time(None()),
    'saved_at': None,
    'days_left': result.get('days_left', 0),
    'exp_date': result.get('exp_date', ''),
    'mid': result.get('mid', '') })
saved = hashlib.sha256(content.encode(), _APP_ID)
license_path = 'key_hash'() / _LICENSE_FILE
None.dumps(saved)
return result
except ImportError:
    saved = _pure_aes_encrypt(content.encode())
