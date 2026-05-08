"""
Recover expert_suggestions.py. It triggers a CPython 3.14.4 marshal heap bug
when the whole thing is marshalled at once, so we do EACH nested code object
in its own fresh python subprocess.
"""
from __future__ import annotations

import marshal
import os
import subprocess
import sys
import types
from pathlib import Path

PYCDC = "/projects/sandbox/pycdc/build/pycdc"
PY314 = "/root/.pyenv/versions/3.14.4/bin/python"
OUT_DIR = Path("/projects/sandbox/decompile/recovered_modules/expert_suggestions")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PER_FUNC = OUT_DIR / "per_func"
PER_FUNC.mkdir(exist_ok=True)

# Worker script invoked per function
WORKER = r"""
import sys, marshal, types
sys.path.insert(0, '/projects/sandbox/decompile')
from transpile_314_to_313 import transpile_code, HEADER

pyc_path = sys.argv[1]
target_name = sys.argv[2]  # the function name we want (or '<module>')
out_pyc = sys.argv[3]

data = open(pyc_path,'rb').read()
top = marshal.loads(data[16:])

def find_code(c, name):
    if c.co_name == name:
        return c
    for const in c.co_consts:
        if isinstance(const, types.CodeType):
            r = find_code(const, name)
            if r:
                return r
    return None

code = find_code(top, target_name)
if code is None:
    print('NOT_FOUND', file=sys.stderr)
    sys.exit(2)

try:
    t = transpile_code(code)
    blob = marshal.dumps(t, 4)
    open(out_pyc, 'wb').write(HEADER + blob)
    print('OK', len(blob))
except Exception as e:
    print('FAIL:', e, file=sys.stderr)
    sys.exit(3)
"""

WORKER_PATH = Path("/tmp/_worker_expert.py")
WORKER_PATH.write_text(WORKER, encoding="utf-8")


def walk(c, path=""):
    q = f"{path}/{c.co_name}" if path else c.co_name
    yield q, c
    for const in c.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk(const, q)


def safe_name(q: str) -> str:
    return q.replace("/", "__").replace("<", "_").replace(">", "_")


def main():
    pyc_in = "/projects/sandbox/decompile/pyz_contents/expert_suggestions.pyc"
    data = open(pyc_in, "rb").read()
    top = marshal.loads(data[16:])

    ok = 0
    total = 0
    for qual, code in walk(top):
        total += 1
        safe = safe_name(qual)
        out_pyc = Path(f"/tmp/_func_{safe}.pyc")
        # Invoke worker in a fresh python subprocess (so a crash doesn't kill us)
        r = subprocess.run(
            [PY314, str(WORKER_PATH), pyc_in, code.co_name, str(out_pyc)],
            capture_output=True, timeout=30, text=True,
        )
        if r.returncode != 0 or not out_pyc.exists():
            (PER_FUNC / f"{safe}.err").write_text(
                f"worker exit={r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}\n",
                encoding="utf-8",
            )
            print(f"  [crash] {qual}")
            continue

        # Run pycdc on the transpiled pyc
        try:
            rp = subprocess.run(
                [PYCDC, str(out_pyc)], capture_output=True, timeout=30, text=False,
            )
            (PER_FUNC / f"{safe}.py").write_bytes(rp.stdout)
            (PER_FUNC / f"{safe}.err").write_bytes(
                rp.stderr + f"\n[exit={rp.returncode}]\n".encode()
            )
            non_comment = [l for l in rp.stdout.decode("utf-8", errors="replace").splitlines()
                           if l.strip() and not l.strip().startswith("#")]
            if rp.returncode in (0, 1) and len(non_comment) >= 1:
                ok += 1
                print(f"  [ok]   {qual}")
            else:
                print(f"  [fail] {qual} exit={rp.returncode}")
        except Exception as e:
            (PER_FUNC / f"{safe}.err").write_text(f"pycdc exception: {e}", encoding="utf-8")
            print(f"  [err]  {qual}: {e}")

    print(f"\n{ok}/{total} succeeded")


if __name__ == "__main__":
    main()
