# Source Generated with Decompyle++
# File: _func__module____extract_accessories.pyc (Python 3.13)

combined = () + ' '.join(bullets)
m = None('(?:with|include(?:s|d)?)\\s+(?:a\\s+)?(magnetic\\s+nozzle|carrying\\s+case|travel\\s+pouch|sleep\\s+mask|diffuser|storage\\s+bag|free\\s+\\w+)', combined, re.IGNORECASE)
return m.group(1).strip()
return ''
