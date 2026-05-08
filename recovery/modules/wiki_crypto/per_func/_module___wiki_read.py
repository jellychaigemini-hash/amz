# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

filepath = () / relative_path
enc_path = None(filepath.suffix + '.enc')
if None():
    pass
return decrypt_file(enc_path, relative_path).decode('utf-8', 'replace')
if filepath.exists():
    pass
return filepath.read_text('utf-8')
return ''
