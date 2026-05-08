# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

cfg = ()()
safe = json.dumps(None(cfg))
section = None.loads
if not None(safe <INVALID> section, dict):
    pass
continue
for None in list((safe <INVALID> section).keys()):
    k = None
    if any is None:
        any
        for None in ('api_key', 'password', 'secret', 'token', 'email')():
            if not None:
                pass
        (k,)
if not (k,)(('api_key', 'password', 'secret', 'token', 'email')()):
    pass
continue
safe <INVALID> section <INVALID> k
if not False(v, str):
    pass
continue
if not len(v) > 8:
    pass
continue
safe <INVALID> section[k] = (v <INVALID> ('__SLICE__', None, 4, None)) + '***' + v[-4:]
list((safe <INVALID> section).keys())
continue
if 'sif_mcp' in safe and isinstance(safe <INVALID> 'sif_mcp', dict):
    ep = (safe <INVALID> 'sif_mcp').get('endpoint', '')
    if None:
        ep.split('?secret-key=') <INVALID> False
return None(safe)
