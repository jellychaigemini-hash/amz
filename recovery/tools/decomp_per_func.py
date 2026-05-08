"""
Decompile each nested code object from app.pyc individually. If pycdc crashes
or fails on one, skip it and continue with the others.

Writes each function's attempt to a file under /projects/sandbox/decompile/per_func/
"""
from __future__ import annotations

import marshal
import subprocess
import sys
import types
from pathlib import Path

# Import the transpiler functions
sys.path.insert(0, "/projects/sandbox/decompile")
from transpile_314_to_313 import transpile_code, HEADER  # type: ignore


PYCDC = "/projects/sandbox/pycdc/build/pycdc"


def extract_code_objects(code: types.CodeType, prefix: str = ""):
    """Yield (qualified_name, code) for every code object (top-level + nested)."""
    qual = f"{prefix}/{code.co_name}" if prefix else code.co_name
    yield qual, code
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from extract_code_objects(c, qual)


def wrap_as_module(code: types.CodeType) -> types.CodeType:
    """Wrap a function-level code object into a minimal module-level code
    object that just returns it. pycdc can then decompile it as top-level."""
    # Simplest: use the code itself as a module. pycdc doesn't require it to be
    # module-level to decompile; it'll emit "def <name>(...)" or similar.
    # But pycdc usually expects a module (<module> code object). It does handle
    # function code if passed directly via the raw loader. Just try as-is.
    return code


def decompile_one(code: types.CodeType, out_path: Path, err_path: Path) -> tuple[bool, str]:
    transpiled = transpile_code(code)
    blob = marshal.dumps(transpiled, 4)
    pyc_bytes = HEADER + blob
    tmp_pyc = Path("/tmp/_per_func.pyc")
    tmp_pyc.write_bytes(pyc_bytes)
    try:
        r = subprocess.run(
            [PYCDC, str(tmp_pyc)],
            capture_output=True,
            timeout=30,
            text=False,
        )
    except subprocess.TimeoutExpired:
        err_path.write_text("TIMEOUT", encoding="utf-8")
        return False, "timeout"
    out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("utf-8", errors="replace")
    # Normalize: if stdout contains "WARNING: Decompyle incomplete" but also
    # substantive code, still count as success.
    out_path.write_text(out, encoding="utf-8")
    err_path.write_text(err + f"\n[exit={r.returncode}]", encoding="utf-8")
    # Success criterion: pycdc produced at least 3 non-comment lines and did not
    # crash (returncode 0 or 1 with some content).
    non_comment_lines = [
        l for l in out.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    ok = r.returncode in (0, 1) and len(non_comment_lines) >= 1
    return ok, f"exit={r.returncode}, out_lines={len(out.splitlines())}, err_lines={len(err.splitlines())}"


def main():
    src = Path("/projects/sandbox/decompile/extracted/app.pyc")
    data = src.read_bytes()
    top = marshal.loads(data[16:])

    out_dir = Path("/projects/sandbox/decompile/per_func")
    out_dir.mkdir(exist_ok=True)

    results = []
    for qual, code in extract_code_objects(top):
        safe = qual.replace("/", "__").replace("<", "_").replace(">", "_")
        out_path = out_dir / f"{safe}.py"
        err_path = out_dir / f"{safe}.err"
        ok, info = decompile_one(code, out_path, err_path)
        status = "OK" if ok else "FAIL"
        results.append((status, qual, info))
        print(f"  [{status}] {qual} ({info})")

    # Summary
    ok_count = sum(1 for s, *_ in results if s == "OK")
    print(f"\n{ok_count}/{len(results)} succeeded")

    summary = out_dir / "_SUMMARY.txt"
    summary.write_text(
        "\n".join(f"{s}\t{q}\t{i}" for s, q, i in results), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
