"""
Dump a .pyc file into a human-readable "pseudo-source":
- Module-level disassembly with line numbers
- Full structure: classes, functions (with args, defaults, closures)
- All string/number constants inlined
- Recursive through nested code objects

Works natively for Python 3.14 since we run under Python 3.14.
"""
from __future__ import annotations

import dis
import io
import marshal
import sys
import types
from pathlib import Path


def load_code(pyc_path: Path) -> types.CodeType:
    data = pyc_path.read_bytes()
    # Python 3.14 pyc header is 16 bytes
    return marshal.loads(data[16:])


def fmt_const(c, max_len: int = 200) -> str:
    if isinstance(c, types.CodeType):
        return f"<code {c.co_name} at {c.co_firstlineno}>"
    r = repr(c)
    if len(r) > max_len:
        r = r[: max_len - 3] + "..."
    return r


def dump_code(code: types.CodeType, out: io.StringIO, indent: int = 0, path: str = "") -> None:
    pad = "    " * indent
    qual = f"{path}.{code.co_name}" if path else code.co_name
    out.write(f"{pad}# === CODE: {qual}  (file={code.co_filename}, line={code.co_firstlineno}) ===\n")
    out.write(f"{pad}# argcount={code.co_argcount}, posonly={code.co_posonlyargcount}, "
              f"kwonly={code.co_kwonlyargcount}, stacksize={code.co_stacksize}\n")
    out.write(f"{pad}# varnames={code.co_varnames}\n")
    out.write(f"{pad}# freevars={code.co_freevars}, cellvars={code.co_cellvars}\n")
    out.write(f"{pad}# names={code.co_names}\n")

    # Constants (excluding code objects, which we recurse into)
    string_consts = []
    for i, c in enumerate(code.co_consts):
        if isinstance(c, types.CodeType):
            continue
        string_consts.append((i, c))
    if string_consts:
        out.write(f"{pad}# constants:\n")
        for i, c in string_consts:
            out.write(f"{pad}#   [{i}] {fmt_const(c)}\n")

    # Disassembly
    out.write(f"{pad}# --- bytecode ---\n")
    buf = io.StringIO()
    try:
        dis.dis(code, file=buf, depth=0)  # depth=0: only this code object
    except TypeError:
        # Older APIs
        dis.dis(code, file=buf)
    for line in buf.getvalue().splitlines():
        out.write(f"{pad}# {line}\n")
    out.write(f"{pad}# --- end bytecode ---\n\n")

    # Recurse into nested code objects (functions, classes, comprehensions)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            dump_code(c, out, indent + 1, qual)


def dump_pyc(pyc_path: Path, out_path: Path) -> None:
    try:
        code = load_code(pyc_path)
    except Exception as e:
        out_path.write_text(f"# Failed to load: {e}\n", encoding="utf-8")
        return
    buf = io.StringIO()
    buf.write(f"# Reconstructed from: {pyc_path}\n")
    buf.write(f"# Python magic: {pyc_path.read_bytes()[:4].hex()}\n\n")
    dump_code(code, buf, 0, "")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(buf.getvalue(), encoding="utf-8")


def extract_strings(pyc_path: Path, out_path: Path) -> None:
    """Extract all string constants recursively."""
    try:
        code = load_code(pyc_path)
    except Exception as e:
        out_path.write_text(f"# Failed: {e}\n", encoding="utf-8")
        return

    strings: list[tuple[str, str]] = []  # (qualified_path, string)

    def walk(c: types.CodeType, path: str):
        qual = f"{path}.{c.co_name}" if path else c.co_name
        for const in c.co_consts:
            if isinstance(const, str):
                strings.append((qual, const))
            elif isinstance(const, (bytes,)):
                try:
                    strings.append((qual, const.decode("utf-8")))
                except UnicodeDecodeError:
                    strings.append((qual, f"<bytes len={len(const)}>"))
            elif isinstance(const, types.CodeType):
                walk(const, qual)

    walk(code, "")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for qual, s in strings:
            s_disp = s.replace("\n", "\\n")
            if len(s_disp) > 500:
                s_disp = s_disp[:500] + "..."
            f.write(f"[{qual}]\n  {s_disp}\n\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: dump_code.py <pyc> <out.txt> [--strings]")
        sys.exit(1)
    pyc = Path(sys.argv[1])
    out = Path(sys.argv[2])
    if "--strings" in sys.argv:
        extract_strings(pyc, out)
    else:
        dump_pyc(pyc, out)
    print(f"[ok] wrote {out}")
