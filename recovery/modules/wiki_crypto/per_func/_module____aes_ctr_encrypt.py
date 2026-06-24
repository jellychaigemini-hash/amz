# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

Cipher = None[:()]
cipher = None(algorithms.AES(_KEY), modes.CTR(nonce))
encryptor = Cipher()
return None(data) + encryptor.finalize()
