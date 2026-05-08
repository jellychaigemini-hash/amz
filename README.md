# BSC Amazon OPC Agent OS — Source Recovery

This repository contains the **recovered source code** of
`BSC-OPC-Agent.exe` — a PyInstaller-packed Python 3.14 Flask application.

The source was recovered by reverse-engineering the frozen executable:

1. **Extract** the PyInstaller archive from `BSC-OPC-Agent.exe` to get raw
   `.pyc` files (done with a custom inline extractor because the network
   sandbox couldn't install pip packages).
2. **Unpack PYZ** to get the 748 bundled third-party module `.pyc` files.
3. **Transpile Python 3.14 bytecode to Python 3.13** so that
   [`pycdc`](https://github.com/zrax/pycdc) can read it. Python 3.14 is
   brand new; no decompiler supports it yet. I wrote a transpiler that:
   - Remaps Python 3.14 opcodes to 3.13 equivalents.
   - Lowers new opcodes (`LOAD_FAST_BORROW`, `POP_ITER`, `TO_BOOL`,
     `CALL_KW`, `FORMAT_SIMPLE`, etc.) to handlers pycdc understands.
   - Handles the new `LOAD_SMALL_INT`, `LOAD_COMMON_CONSTANT` constants.
   - Converts 3.14-only `slice` object constants into marshal-safe
     placeholders.
4. **Decompile function-by-function** with a patched pycdc (to get around
   3.14's new marshal type code `0x3A`).

## Folder Layout

```
recovery/
  app.disasm.txt           # Full bytecode disassembly of the main module (~12k lines)
  app.strings.txt          # Every string constant, keyed by function name
  app_reconstructed.py     # Combined pycdc output + disassembly per function
  per_func/                # Per-function decompilation attempts
  tools/                   # The decompilation tooling (transpiler, etc.)

src/                       # Hand-cleaned Python source (work in progress)
  app.py                   # The main Flask app
```

## Decompilation Success Rate

Out of 56 code objects in the main module:
- **42 succeeded** cleanly
- **14 failed or are partial** (mostly functions with complex try/except,
  slice operations, or exception groups)

For the failed ones, the disassembly in `app.disasm.txt` together with the
string constants in `app.strings.txt` is enough to read the original
intent and rewrite the function.

## What the App Does

From the strings and function names recovered, `BSC-OPC-Agent.exe` is a
local-first Flask web tool that helps Amazon sellers optimize listings:

- Accepts an ASIN + marketplace + product reference images.
- Calls Amazon "Rufus" + "COSMO" style expert AIs via MCP tools (sif,
  sorftime) to generate title/bullet/QA suggestions.
- Generates GPT Image-2 prompts for product photos, A+ content, and
  standalone site images (Apimart).
- Exports PSD files with overlays.
- Has a license activation system and a trial flow.
- UI served on `http://127.0.0.1:5173`.

## Credits

Recovery tooling (`recovery/tools/`) is original work for this project.
Bytecode-level work was made tractable thanks to
[pycdc](https://github.com/zrax/pycdc) by zrax (GPL-3.0).
