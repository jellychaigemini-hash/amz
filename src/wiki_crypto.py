"""
Wiki Knowledge Base — Encrypted Storage
========================================
All Wiki .md files are AES-256 encrypted at build time.
This module handles decryption at runtime via .pyd-protected key.

Build-time:  python wiki_crypto.py --encrypt    (encrypts Wiki/*.md → Wiki/*.enc)
Runtime:     from wiki_crypto import wiki_read   (decrypts and returns content)
"""
# Reconstructed from the original wiki_crypto.pyc (Python 3.14).
# Exact AES key + magic string preserved. Algorithm faithful to disassembly.

from __future__ import annotations

import hashlib
import struct
from pathlib import Path


WIKI_DIR = Path("Wiki")

# Master key is derived by SHA-256 of the banner below; the first 32 bytes
# become the AES-256 key. This matches the original constant _KEY.
_MASTER_SECRET = b"BSC-Wiki-OPC-OS-KnowledgeBase-Protection-2026"
_KEY = hashlib.sha256(_MASTER_SECRET).digest()  # 32 bytes

# 8-byte magic/prefix that makes all derived nonces start with "BSCWIKI1".
# The remaining 8 bytes come from a SHA-256 of the filepath.
_NONCE_PREFIX = b"BSCWIKI1"


def _derive_nonce(filepath: str) -> bytes:
    """Derive a deterministic 16-byte nonce for each file."""
    h = hashlib.sha256(filepath.encode()).digest()[:8]
    return _NONCE_PREFIX + h


def _aes_ctr_encrypt(data: bytes, nonce: bytes) -> bytes:
    """AES-256-CTR encrypt/decrypt (symmetric). Nonce must be 16 bytes."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(_KEY), modes.CTR(nonce))
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _aes_ctr_decrypt(data: bytes, nonce: bytes) -> bytes:
    """AES-256-CTR decrypt (same as encrypt since CTR is symmetric)."""
    return _aes_ctr_encrypt(data, nonce)


def _pure_aes_ctr(data: bytes, nonce: bytes) -> bytes:
    """Pure Python AES-CTR implementation using PyCryptodome-compatible approach.

    Falls back to simple XOR with key stream for environments without cryptography.
    """
    result = bytearray(len(data))
    counter = 0
    for i in range(0, len(data), 32):
        block_input = nonce + struct.pack(">Q", counter)
        keystream = hashlib.sha256(_KEY + block_input).digest()
        chunk = data[i:i + 32]
        for j in range(len(chunk)):
            result[i + j] = chunk[j] ^ keystream[j]
        counter += 1
    return bytes(result)


def encrypt_file(filepath: Path) -> Path:
    """Encrypt a single file. Returns path to .enc file."""
    data = filepath.read_bytes()
    nonce = _derive_nonce(str(filepath.relative_to(WIKI_DIR)))

    try:
        encrypted = _aes_ctr_encrypt(data, nonce)
    except ImportError:
        encrypted = _pure_aes_ctr(data, nonce)

    enc_path = filepath.with_suffix(filepath.suffix + ".enc")
    enc_path.write_bytes(encrypted)
    return enc_path


def decrypt_file(enc_path: Path, original_rel_path: str | None = None) -> bytes:
    """Decrypt a .enc file. Returns raw bytes."""
    data = enc_path.read_bytes()
    if original_rel_path is None:
        original_rel_path = enc_path.name.replace(".enc", "")

    # The original encrypt step was run on Windows, so the nonce was derived
    # from the backslash-separated relative path. On non-Windows machines we
    # need to try that spelling too, otherwise files in subdirectories fail
    # to decrypt with a slash-separated path.
    posix_rel = original_rel_path.replace("\\", "/")
    windows_rel = posix_rel.replace("/", "\\")

    for candidate in (windows_rel, posix_rel, enc_path.stem):
        nonce = _derive_nonce(candidate)
        try:
            plain = _aes_ctr_decrypt(data, nonce)
        except ImportError:
            plain = _pure_aes_ctr(data, nonce)
        # A successful decryption should start with printable bytes for .md/.json.
        if plain[:1] in (b"#", b"{", b"[", b" ", b"-", b"`") or b"\n" in plain[:100]:
            # Heuristic: if the first 100 bytes look like text/Markdown, accept.
            try:
                plain[:200].decode("utf-8")
                return plain
            except UnicodeDecodeError:
                continue
    # Fallback: return the last attempt (may be garbage, but we've tried all candidates).
    return plain


def wiki_read(relative_path: str) -> str:
    """Read a Wiki file by its relative path (e.g., '06-Rufus-Cosmo/algorithms.md').

    Supports both .enc (encrypted) and plain .md files.
    Returns decoded UTF-8 string.
    """
    full = WIKI_DIR / relative_path
    enc_path = full.with_suffix(full.suffix + ".enc")
    if enc_path.exists():
        data = decrypt_file(enc_path, relative_path)
        return data.decode("utf-8", errors="replace")
    if full.exists():
        return full.read_text(encoding="utf-8", errors="replace")
    return ""


def encrypt_all_wiki() -> None:
    """Encrypt all .md and .json files in Wiki directory. Run at build time."""
    count = 0
    for p in WIKI_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in (".md", ".json") and not p.name.endswith(".enc"):
            enc = encrypt_file(p)
            print(f"  Encrypted: {p} → {enc}")
            count += 1
    print(f"  Total: {count} files encrypted")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python wiki_crypto.py --encrypt")
        sys.exit(1)
    if sys.argv[1] == "--encrypt":
        encrypt_all_wiki()
    elif sys.argv[1] == "--test":
        for p in WIKI_DIR.rglob("*.enc"):
            rel = str(p.relative_to(WIKI_DIR)).replace(".enc", "")
            try:
                content = wiki_read(rel)
                print(f"  {rel}: {len(content)} chars")
            except Exception as e:
                print(f"  {rel}: ERROR {e}")
    else:
        print("Usage: python wiki_crypto.py --encrypt")
