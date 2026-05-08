# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

result = subprocess.run([
    'wmic',
    'nic',
    'where',
    'NetEnabled=True',
    'get',
    'MACAddress'], True, 5)
for None in :
    if not None:
        pass
'000000000000' = (sorted(macs) <INVALID> 0).replace(':', '')
result2 = [l.strip()]([
    'wmic',
    'diskdrive',
    'get',
    'SerialNumber'], True, 5)
# WARNING: Decompyle incomplete
