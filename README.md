# BSC Amazon OPC Agent OS — Source Recovery

This repository contains the **fully recovered source code** of
`BSC-OPC-Agent.exe` — a PyInstaller-packed Python 3.14 Flask application.

The source was recovered by reverse-engineering the frozen executable,
including all private modules that were packed inside the PYZ archive.

## What's recovered

All 6 Python modules from the original app:

| Module | Purpose | Lines | Status |
|---|---|---|---|
| `src/app.py` | Main Flask web app, API routes, job queue | ~1180 | Running, verified |
| `src/expert_suggestions.py` | Rufus/COSMO expert suggestion engine (title/bullets/QA/selling points/insights) | ~860 | Running, verified |
| `src/rufus_cosmo.py` | COSMO/Rufus/GEO algorithm integration layer | ~320 | Running, verified |
| `src/license_crypto.py` | AES-256-GCM license system with machine binding | ~400 | Roundtrip verified |
| `src/wiki_crypto.py` | AES-256-CTR encryption for Wiki knowledge base | ~170 | **Decrypts all `.md.enc` files** |
| `src/activate_ui.py` | Tkinter activation dialog | ~200 | Compiles, follows original UI |

**Total: ~3,130 lines of Python across 6 modules.**

## How it was done

Python 3.14 was released so recently that no existing decompiler
(uncompyle6 / decompyle3 / pycdc) supports it yet. I wrote a custom
bytecode transpiler to lower 3.14 bytecode to 3.13 so that
[`pycdc`](https://github.com/zrax/pycdc) could read it:

1. **Extract** the PyInstaller archive from `BSC-OPC-Agent.exe` to get raw
   `.pyc` files (done with a custom inline extractor because the network
   sandbox couldn't install pip packages).
2. **Unpack PYZ** to get the 748 bundled third-party module `.pyc` files.
3. **Transpile Python 3.14 bytecode to Python 3.13** so that `pycdc` can read
   it. The transpiler:
   - Remaps Python 3.14 opcodes to 3.13 equivalents (the whole table was
     renumbered in 3.14).
   - Lowers new 3.14 opcodes (`LOAD_FAST_BORROW`, `POP_ITER`, `TO_BOOL`,
     `CALL_KW`, `FORMAT_SIMPLE`, etc.) to handlers pycdc understands.
   - Handles the new `LOAD_SMALL_INT`, `LOAD_COMMON_CONSTANT` constants.
   - Converts 3.14-only `slice` object constants into marshal-safe
     placeholders.
   - Blanks the exception table (stale byte offsets after re-layout would
     cause CPython to corrupt the heap during marshal.dumps).
4. **Decompile function-by-function** with subprocess isolation so a
   pycdc crash on one function doesn't kill the whole pipeline.
5. **Hand-reconstruct** each function using the pycdc output + full
   disassembly + every string constant as reference.

## Key findings

- **Wiki encryption is fully reverse-engineered**. The master key is
  `SHA-256("BSC-Wiki-OPC-OS-KnowledgeBase-Protection-2026")`. Nonces use
  `"BSCWIKI1" + SHA-256(filepath)[:8]`. Note that the original was packed
  on Windows, so nonces were derived from backslash-separated paths; the
  reconstructed `wiki_read()` tries both Windows-style and POSIX-style
  spellings automatically.

- **License crypto is fully reverse-engineered**. AES-256-GCM with the key
  `SHA-256("BSC-OPC-License-Key-v1-2026-Production-Secure")`. License
  keys encode a 28-byte payload: `app_hash(8) + machine_hash(8) + exp_ts(Q) + days(I)`,
  encrypted with the master key as key and `b"BSC-OPC-Agent"` as AAD,
  then base32hex-encoded and dash-grouped in 5-char chunks.

- **Machine binding** hashes MAC + disk serial via WMIC on Windows, falls
  back to `uuid.getnode()` elsewhere.

- **App uses Flask + werkzeug + psd_tools + Pillow + cryptography**,
  listens on `127.0.0.1:5173`, stores work under `input/`, `output/`,
  `prompts/`.

## Folder layout

```
src/                          # Clean, runnable Python source (the "real" deliverable)
  app.py                      # Flask web app
  expert_suggestions.py       # Rufus/COSMO expert logic
  rufus_cosmo.py              # Algorithm integration layer
  license_crypto.py           # License system
  wiki_crypto.py              # Wiki encryption
  activate_ui.py              # Tkinter activation dialog

recovery/                     # Raw decompilation artifacts (source of truth)
  app.disasm.txt              # Bytecode disassembly of the main module
  app.strings.txt             # All string constants
  app_reconstructed.py        # Combined pycdc output + disasm per function
  per_func/                   # pycdc output for each of 56 app.py code objects
  modules/
    expert_suggestions/       # disasm + strings + per_func for each module
    rufus_cosmo/
    license_crypto/
    wiki_crypto/
    activate_ui/
  tools/                      # All decompilation tooling
    pyinstxtractor.py         # Inline PyInstaller archive extractor
    transpile_314_to_313.py   # The custom 3.14 → 3.13 bytecode transpiler
    dump_code.py              # pyc → disasm + strings dumper
    decomp_per_func.py        # Per-function pycdc driver for app.pyc
    recover_all.py            # Same for expert/rufus/license/wiki/activate
    recover_expert.py         # Subprocess-isolated driver (CPython 3.14 has
                              #   a marshal heap bug that crashes the whole
                              #   recovery run on one specific function)
    find_bad_const.py         # Finds unmarshallable 3.14 constants
    combine_output.py         # Merges pycdc + disasm into one big file
    opinfo_313.json           # Python 3.13's opcode map
```

## Running

```bash
pip install flask cryptography psd_tools pillow werkzeug

# Put your config.json next to src/app.py:
echo '{"apimart": {"api_key": "YOUR_KEY"}}' > src/config.json

python src/app.py    # opens http://127.0.0.1:5173
```

## Caveats / differences from the original

- The bullet-suggestion Chinese templates use the exact phrasing found in
  the bytecode, but the template branching (which phrase per bullet) is
  the best reconstruction from disassembly; the exact per-field
  conditional logic in `_generate_bullet_suggestion` may differ in
  cosmetic ways from the original.
- `api_export_psd` depends on specific fonts bundled in `_internal/`; the
  reconstruction uses Pillow's default text renderer as a fallback.
- The CPython 3.14 opcode for `BUILD_INTERPOLATION` / `BUILD_TEMPLATE`
  (PEP 750 t-strings) is lowered to `BUILD_STRING`. If the original code
  used t-string literals, they decompile as f-strings.
- The `_internal/` runtime directory (~51 MB of Python DLLs + C extensions)
  is NOT included here; it's regenerated by PyInstaller at build time.

## Credits

Recovery tooling (`recovery/tools/`) is original work for this project.
Bytecode-level decompilation was made tractable thanks to
[pycdc](https://github.com/zrax/pycdc) by zrax (GPL-3.0).
