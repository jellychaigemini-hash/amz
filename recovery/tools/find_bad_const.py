"""Find what constants choke marshal v4 in a pyc."""
import marshal
import sys
import types
from pathlib import Path

p = Path(sys.argv[1])
code = marshal.loads(p.read_bytes()[16:])

def walk(c, path=""):
    qual = f"{path}.{c.co_name}" if path else c.co_name
    for i, const in enumerate(c.co_consts):
        if isinstance(const, types.CodeType):
            walk(const, qual)
            continue
        try:
            marshal.dumps(const, 4)
        except ValueError:
            print(f"  BAD in {qual} consts[{i}]: type={type(const).__name__!r} value={const!r}")
        except Exception as e:
            print(f"  ERR in {qual} consts[{i}]: {e}")

walk(code)
print("done")
