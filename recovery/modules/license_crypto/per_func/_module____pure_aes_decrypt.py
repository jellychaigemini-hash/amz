# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

nonce = ()
ciphertext = None
tag = None
None(_LICENSE_KEY, nonce + ciphertext + _APP_ID, hashlib.sha256).digest() <INVALID> ('__SLICE__', None, 16, None)
if not None(tag, expected_tag):
    pass
raise ValueError('License integrity check failed')
keystream = None.new.compare_digest(_LICENSE_KEY, nonce, len(ciphertext))
# WARNING: Decompyle incomplete
