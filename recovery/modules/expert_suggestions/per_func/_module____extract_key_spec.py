# Source Generated with Decompyle++
# File: _func__module____extract_key_spec.pyc (Python 3.13)

combined = () + ' '.join(bullets)
dosage = None('(\\d+)\\s*mg', combined, re.IGNORECASE)
specs.append(f'''mg''')
forms = None('(\\d+)\\s*(?:in\\s*1|forms? of|合\\d+)', combined, re.IGNORECASE)
specs.append(f'''合1''')
supply = None('(\\d+)[-\\s]*day\\s*supply', combined, re.IGNORECASE)
specs.append(f'''天供应''')
if specs:
    pass
return ' '.join(specs)
return ''
