"""
Minimal PyInstaller archive extractor (inline, no pip required).
Based on the public PyInstaller archive format (CArchive).
Works for PyInstaller >= 4.x (cookie layout we check covers modern builds).
"""
from __future__ import annotations

import os
import struct
import sys
import zlib
import marshal
from pathlib import Path


# --- PyInstaller CArchive constants -------------------------------------------------
# Magic at the start of the cookie (end of archive):
PYINST_MAGIC = b"MEI\014\013\012\013\016"

# Newer cookie (PyInstaller >= 4) layout:
#   magic (8s) | lengthofPackage (I) | toc (I) | tocLen (I) | pyver (I) | pylibname (64s)
COOKIE_FMT_NEW = "!8sIIII64s"
COOKIE_SIZE_NEW = struct.calcsize(COOKIE_FMT_NEW)

# Older cookie:
#   magic (8s) | lengthofPackage (I) | toc (I) | tocLen (I) | pyver (I)
COOKIE_FMT_OLD = "!8sIIII"
COOKIE_SIZE_OLD = struct.calcsize(COOKIE_FMT_OLD)


def find_cookie(data: bytes) -> tuple[int, bool]:
    """Return (offset_of_magic, is_new_cookie)."""
    # Search from the end backwards, some builds may have trailing data.
    idx = data.rfind(PYINST_MAGIC)
    if idx == -1:
        raise RuntimeError("PyInstaller magic not found, not a PyInstaller exe?")
    # Heuristic: if there are at least 64 bytes of name after the old layout, treat as new.
    # Simpler: try new layout first (matches PyInstaller >=4), fall back to old.
    return idx, True


