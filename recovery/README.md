# Recovery Artifacts

This folder holds the **raw** outputs from the decompilation pipeline.
You shouldn't need to edit anything here — the cleaned source lives in
`../src/app.py`.

| File / folder | What it is |
|---|---|
| `app.disasm.txt` | Full bytecode disassembly of `app.pyc`, with all variable names, line numbers, and constant indices. ~12k lines. The **most reliable** source of truth. |
| `app.strings.txt` | Every string constant in the app, keyed by the function it appears in. Handy for grep-ing. |
| `app_reconstructed.py` | Combined: pycdc output interleaved with disassembly, one block per function. Used as the working file during hand-reconstruction. |
| `per_func/*.py` | pycdc attempts, one function per file (56 files). 42 succeeded, 14 failed. See `per_func/_SUMMARY.txt`. |
| `tools/` | The custom decompilation tooling (see below). |

## Tools

| Script | Purpose |
|---|---|
| `pyinstxtractor.py` | Inline PyInstaller archive extractor (no pip deps). |
| `transpile_314_to_313.py` | The **key piece**: lowers Python 3.14 bytecode to 3.13 so that pycdc can read it. Handles `LOAD_FAST_BORROW`, `LOAD_SMALL_INT`, `LOAD_COMMON_CONSTANT`, `POP_ITER`, `CALL_KW`, `TO_BOOL`, `FORMAT_SIMPLE`, `CONVERT_VALUE`, and the new `slice` constant type. Also translates inline cache slots between the two formats. |
| `dump_code.py` | Walks a `.pyc` and emits per-code-object disassembly + constants dump. |
| `decomp_per_func.py` | Runs pycdc on each code object in isolation (useful because pycdc sometimes segfaults on the whole module but succeeds per-function). |
| `combine_output.py` | Merges pycdc outputs + disassembly into `app_reconstructed.py`. |
| `opinfo_313.json` | Python 3.13's opcode map, captured for the transpiler. |

## Reproducing

```bash
# 1. Extract the exe
python3.14 tools/pyinstxtractor.py BSC-OPC-Agent.exe extracted/

# 2. Unpack PYZ
python3.14 tools/pyinstxtractor.py --pyz extracted/PYZ.pyz pyz_contents/

# 3. Transpile main app to 3.13-format
python3.14 tools/transpile_314_to_313.py extracted/app.pyc transpiled/app.pyc

# 4. Decompile per-function (your pycdc must be patched to accept the 3.14 pyc magic
#    or you can use the transpiled 3.13-stamped output from step 3)
python3.14 tools/decomp_per_func.py

# 5. Combine
python3.14 tools/combine_output.py
```
