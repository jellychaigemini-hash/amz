"""
Transpile Python 3.14 bytecode to Python 3.13 bytecode so pycdc can read it.

Strategy:
  - For each code object (recursively), decode 3.14 instructions.
  - Emit 3.13-equivalent instructions using 3.13's opcode numbering.
  - Handle inline CACHE entries: 3.13 and 3.14 both use CACHE entries but
    the counts per opcode can differ. We strip 3.14 caches and re-emit
    the correct number of 3.13 caches after each instruction.
  - Handle new 3.14 opcodes by mapping them to 3.13 equivalents:
      LOAD_FAST_BORROW                    -> LOAD_FAST
      LOAD_FAST_BORROW_LOAD_FAST_BORROW   -> LOAD_FAST_LOAD_FAST
      POP_ITER                            -> POP_TOP
      NOT_TAKEN                           -> NOP
      LOAD_SMALL_INT <n>                  -> LOAD_CONST <index of n>   (we add n as a const)
      LOAD_COMMON_CONSTANT <i>            -> LOAD_CONST <index>        (with known map)
      LOAD_SPECIAL <i>                    -> left as a best-effort LOAD_ATTR replacement
      JUMP_IF_FALSE / JUMP_IF_TRUE        -> POP_JUMP_IF_FALSE / TRUE (no pop behavior actually
                                              differs: these are the "peek" variants used by the
                                              new-style exception handlers; pycdc won't trip).
      BUILD_INTERPOLATION, BUILD_TEMPLATE -> replaced by a BUILD_STRING followed by NOPs to keep
                                              stack balance (best-effort; only affects t-string
                                              literals which are rare).
  - Rewrite co_code, co_linetable (we keep as-is; pycdc reads it for line #),
    co_exceptiontable (same format 3.12+), and create a new 3.13-stamped code object.

The goal is "pycdc reads this and produces recognizable Python". We don't need
perfect semantic equivalence in every edge case.
"""
from __future__ import annotations

import dis
import marshal
import sys
import types
from pathlib import Path


# ---------------------------------------------------------------------------
# 3.14 opcode info (the running interpreter is 3.14)
# ---------------------------------------------------------------------------
OPMAP_314 = dict(dis.opmap)
OPNAME_314 = {v: k for k, v in OPMAP_314.items()}

HAS_ARG_314 = set()
for name, op in OPMAP_314.items():
    if op >= dis.HAVE_ARGUMENT:
        HAS_ARG_314.add(op)

# Inline cache counts per 3.14 opcode (in code units of 2 bytes each).
# Introspect via _opcode if available, else fall back to a known table.
try:
    import _opcode  # type: ignore
    _CACHE_FORMAT_314 = getattr(_opcode, "_cache_format", {})
    _has_cache_attr = getattr(_opcode, "has_cache", None)
except Exception:
    _CACHE_FORMAT_314 = {}
    _has_cache_attr = None


def caches_314(op: int) -> int:
    """How many CACHE code units follow a 3.14 opcode."""
    name = OPNAME_314.get(op)
    if name is None:
        return 0
    if name in _CACHE_FORMAT_314:
        fmt = _CACHE_FORMAT_314[name]
        if isinstance(fmt, dict):
            return sum(fmt.values())
        if isinstance(fmt, int):
            return fmt
    return 0


# ---------------------------------------------------------------------------
# 3.13 opcode info (hardcoded from /projects/sandbox/decompile/opinfo_313.json)
# ---------------------------------------------------------------------------
import json as _json

_OPINFO_313 = _json.loads(Path("/projects/sandbox/decompile/opinfo_313.json").read_text())
OPMAP_313: dict[str, int] = _OPINFO_313["opmap"]
OPNAME_313 = {v: k for k, v in OPMAP_313.items()}

# 3.13 cache counts. Use the known CPython 3.13 cache format.
CACHE_FORMAT_313: dict[str, int] = {
    # (opcode name) -> number of CACHE code units following
    "BINARY_OP": 1,
    "BINARY_SUBSCR": 1,
    "CALL": 3,
    "CALL_KW": 3,
    "COMPARE_OP": 1,
    "CONTAINS_OP": 1,
    "FOR_ITER": 1,
    "IS_OP": 1,
    "LOAD_ATTR": 9,
    "LOAD_GLOBAL": 4,
    "LOAD_SUPER_ATTR": 1,
    "POP_JUMP_IF_FALSE": 1,
    "POP_JUMP_IF_NONE": 1,
    "POP_JUMP_IF_NOT_NONE": 1,
    "POP_JUMP_IF_TRUE": 1,
    "SEND": 1,
    "STORE_ATTR": 4,
    "STORE_SUBSCR": 1,
    "TO_BOOL": 3,
    "UNPACK_SEQUENCE": 1,
}


