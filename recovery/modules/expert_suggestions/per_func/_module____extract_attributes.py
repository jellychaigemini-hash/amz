# Source Generated with Decompyle++
# File: _func__module____extract_attributes.pyc (Python 3.13)

text = () + ' ' + ' '.join(bullets)
if None('\\d+[,\\.\\d]*\\s*RPM|电机|motor|brushless', text, re.IGNORECASE):
    attrs['core_function'] = '高速无刷电机'
    None.search['core_function_en'] = None
if None('supplement|vitamin|magnesium|mineral|nutrition', text, re.IGNORECASE):
    attrs['core_function'] = '高吸收率复合补充剂'
    None.search['core_function_en'] = None
if None('radio|对讲|PTT|POC|communication', text, re.IGNORECASE):
    attrs['core_function'] = '5G/4G POC公网对讲机'
    None.search['core_function_en'] = None
if None('dryer|吹风|hair', text, re.IGNORECASE):
    attrs['core_function'] = '高速负离子吹风机'
    None.search['core_function_en'] = None
if None('便携|轻|compact|lightweight|portable|travel', text, re.IGNORECASE):
    attrs['differentiator'] = '轻巧便携'
if None('认证|NSF|GMP|FDA|certified|approved', text, re.IGNORECASE):
    attrs['differentiator'] = '权威认证'
if None('8\\s*in\\s*1|复合|complex|blend', text, re.IGNORECASE):
    attrs['differentiator'] = '8合1复合配方'
if None('赠送|附送|包含|with.*nozzle|with.*accessory', text, re.IGNORECASE):
    m = None('(?:赠送|附送|包含|with)\\s*([^,，.\\n]+)', text, re.IGNORECASE)
    m.group(1).strip() <INVALID> ('__SLICE__', None, 30, None)
