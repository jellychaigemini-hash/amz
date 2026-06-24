"""
Offline license-key generator for BSC OPC Agent OS.

Usage:
    python generate_license.py <machine_id> <days>

Example:
    # Get the machine_id from the activation dialog in the running app, then:
    python generate_license.py 44a1638c8ae4424a 30

The output key is pasted into the activation dialog. Verification happens
locally — no network required.

This works because src/license_crypto.py holds the master secret
'BSC-OPC-License-Key-v1-2026-Production-Secure' (recovered from the original
binary). The generated key is an AES-256-GCM encrypted payload bound to
the target machine's fingerprint.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable
THIS = Path(__file__).resolve()
SRC = THIS.parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

try:
    from license_crypto import generate_license_key, get_machine_id
except ImportError as e:
    print(f"Error: couldn't import license_crypto. Expected at {SRC / 'license_crypto.py'}")
    print(f"Detail: {e}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) == 1:
        # No args -> generate a 365-day key for THIS machine (quick dev flow)
        mid = get_machine_id()
        days = 365
        print(f"(no args) generating key for this machine, valid {days} days")
    elif len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    elif len(sys.argv) == 3:
        mid = sys.argv[1].strip()
        try:
            days = int(sys.argv[2])
        except ValueError:
            print(f"Error: <days> must be an integer (got {sys.argv[2]!r})")
            sys.exit(2)
    else:
        print(__doc__)
        sys.exit(2)

    if not mid:
        print("Error: machine_id is empty")
        sys.exit(2)
    if days < 1 or days > 3650:
        print(f"Error: days must be 1..3650 (got {days})")
        sys.exit(2)

    key = generate_license_key(mid, days)

    print()
    print("  machine_id :", mid)
    print("  days       :", days)
    print()
    print("  License key:")
    print()
    print("    " + key)
    print()
    print("  Paste this into the activation dialog in the running app.")


if __name__ == "__main__":
    main()
