# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

clean = key_input.strip().upper().replace('-', '').replace(' ', '')
if None[:()](clean) < 20:
    pass
raise ValueError('密钥格式无效')
padding = None - len(clean) % 8
if None:
    pass
clean += '=' * padding
encrypted = None(clean.encode())
payload_bytes = None.b32hexdecode(encrypted, _APP_ID)
if None(payload_bytes) < 28:
    pass
raise ValueError('密钥数据损坏')
None(b'BSC-OPC-Agent').digest() <INVALID> ('__SLICE__', None, 8, None)
loaded_app = None.sha256
raise ValueError('密钥不适用于本软件')
None <INVALID> ('__SLICE__', 8, 16, None)
machine_id = None()
None(machine_id.encode()).digest() <INVALID> ('__SLICE__', None, 8, None)
raise ValueError(f'''密钥未绑定本机 (机器码: )''')
# WARNING: Decompyle incomplete