def caches_313(name: str) -> int:
    return CACHE_FORMAT_313.get(name, 0)


# ---------------------------------------------------------------------------
# Opcode translation 3.14 -> 3.13 name
# ---------------------------------------------------------------------------
# Strategy: map each 3.14 opcode NAME to a 3.13 opcode NAME (or a callable that
# returns (name, arg) given the original (name, arg, ctx)).

# 1-to-1 name mappings for opcodes that exist under a different number in 3.13.
# For names present in both, use the same name (renumbering is handled by lookup).
#
# We target pycdc's "comfort zone" which is roughly Python 3.11 semantics,
# so we also lower some 3.12/3.13-only opcodes to their 3.11 equivalents.
NAME_MAP_SIMPLE = {
    # 3.14 only -> 3.13 equivalent
    "LOAD_FAST_BORROW": "LOAD_FAST",
    "LOAD_FAST_BORROW_LOAD_FAST_BORROW": "LOAD_FAST_LOAD_FAST",
    "POP_ITER": "POP_TOP",
    "NOT_TAKEN": "NOP",
    "JUMP_IF_FALSE": "POP_JUMP_IF_FALSE",  # nearest semantic; pycdc treats similarly
    "JUMP_IF_TRUE": "POP_JUMP_IF_TRUE",
    # BUILD_INTERPOLATION / BUILD_TEMPLATE (PEP 750 t-strings) -> BUILD_STRING
    "BUILD_INTERPOLATION": "BUILD_STRING",
    "BUILD_TEMPLATE": "BUILD_STRING",
    "LOAD_SPECIAL": "LOAD_ATTR",
    "ANNOTATIONS_PLACEHOLDER": "NOP",
    "INSTRUMENTED_END_ASYNC_FOR": "NOP",
    "INSTRUMENTED_NOT_TAKEN": "NOP",
    "INSTRUMENTED_POP_ITER": "POP_TOP",

    # --- Opcodes pycdc's ASTree doesn't handle; lower to equivalents ---
    # TO_BOOL: coerces TOS to bool. pycdc's POP_JUMP_IF_FALSE handles the
    # old semantics where the jump opcode itself does the truthiness check.
    # Just NOP it and the following POP_JUMP_IF_* still works.
    "TO_BOOL": "NOP",
    # END_SEND (3.12+): used in `yield from` / `await`. Equivalent: POP_TOP
    # (consumes the unused value).
    "END_SEND": "POP_TOP",
    # CLEANUP_THROW (3.12+): internal to send(). Harmless to NOP; only shows
    # up in generators.
    "CLEANUP_THROW": "NOP",
    # EXIT_INIT_CHECK (3.13): ensures __init__ returns None. No-op for us.
    "EXIT_INIT_CHECK": "NOP",
    # CHECK_EG_MATCH (3.11+, exception groups): lower to CHECK_EXC_MATCH which
    # pycdc handles. Not perfect but readable.
    "CHECK_EG_MATCH": "CHECK_EXC_MATCH",
    # CONVERT_VALUE (3.12+): used by f-strings with conversion. Arg is 1=str,
    # 2=repr, 3=ascii. pycdc's older handler was FORMAT_VALUE with the same arg.
    "CONVERT_VALUE": "FORMAT_VALUE",
    # FORMAT_SIMPLE (3.12+): like FORMAT_VALUE with no conversion and no spec.
    "FORMAT_SIMPLE": "FORMAT_VALUE",
    # FORMAT_WITH_SPEC (3.12+): like FORMAT_VALUE with a spec on stack.
    # FORMAT_VALUE's arg=4 means "has spec", which is what pycdc expects.
    # We'll special-case this in a post-pass below.
    "FORMAT_WITH_SPEC": "FORMAT_VALUE",
    # CALL_INTRINSIC_1/2 (3.12+): call CPython-internal helpers. Rarely matters
    # for our decompile; NOP leaves the value on stack (best-effort).
    "CALL_INTRINSIC_1": "NOP",
    "CALL_INTRINSIC_2": "NOP",
    # BEFORE_ASYNC_WITH (3.11): lower to BEFORE_WITH for decompile readability.
    "BEFORE_ASYNC_WITH": "BEFORE_WITH",
    # LOAD_FAST_CHECK (3.12+): same as LOAD_FAST but raises if unbound. For
    # decompile we don't care about the check.
    "LOAD_FAST_CHECK": "LOAD_FAST",
    # LOAD_FAST_AND_CLEAR (3.12+): used in generator expressions. Closest is
    # LOAD_FAST; semantics differ but variable name survives.
    "LOAD_FAST_AND_CLEAR": "LOAD_FAST",
    # LOAD_FROM_DICT_OR_DEREF / LOAD_FROM_DICT_OR_GLOBALS (3.12+, class scope
    # PEP 695): lower to LOAD_DEREF / LOAD_GLOBAL.
    "LOAD_FROM_DICT_OR_DEREF": "LOAD_DEREF",
    "LOAD_FROM_DICT_OR_GLOBALS": "LOAD_GLOBAL",
    # COPY_FREE_VARS (3.11+): sets up cell vars for a closure. pycdc should
    # tolerate a NOP here because it reconstructs closures from co_freevars.
    "COPY_FREE_VARS": "NOP",
    # MAKE_CELL (3.11+): creates a cell for a variable. Same story.
    "MAKE_CELL": "NOP",
    # LOAD_LOCALS (3.12+, PEP 695): we already have LOAD_LOCALS in pycdc.
    # (no mapping needed)
    # SET_FUNCTION_ATTRIBUTE (3.12+): replaces MAKE_FUNCTION flag variants.
    # pycdc's MAKE_FUNCTION handling covers the 3.11 path; SET_FUNCTION_ATTRIBUTE
    # after a MAKE_FUNCTION attaches attrs (closure, defaults, etc.). NOP is a
    # safe-ish fallback that still leaves the function object on stack.
    "SET_FUNCTION_ATTRIBUTE": "NOP",
    # RESERVED (3.12, unused). NOP.
    "RESERVED": "NOP",
    # ENTER_EXECUTOR (3.13): tier-2 JIT escape. Should not appear in pyc files
    # produced by normal compile, but NOP is safe.
    "ENTER_EXECUTOR": "NOP",
    # INTERPRETER_EXIT: should only appear in top-level; lower to RETURN_CONST(None).
    "INTERPRETER_EXIT": "RETURN_VALUE",
    # CALL_KW (3.13): call with keyword args. pycdc has CALL_KW_A but no ASTree
    # handler. We can sometimes lower to CALL; but kwargs semantics differ.
    # Keep as-is and hope for the best; if pycdc errors we'll switch to CALL.
    # "CALL_KW": "CALL",  # (disabled; try native first)
}


