"""
Produce a single reconstructed-app.py-like file that, for each function in
app.pyc (in original source order), shows:
  1. The pycdc decompile output if available, and
  2. The disassembly as a fallback / sanity check.

Also produces a clean module-level summary at the top.
"""
from __future__ import annotations

import io
import marshal
import types
from pathlib import Path

SRC_PYC = Path("/projects/sandbox/decompile/extracted/app.pyc")
PER_FUNC_DIR = Path("/projects/sandbox/decompile/per_func")
OUT = Path("/projects/sandbox/decompile/app_reconstructed.py")


def walk_codes(code: types.CodeType, prefix: str = ""):
    qual = f"{prefix}/{code.co_name}" if prefix else code.co_name
    yield qual, code
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk_codes(c, qual)


def safe_name(qual: str) -> str:
    return qual.replace("/", "__").replace("<", "_").replace(">", "_")


def load_pycdc(qual: str) -> str | None:
    p = PER_FUNC_DIR / f"{safe_name(qual)}.py"
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8", errors="replace")
    # Strip the standard pycdc header comments
    lines = txt.splitlines()
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).rstrip()


def short_disasm(code: types.CodeType, indent: int = 0) -> str:
    """Compact disassembly of just this code object."""
    import dis
    buf = io.StringIO()
    try:
        dis.dis(code, file=buf, depth=0)
    except TypeError:
        dis.dis(code, file=buf)
    pad = "    " * indent
    return "\n".join(f"{pad}# {ln}" for ln in buf.getvalue().splitlines())


def main():
    data = SRC_PYC.read_bytes()
    top = marshal.loads(data[16:])

    out_lines: list[str] = []
    out_lines.append('"""')
    out_lines.append("Reconstructed app.py (from BSC-OPC-Agent.exe)")
    out_lines.append("")
    out_lines.append("This file combines two sources:")
    out_lines.append("  1. Best-effort Python decompilation via pycdc (with a custom")
    out_lines.append("     3.14 -> 3.13 bytecode transpiler to get past Python 3.14's")
    out_lines.append("     new opcodes like LOAD_FAST_BORROW, CALL_KW, TO_BOOL, etc.)")
    out_lines.append("  2. Full bytecode disassembly for each function, as a fallback")
    out_lines.append("     when the decompiler couldn't produce clean output.")
    out_lines.append("")
    out_lines.append("Function-level sections are labeled DECOMPILE-OK (high confidence)")
    out_lines.append("or DECOMPILE-PARTIAL (refer to disassembly and strings).")
    out_lines.append('"""')
    out_lines.append("")

    # Module-level
    out_lines.append("# " + "=" * 72)
    out_lines.append("# MODULE TOP-LEVEL")
    out_lines.append("# " + "=" * 72)
    mod_dec = load_pycdc("<module>")
    if mod_dec and len(mod_dec.strip()) > 20:
        out_lines.append("# --- pycdc decompilation (partial) ---")
        out_lines.append(mod_dec)
    else:
        out_lines.append("# (module-level decompilation failed; see disassembly)")
    out_lines.append("")
    out_lines.append("# --- module-level disassembly ---")
    out_lines.append(short_disasm(top))
    out_lines.append("")

    # For each function
    for qual, code in walk_codes(top):
        if qual == "<module>":
            continue
        out_lines.append("")
        out_lines.append("# " + "=" * 72)
        out_lines.append(f"# FUNCTION: {qual}  (file {code.co_filename}, line {code.co_firstlineno})")
        out_lines.append(f"# args={code.co_argcount}  varnames={list(code.co_varnames)[:8]}")
        out_lines.append("# " + "=" * 72)

        dec = load_pycdc(qual)
        if dec:
            dec_clean = dec.strip()
            # Heuristic: if the decompile has an INCOMPLETE warning and <5 lines of code, mark as partial
            incomplete = "Decompyle incomplete" in dec
            sizable = len(dec_clean.splitlines()) > 3
            status = "OK" if (sizable and not incomplete) else "PARTIAL"
            out_lines.append(f"# --- pycdc decompilation ({status}) ---")
            out_lines.append(dec)
        else:
            out_lines.append("# --- pycdc decompilation FAILED ---")

        # Always include the disassembly for verification
        out_lines.append("")
        out_lines.append("# --- disassembly ---")
        out_lines.append(short_disasm(code, indent=0))
        # Consts too
        if code.co_consts:
            out_lines.append("# --- constants ---")
            for i, const in enumerate(code.co_consts):
                if isinstance(const, types.CodeType):
                    continue
                r = repr(const)
                if len(r) > 300:
                    r = r[:300] + "..."
                out_lines.append(f"#   [{i}] {r}")

    OUT.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"[ok] wrote {OUT} ({OUT.stat().st_size} bytes, {len(out_lines)} lines)")


if __name__ == "__main__":
    main()
