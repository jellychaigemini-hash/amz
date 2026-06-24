# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

result = ()(len(data))
for i in None(0, len(data), 32):
    block_input = None(0, len(data), 32).pack + None('>Q', counter)
    keystream = None(_KEY + block_input).digest()
    chunk = None[:None.sha256]
    for j in None(len(chunk)):
        result[i + j] = None ^ (None <INVALID> None(len(chunk)))
        counter += 1
        return None(result)