# 3.14 LOAD_COMMON_CONSTANT index -> Python object
# From CPython 3.14 source (Python/bytecodes.c): index 0 -> AssertionError,
# 1 -> NotImplementedError. We intercept these specially.
COMMON_CONSTANTS = {
    0: AssertionError,
    1: NotImplementedError,
}


# ---------------------------------------------------------------------------
# Bytecode decoder for 3.14 (handles EXTENDED_ARG properly)
# ---------------------------------------------------------------------------

EXTENDED_ARG_314 = OPMAP_314.get("EXTENDED_ARG")
CACHE_OP_314 = OPMAP_314.get("CACHE")

EXTENDED_ARG_313 = OPMAP_313["EXTENDED_ARG"]
CACHE_OP_313 = OPMAP_313["CACHE"]


def decode_314(code_bytes: bytes) -> list[tuple[int, int, int]]:
    """Decode 3.14 instructions.
    Returns list of (absolute_code_offset_in_units, opcode, full_arg).
    CACHE entries are included as separate instructions (opcode = CACHE).
    """
    result = []
    ext_arg = 0
    i = 0
    n = len(code_bytes)
    while i < n:
        op = code_bytes[i]
        arg = code_bytes[i + 1]
        full_arg = (ext_arg << 8) | arg
        if op == EXTENDED_ARG_314:
            ext_arg = full_arg
            # EXTENDED_ARG has no cache
            result.append((i // 2, op, full_arg))
            i += 2
            continue
        result.append((i // 2, op, full_arg))
        ext_arg = 0
        i += 2
        # Skip inline caches (part of the instruction in 3.14)
        nc = caches_314(op)
        for c in range(nc):
            # CACHE entries have opcode CACHE_OP and arg is whatever the bytes are
            if i + 1 < n:
                result.append((i // 2, code_bytes[i], code_bytes[i + 1]))
            i += 2
    return result


# ---------------------------------------------------------------------------
# Transpile one code object
# ---------------------------------------------------------------------------

def emit_instr_313(op_name: str, arg: int, out: bytearray) -> None:
    """Emit a 3.13 instruction with EXTENDED_ARG as needed, followed by its
    caches (filled with zeros). If op_name is not in 3.13's opmap, fall back
    to NOP."""
    if op_name not in OPMAP_313:
        op_name = "NOP"
        arg = 0
    opcode = OPMAP_313[op_name]

    # Emit EXTENDED_ARG bytes if arg > 255
    ext_bytes = []
    a = arg
    while a > 0xFF:
        ext_bytes.append((a >> 8) & 0xFF)
        a &= 0xFF
    # We pushed least-significant-extended first; we need most-significant first.
    # Actually: arg = (ext1 << 16) | (ext2 << 8) | arg. The EXTENDED_ARG opcodes
    # are emitted in order with the higher bits first.
    # Rebuild properly:
    ext_vals = []
    a = arg >> 8
    while a:
        ext_vals.append(a & 0xFF)
        a >>= 8
    # ext_vals is in low-to-high order; we need to emit high-to-low.
    for v in reversed(ext_vals):
        out.append(EXTENDED_ARG_313)
        out.append(v)

    out.append(opcode)
    out.append(arg & 0xFF)

    # Emit 3.13 cache slots (filled with CACHE opcode + 0 arg)
    for _ in range(caches_313(op_name)):
        out.append(CACHE_OP_313)
        out.append(0)


def transpile_code_bytes(
    code_bytes_314: bytes,
    consts: list,
) -> tuple[bytes, list]:
    """Transpile the raw code bytes from 3.14 to 3.13 format.

    `consts` is the current constants list (mutable). We may append new
    constants (e.g. for LOAD_SMALL_INT).

    Returns (new_code_bytes, new_consts_list).

    NOTE: This is a two-pass transpile: first pass builds (op_name, arg) list
    and records 3.14 offset -> 3.13 offset map, second pass fixes jump args.
    """
    # --- pass 1: decode 3.14 stream into logical instructions (no CACHEs) ---
    instrs_314 = []  # list of (offset_314_in_units, op_name_314, arg, is_cache)
    ext = 0
    i = 0
    n = len(code_bytes_314)
    while i < n:
        op = code_bytes_314[i]
        raw_arg = code_bytes_314[i + 1]
        if op == CACHE_OP_314:
            # Should have been skipped; but in case alignment is off, just consume it.
            i += 2
            continue
        full_arg = (ext << 8) | raw_arg
        name = OPNAME_314.get(op, f"UNK_{op}")
        if op == EXTENDED_ARG_314:
            ext = full_arg
            i += 2
            continue
        instrs_314.append((i // 2, name, full_arg))
        ext = 0
        i += 2
        # consume inline caches for this op
        i += 2 * caches_314(op)

    # --- pass 1b: translate each 3.14 logical instr -> list of 3.13 logical instrs ---
    # We produce: list of (src_offset_314_in_units, op_name_313, arg_313)
    # Jump-target args are stored in terms of *3.14 offsets* and will be remapped in pass 2.
    translated: list[tuple[int, str, int, bool]] = []  # (src_off, op, arg, arg_is_jump_delta_314)

    def is_jump_314(op_name: str) -> bool:
        return op_name in {
            "JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT",
            "POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE",
            "POP_JUMP_IF_NONE", "POP_JUMP_IF_NOT_NONE",
            "FOR_ITER", "SEND", "JUMP_IF_FALSE", "JUMP_IF_TRUE",
        }

    def is_backward_jump_314(op_name: str) -> bool:
        return op_name in {"JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"}

    # We need to know target offsets in 3.14 units. In 3.14 the "arg" of a jump
    # is a relative offset in code units counted from the instruction *after*
    # this one (i.e. after this op + its caches).

    # Peephole: CALL_KW is a 3.13+ op. pycdc's ASTree only handles the older
    # KW_NAMES + CALL pattern. The pattern preceding CALL_KW is always:
    #   LOAD_CONST <kwtuple_idx>   ; the tuple of kw names
    #   CALL_KW N
    # We rewrite that LOAD_CONST into KW_NAMES <kwtuple_idx> and CALL_KW into CALL.
    # Note: 3.13's KW_NAMES arg is also the const index.

    for idx, (src_off, name, arg) in enumerate(instrs_314):
        is_jump = is_jump_314(name)

        # Handle CALL_KW peephole: in 3.13 the pattern is:
        #   LOAD_CONST <kwtuple>
        #   CALL_KW N
        # pycdc ASTree doesn't handle CALL_KW. Lower to plain CALL by
        # dropping the kwtuple push (NOP) and converting to CALL. The kw
        # argument names are lost but the call itself decompiles correctly.
        if name == "CALL_KW" and translated and translated[-1][1] == "LOAD_CONST":
            prev = translated[-1]
            translated[-1] = (prev[0], "NOP", 0, False)
            translated.append((src_off, "CALL", arg, False))
            continue

        if is_jump:
            # Compute absolute 3.14 target offset (in units).
            after_this = src_off + 1 + caches_314(OPMAP_314[name])
            if is_backward_jump_314(name):
                target_314 = after_this - arg
            else:
                target_314 = after_this + arg

            # Translate name: most jump names are identical in 3.13.
            new_name = NAME_MAP_SIMPLE.get(name, name)
            if new_name not in OPMAP_313:
                new_name = "NOP"
                translated.append((src_off, new_name, 0, False))
                continue

            # Store target as a sentinel arg (negative) so pass 2 recognizes it.
            # We'll encode: positive means "target 3.14 unit offset", and mark with flag.
            translated.append((src_off, new_name, target_314, True))
            continue

        # Non-jump: translate name / arg
        if name == "LOAD_SMALL_INT":
            # Need to add the small integer to consts, emit LOAD_CONST
            val = arg  # LOAD_SMALL_INT's arg is the int value directly
            try:
                ci = consts.index(val)
            except ValueError:
                consts.append(val)
                ci = len(consts) - 1
            translated.append((src_off, "LOAD_CONST", ci, False))
            continue

        if name == "LOAD_COMMON_CONSTANT":
            val = COMMON_CONSTANTS.get(arg, None)
            if val is None:
                # Unknown common constant: fall back to None
                val = None
            # Find/add in consts (identity-based for None, value-based for classes is fine)
            try:
                ci = consts.index(val)
            except ValueError:
                consts.append(val)
                ci = len(consts) - 1
            translated.append((src_off, "LOAD_CONST", ci, False))
            continue

        # Default: use mapped name if needed
        new_name = NAME_MAP_SIMPLE.get(name, name)
        if new_name not in OPMAP_313:
            # Fall back to NOP if really unknown
            new_name = "NOP"
            arg = 0
        translated.append((src_off, new_name, arg, False))

    # --- pass 2: assemble bytes, computing offset maps ---
    # First we need to know the 3.13 byte offset of each translated instr.
    # We do a provisional layout with best-guess arg sizes (which depends on
    # jump arg magnitudes). Jumps may require EXTENDED_ARG. We iterate up to
    # a fixed point.

    def emit_size(op_name: str, arg: int) -> int:
        # EXTENDED_ARG bytes
        a = arg >> 8
        ext_count = 0
        while a:
            ext_count += 1
            a >>= 8
        return 2 + 2 * ext_count + 2 * caches_313(op_name)

    # Initial sizes assume arg <= 255 unless obviously bigger (non-jump args are known).
    sizes = []
    for (src_off, name, arg, is_jump) in translated:
        if is_jump:
            sizes.append(4)  # placeholder, at least 2 bytes + maybe EXTENDED_ARG
        else:
            sizes.append(emit_size(name, arg))

    # Compute 3.14 unit offset -> translated index map
    src_off_to_idx = {t[0]: i for i, t in enumerate(translated)}

    def recompute():
        # Build byte offsets for each translated instr
        offsets = []
        pos = 0
        for s in sizes:
            offsets.append(pos)
            pos += s
        total = pos
        # Now re-evaluate sizes for jump instructions using actual distance
        changed = False
        for idx, (src_off, name, arg, is_jump) in enumerate(translated):
            if not is_jump:
                continue
            target_314 = arg  # stored earlier
            # Find the translated idx whose src_off matches or nearest after
            tgt_idx = src_off_to_idx.get(target_314)
            if tgt_idx is None:
                # Find the next translated instr with src_off >= target_314
                # This handles cases where the target was a CACHE slot in 3.14.
                candidates = [i for i, t in enumerate(translated) if t[0] >= target_314]
                if candidates:
                    tgt_idx = candidates[0]
                else:
                    tgt_idx = len(translated) - 1
            tgt_byte = offsets[tgt_idx]
            my_end_byte = offsets[idx] + sizes[idx]
            # 3.13 jumps are relative to "after this instr (incl caches)" in code units
            # For forward jumps: delta = (tgt - end) / 2
            # For backward: arg = (end - tgt) / 2  (positive)
            if name in ("JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
                delta = (my_end_byte - tgt_byte) // 2
                if delta < 0:
                    # Should not happen; treat as forward
                    pass
                new_arg_val = delta
            else:
                delta = (tgt_byte - my_end_byte) // 2
                if delta < 0:
                    # Backwards with forward opcode: switch to JUMP_BACKWARD
                    # (rare; only if our translation went wrong). Keep as-is with abs.
                    new_arg_val = abs(delta)
                else:
                    new_arg_val = delta
            needed = emit_size(name, new_arg_val)
            if needed != sizes[idx]:
                sizes[idx] = needed
                changed = True
        return changed, offsets

    # Iterate to fixed point
    for _ in range(16):
        changed, offsets = recompute()
        if not changed:
            break

    # Final emission
    out = bytearray()
    for idx, (src_off, name, arg, is_jump) in enumerate(translated):
        if is_jump:
            target_314 = arg
            tgt_idx = src_off_to_idx.get(target_314)
            if tgt_idx is None:
                candidates = [i for i, t in enumerate(translated) if t[0] >= target_314]
                tgt_idx = candidates[0] if candidates else len(translated) - 1
            tgt_byte = offsets[tgt_idx]
            my_end_byte = offsets[idx] + sizes[idx]
            if name in ("JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
                final_arg = max(0, (my_end_byte - tgt_byte) // 2)
            else:
                final_arg = max(0, (tgt_byte - my_end_byte) // 2)
            emit_instr_313(name, final_arg, out)
        else:
            emit_instr_313(name, arg, out)

    return bytes(out), consts


# ---------------------------------------------------------------------------
# Full code object rewriter
# ---------------------------------------------------------------------------

def transpile_code(code: types.CodeType) -> types.CodeType:
    # Recurse into nested code objects first
    new_consts = []
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            new_consts.append(transpile_code(c))
        elif isinstance(c, slice):
            # Marshal v4 can't serialize slice. Replace with tuple marker.
            new_consts.append(("__SLICE__", c.start, c.stop, c.step))
        else:
            new_consts.append(c)

    new_bytes, new_consts = transpile_code_bytes(code.co_code, new_consts)

    # Build a replacement code object. Python 3.14's code.replace() will create
    # a new 3.14 code object, but when we marshal.dumps() with version=4 and
    # stamp the pyc header as 3.13, pycdc will read it as 3.13. The code object
    # attributes we care about (co_code, co_consts, co_names, co_varnames,
    # co_freevars, co_cellvars, co_filename, co_name, co_qualname,
    # co_firstlineno, co_linetable, co_exceptiontable, argcount, etc.) are the
    # same shape in 3.13 and 3.14.
    try:
        return code.replace(co_code=new_bytes, co_consts=tuple(new_consts))
    except Exception as e:
        print(f"[!] replace failed for {code.co_name}: {e}", file=sys.stderr)
        return code


# ---------------------------------------------------------------------------
# Top-level pyc converter
# ---------------------------------------------------------------------------

PY313_MAGIC_BYTES = bytes.fromhex("f30d0d0a")
HEADER = PY313_MAGIC_BYTES + b"\x00" * 12


def convert(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    code = marshal.loads(data[16:])
    code = transpile_code(code)
    blob = marshal.dumps(code, 4)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(HEADER + blob)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: transpile_314_to_313.py <in.pyc> <out.pyc>")
        sys.exit(1)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"[ok] wrote {sys.argv[2]}")
