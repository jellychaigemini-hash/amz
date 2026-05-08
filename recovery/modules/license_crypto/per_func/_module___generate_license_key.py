# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

None(b'BSC-OPC-Agent').digest() <INVALID> ('__SLICE__', None, 8, None)
None(machine_id.encode()).digest() <INVALID> ('__SLICE__', None, 8, None)
exp_ts = time.time(None()) + days * 86400
payload = None[:()] + hashlib.sha256.sha256.pack('>QI', exp_ts, days)
encrypted = None(payload, _APP_ID)
encoded = None(encrypted).decode().rstrip('=')
return (encoded,)(range(0, len(encoded), 5)())
except ImportError:
    encrypted = _pure_aes_encrypt(payload)
