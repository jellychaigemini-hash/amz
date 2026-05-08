"""
Recover all the BSC-specific modules from pyz_contents/:
  - expert_suggestions
  - rufus_cosmo
  - license_crypto
  - wiki_crypto
  - _config / config
  - activate_ui
  - user_agent

For each:
  1. Transpile 3.14 -> 3.13 bytecode
  2. Run pycdc to decompile
  3. Also dump the disassembly and strings for reference
"""
from __future__ import annotations

import marshal
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/projects/sandbox/decompile")
from transpile_314_to_313 import transpile_code, HEADER  # type: ignore
from dump_code import dump_pyc, extract_strings  # type: ignore

PYZ_DIR = Path("/projects/sandbox/decompile/pyz_contents")
OUT_DIR = Path("/projects/sandbox/decompile/recovered_modules")
OUT_DIR.mkdir(exist_ok=True)
PYCDC = "/projects/sandbox/pycdc/build/pycdc"

# Candidate modules that look like app-specific (not stdlib / not deps)
MODULES = [
    "expert_suggestions",
    "rufus_cosmo",
    "license_crypto",
    "wiki_crypto",
    "activate_ui",
]


def process_module(name: str):
    pyc_in = PYZ_DIR / f"{name}.pyc"
    if not pyc_in.exists():
        print(f"  [skip] {name} (no pyc)")
        return
    print(f"\n=== {name} ===")
    mod_dir = OUT_DIR / name
    mod_dir.mkdir(exist_ok=True)

    # 1. Load and transpile to 3.13
    data = pyc_in.read_bytes()
    try:
        code = marshal.loads(data[16:])
    except Exception as e:
        print(f"  [FAIL] marshal.loads: {e}")
        return

    try:
        code313 = transpile_code(code)
        blob = marshal.dumps(code313, 4)
        transpiled_pyc = mod_dir / f"{name}.transpiled.pyc"
        transpiled_pyc.write_bytes(HEADER + blob)
    except Exception as e:
        print(f"  [FAIL] transpile: {e}")
        return

    # 2. Disassembly + strings (always works, best fallback)
    dump_pyc(pyc_in, mod_dir / f"{name}.disasm.txt")
    extract_strings(pyc_in, mod_dir / f"{name}.strings.txt")

    # 3. Whole-module pycdc
    try:
        r = subprocess.run(
            [PYCDC, str(transpiled_pyc)], capture_output=True, timeout=60, text=False,
        )
        (mod_dir / f"{name}.pycdc.py").write_bytes(r.stdout)
        (mod_dir / f"{name}.pycdc.err").write_bytes(
            r.stderr + f"\n[exit={r.returncode}]\n".encode()
        )
        print(f"  whole-module: exit={r.returncode}, {len(r.stdout)}b stdout")
    except Exception as e:
        print(f"  [FAIL] pycdc module: {e}")

    # 4. Per-function pycdc (in case whole-module crashes)
    per_func_dir = mod_dir / "per_func"
    per_func_dir.mkdir(exist_ok=True)

    def walk(c, prefix=""):
        import types
        qual = f"{prefix}/{c.co_name}" if prefix else c.co_name
        yield qual, c
        for const in c.co_consts:
            if isinstance(const, types.CodeType):
                yield from walk(const, qual)

    ok = 0
    total = 0
    for qual, c in walk(code):
        total += 1
        safe = qual.replace("/", "__").replace("<", "_").replace(">", "_")
        try:
            c313 = transpile_code(c)
            pyc_bytes = HEADER + marshal.dumps(c313, 4)
            tmp_pyc = Path("/tmp/_recover.pyc")
            tmp_pyc.write_bytes(pyc_bytes)
            r = subprocess.run(
                [PYCDC, str(tmp_pyc)], capture_output=True, timeout=30, text=False,
            )
            out = r.stdout.decode("utf-8", errors="replace")
            (per_func_dir / f"{safe}.py").write_text(out, encoding="utf-8")
            (per_func_dir / f"{safe}.err").write_text(
                r.stderr.decode("utf-8", errors="replace") + f"\n[exit={r.returncode}]",
                encoding="utf-8",
            )
            non_comment = [
                l for l in out.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            if r.returncode in (0, 1) and len(non_comment) >= 1:
                ok += 1
        except Exception as e:
            (per_func_dir / f"{safe}.err").write_text(f"EXCEPTION: {e}", encoding="utf-8")

    print(f"  per-func: {ok}/{total} succeeded")


def main():
    for m in MODULES:
        process_module(m)


if __name__ == "__main__":
    main()