def extract(exe_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = exe_path.read_bytes()

    magic_off, _ = find_cookie(data)

    # Try new cookie first
    try:
        cookie = data[magic_off : magic_off + COOKIE_SIZE_NEW]
        magic, length_of_package, toc_off, toc_len, pyver, pylibname = struct.unpack(
            COOKIE_FMT_NEW, cookie
        )
        new_cookie = True
    except struct.error:
        cookie = data[magic_off : magic_off + COOKIE_SIZE_OLD]
        magic, length_of_package, toc_off, toc_len, pyver = struct.unpack(
            COOKIE_FMT_OLD, cookie
        )
        pylibname = b""
        new_cookie = False

    # The archive starts at: magic_off - (length_of_package - cookie_size_with_cookie)
    # Actually: magic_off + cookie_size = end of archive
    # archive_start = end_of_archive - length_of_package
    cookie_size = COOKIE_SIZE_NEW if new_cookie else COOKIE_SIZE_OLD
    end_of_archive = magic_off + cookie_size
    archive_start = end_of_archive - length_of_package

    # toc_off is offset from archive_start
    toc_abs = archive_start + toc_off
    toc_bytes = data[toc_abs : toc_abs + toc_len]

    print(f"[i] PyInstaller version field: {pyver}")
    print(f"[i] Python library: {pylibname.strip(chr(0).encode()).decode(errors='replace')}")
    print(f"[i] Archive start: {archive_start}, end: {end_of_archive}")
    print(f"[i] TOC at abs {toc_abs}, length {toc_len}")

    # Parse TOC entries
    # Each TOC entry:
    # entrySize (I) | entryPos (I) | cmprsdDataSize (I) | uncmprsdDataSize (I)
    # | cmprsFlag (B) | typeCmprsData (c) | name (entrySize - 18 bytes, null-terminated)
    entries = []
    offset = 0
    while offset < toc_len:
        (entry_size,) = struct.unpack("!I", toc_bytes[offset : offset + 4])
        fmt = f"!IIIIBc{entry_size - 18}s"
        fields = struct.unpack(fmt, toc_bytes[offset : offset + entry_size])
        (
            _esize,
            entry_pos,
            cmprsd_size,
            uncmprsd_size,
            cmprs_flag,
            type_cmprs,
            name,
        ) = fields
        name = name.rstrip(b"\x00").decode("utf-8", errors="replace")
        if not name:
            name = f"unknown_{entry_pos}"
        entries.append(
            {
                "name": name,
                "entry_pos": entry_pos,
                "cmprsd_size": cmprsd_size,
                "uncmprsd_size": uncmprsd_size,
                "cmprs_flag": cmprs_flag,
                "type": type_cmprs.decode("latin1"),
            }
        )
        offset += entry_size

    print(f"[i] {len(entries)} TOC entries")

    # Write TOC listing
    (out_dir / "_TOC.txt").write_text(
        "\n".join(
            f"{e['type']}\t{e['name']}\tcmprsd={e['cmprsd_size']}\tuncmprsd={e['uncmprsd_size']}"
            for e in entries
        ),
        encoding="utf-8",
    )

    for e in entries:
        raw = data[archive_start + e["entry_pos"] : archive_start + e["entry_pos"] + e["cmprsd_size"]]
        if e["cmprs_flag"]:
            try:
                raw = zlib.decompress(raw)
            except Exception as ex:
                print(f"[!] Failed to decompress {e['name']}: {ex}")
                continue

        # Normalize name path-safe
        name = e["name"].replace("\\", "/")
        # Strip absolute paths
        name = name.lstrip("/")
        target = out_dir / name

        # Type 'z' / 'Z' = PYZ archive (contains most modules as .pyc)
        # Type 's' = PYSOURCE (an entry script, stored as marshalled code object)
        # Type 'm' / 'M' = PYMODULE / PYPACKAGE (marshalled code object, also used)
        # Type 'b' = binary / DLL / PYD
        # Type 'x' = DATA
        # Type 'o' = runtime option
        # For 's', 'm', 'M' we need to wrap as a .pyc (add magic header + metadata)
        t = e["type"]
        if t in ("s", "m", "M"):
            # raw is a marshalled code object. Wrap as .pyc so decompilers accept it.
            # Python 3.14 pyc header: 16 bytes = magic(4) + bit_field(4) + mtime(4) + size(4)
            import importlib.util
            pyc_header = importlib.util.MAGIC_NUMBER + b"\x00" * 12
            target_pyc = target.with_suffix(".pyc")
            target_pyc.parent.mkdir(parents=True, exist_ok=True)
            target_pyc.write_bytes(pyc_header + raw)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

    print(f"[ok] Extracted to: {out_dir}")


def unpack_pyz(pyz_path: Path, out_dir: Path) -> None:
    """Unpack a PyInstaller PYZ archive into individual .pyc files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    data = pyz_path.read_bytes()
    # PYZ format: 4-byte magic 'PYZ\0', 4-byte pyc-magic, 4-byte toc_offset, 4 bytes reserved
    # Followed by payload, TOC at the end (marshalled list of (name, (ispkg, pos, len)))
    if data[:4] != b"PYZ\x00":
        raise RuntimeError(f"{pyz_path} is not a PYZ archive")
    pyc_magic = data[4:8]
    toc_offset = struct.unpack("!I", data[8:12])[0]
    toc = marshal.loads(data[toc_offset:])

    # toc is a dict: name -> (ispkg, pos, length)
    # In newer PyInstaller, toc is a dict; in older, a list of tuples.
    if isinstance(toc, dict):
        items = toc.items()
    else:
        items = [(k, v) for k, v in toc]

    import importlib.util
    header = importlib.util.MAGIC_NUMBER + b"\x00" * 12
    count = 0
    for name, meta in items:
        try:
            ispkg, pos, length = meta
        except Exception:
            continue
        blob = data[pos : pos + length]
        try:
            code_bytes = zlib.decompress(blob)
        except zlib.error as ex:
            print(f"[!] decompress failed for {name}: {ex}")
            continue

        # code_bytes is a marshalled code object
        parts = name.split(".")
        if ispkg:
            target = out_dir.joinpath(*parts) / "__init__.pyc"
        else:
            target = out_dir.joinpath(*parts).with_suffix(".pyc")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(header + code_bytes)
        count += 1
    print(f"[ok] PYZ {pyz_path.name}: wrote {count} .pyc files to {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: pyinstxtractor.py <exe> <out_dir>")
        print("       pyinstxtractor.py --pyz <pyz> <out_dir>")
        sys.exit(1)

    if sys.argv[1] == "--pyz":
        unpack_pyz(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        extract(Path(sys.argv[1]), Path(sys.argv[2]))
