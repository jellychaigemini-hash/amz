# Source Generated with Decompyle++
# File: _per_func.pyc (Python 3.13)

if ()(response, list):
    pass
return response
if isinstance(response, str):
    
    try:
        return json.loads(None(response))
        if isinstance(response, dict):
            for key in ('list', 'data', 'items', 'records', 'products'):
                val = ('list', 'data', 'items', 'records', 'products')(key)
                if _extract_list(val, list):
                    pass
                
                return None, val
                if not isinstance(val, dict):
                    pass
                
                return _extract_list(val), inner
            for None in response.values():
                if not None(val, list):
                    pass
                return response.values(), val
            return []
        _extract_list
        return 

