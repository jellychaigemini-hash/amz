"""
License verification and activation for BSC OPC Agent OS.
==========================================================
AES-256-GCM encrypted license keys with machine binding.
This module is compiled to .pyd by PyArmor during build.
"""
# Reconstructed from license_crypto.pyc (Python 3.14).
# Master secret, app id, and file names preserved verbatim from the
# original. Algorithm reconstructed from disassembly + strings.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants (faithful to original)
# ---------------------------------------------------------------------------

# Master secret. Used via SHA-256 to derive the AES-256-GCM key.
_MASTER_SECRET = b"BSC-OPC-License-Key-v1-2026-Production-Secure"
_LICENSE_KEY = hashlib.sha256(_MASTER_SECRET).digest()  # 32 bytes

# App ID is used as AAD (additional authenticated data) in GCM.
_APP_ID = b"BSC-OPC-Agent"

# License / trial file names (sit next to the .exe).
_LICENSE_FILE = "license.key"
_TRIAL_FILE = "trial_start.key"

# Trial length in days
_TRIAL_DAYS = 3


# ---------------------------------------------------------------------------
# Paths / machine identification
# ---------------------------------------------------------------------------

def _get_base_dir() -> Path:
    """Get the directory containing the .exe or .py."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _trial_file() -> Path:
    return _get_base_dir() / _TRIAL_FILE


def _get_machine_id() -> str:
    """Generate a machine fingerprint from hardware."""
    fingerprint = ""
    # Try MAC addresses via WMIC (Windows)
    try:
        result = subprocess.run(
            ["wmic", "nic", "where", "NetEnabled=True", "get", "MACAddress"],
            capture_output=True, timeout=5,
        )
        macs = [l.strip() for l in result.stdout.decode(errors="ignore").splitlines() if l.strip()]
        # First data line (not 'MACAddress' header)
        macs = [m for m in macs if m.lower() != "macaddress" and ":" in m]
        if macs:
            fingerprint += sorted(macs)[0].replace(":", "")
    except Exception:
        pass

    # Try disk serial
    try:
        result2 = subprocess.run(
            ["wmic", "diskdrive", "get", "SerialNumber"],
            capture_output=True, timeout=5,
        )
        serials = [l.strip() for l in result2.stdout.decode(errors="ignore").splitlines() if l.strip()]
        serials = [s for s in serials if s.lower() != "serialnumber"]
        if serials:
            disk = serials[0]
            if disk and disk != "00000000":
                fingerprint += "-" + disk
    except Exception:
        pass

    # Fallback via uuid.getnode() (cross-platform)
    if not fingerprint:
        fingerprint = str(uuid.getnode()) or "000000000000"

    # Final hash: first 16 hex chars of SHA-256
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def get_machine_id() -> str:
    """Public accessor for machine ID."""
    return _get_machine_id()


# ---------------------------------------------------------------------------
# AES-256-GCM primitives (with pure-Python fallback)
# ---------------------------------------------------------------------------

def _aes_gcm_encrypt(plaintext: bytes, aad: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce(12) + tag(16) + ciphertext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_LICENSE_KEY)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, aad)
    # cryptography appends the 16-byte tag to ciphertext; rearrange:
    ciphertext, tag = ct[:-16], ct[-16:]
    return nonce + tag + ciphertext


def _aes_gcm_decrypt(data: bytes, aad: bytes) -> bytes:
    """AES-256-GCM decrypt. Input: nonce(12) + tag(16) + ciphertext(N)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = data[:12]
    tag = data[12:28]
    ciphertext = data[28:]
    aesgcm = AESGCM(_LICENSE_KEY)
    # cryptography expects tag appended to ciphertext
    return aesgcm.decrypt(nonce, ciphertext + tag, aad)


def _pure_aes_ctr_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate AES-CTR keystream using SHA-256 as PRF."""
    result = bytearray()
    counter = 0
    while len(result) < length:
        block = hashlib.sha256(key + nonce + struct.pack(">Q", counter)).digest()
        result.extend(block)
        counter += 1
    return bytes(result[:length])


def _pure_aes_encrypt(plaintext: bytes) -> bytes:
    """Pure-Python AES-GCM-like encrypt using SHA-256 based CTR + HMAC."""
    nonce = os.urandom(12)
    keystream = _pure_aes_ctr_keystream(_LICENSE_KEY, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
    tag = hmac.new(
        _LICENSE_KEY, nonce + ciphertext + _APP_ID, hashlib.sha256
    ).digest()[:16]
    return nonce + tag + ciphertext


def _pure_aes_decrypt(data: bytes) -> bytes:
    """Pure-Python AES-GCM-like decrypt."""
    nonce = data[:12]
    tag = data[12:28]
    ciphertext = data[28:]
    expected_tag = hmac.new(
        _LICENSE_KEY, nonce + ciphertext + _APP_ID, hashlib.sha256
    ).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("License integrity check failed")
    keystream = _pure_aes_ctr_keystream(_LICENSE_KEY, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, keystream))


# ---------------------------------------------------------------------------
# License key generation / verification
# ---------------------------------------------------------------------------

def generate_license_key(machine_id: str, days: int) -> str:
    """Generate a compact encrypted license key."""
    app_hash = hashlib.sha256(_APP_ID).digest()[:8]
    mid_hash = hashlib.sha256(machine_id.encode()).digest()[:8]

    exp_ts = int(time.time()) + days * 86400
    payload = app_hash + mid_hash + struct.pack(">QI", exp_ts, days)

    try:
        encrypted = _aes_gcm_encrypt(payload, _APP_ID)
    except ImportError:
        encrypted = _pure_aes_encrypt(payload)

    # base32hex (uppercase, rstrip '=') then break into groups of 5
    encoded = base64.b32hexencode(encrypted).decode().rstrip("=")
    return "-".join(
        encoded[i:i + 5] for i in range(0, len(encoded), 5)
    )


def verify_and_save_license(key_input: str) -> dict:
    """Verify a license key. Returns {valid, exp_date, days_left, mid} or raises."""
    clean = key_input.strip().upper().replace("-", "").replace(" ", "")
    if len(clean) < 20:
        raise ValueError("密钥格式无效")

    # Re-pad for base32hex decode
    padding = (8 - len(clean) % 8) % 8
    clean += "=" * padding

    try:
        encrypted = base64.b32hexdecode(clean.encode())
    except Exception:
        raise ValueError("密钥解码失败")

    try:
        try:
            payload_bytes = _aes_gcm_decrypt(encrypted, _APP_ID)
        except ImportError:
            payload_bytes = _pure_aes_decrypt(encrypted)
    except Exception:
        raise ValueError("密钥验证失败")

    if len(payload_bytes) < 28:
        raise ValueError("密钥数据损坏")

    app_hash = hashlib.sha256(_APP_ID).digest()[:8]
    loaded_app = payload_bytes[:8]
    if loaded_app != app_hash:
        raise ValueError("密钥不适用于本软件")

    loaded_mid = payload_bytes[8:16]
    machine_id = _get_machine_id()
    expected_mid = hashlib.sha256(machine_id.encode()).digest()[:8]
    if loaded_mid != expected_mid:
        raise ValueError(f"密钥未绑定本机 (机器码: {machine_id[:8]})")

    exp_ts, days = struct.unpack(">QI", payload_bytes[16:28])
    now = int(time.time())
    if now > exp_ts:
        raise ValueError("密钥已过期，请联系客服续期")

    result = {
        "valid": True,
        "exp_date": _fmt_date(exp_ts),
        "days_left": max(0, (exp_ts - now) // 86400),
        "mid": machine_id,
        "grace": False,
    }
    save_license(key_input, result)
    return result


def save_license(key_input: str, result: dict) -> dict:
    """Verify and save license to file."""
    content = json.dumps({
        "key_hash": hashlib.sha256(key_input.encode()).hexdigest(),
        "mid": result.get("mid", ""),
        "exp_date": result.get("exp_date", ""),
        "days_left": result.get("days_left", 0),
        "saved_at": int(time.time()),
    })

    try:
        saved = _aes_gcm_encrypt(content.encode(), _APP_ID)
    except ImportError:
        saved = _pure_aes_encrypt(content.encode())

    license_path = _get_base_dir() / _LICENSE_FILE
    license_path.write_bytes(saved)
    return result


def check_license() -> dict:
    """Check if a valid license exists. Returns {valid, exp_date, days_left} or raises."""
    license_path = _get_base_dir() / _LICENSE_FILE
    if not license_path.exists():
        raise FileNotFoundError("未找到激活文件")

    try:
        saved = license_path.read_bytes()
        try:
            content_bytes = _aes_gcm_decrypt(saved, _APP_ID)
        except ImportError:
            content_bytes = _pure_aes_decrypt(saved)
        saved_data = json.loads(content_bytes.decode())
    except Exception:
        try:
            license_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("激活文件损坏，请重新激活")

    current_mid = _get_machine_id()
    if saved_data.get("mid") != current_mid:
        raise ValueError("机器环境变更，请重新激活")

    return {
        "valid": True,
        "message": "License OK",
        "mid": current_mid,
        "exp_date": saved_data.get("exp_date", ""),
        "days_left": saved_data.get("days_left", 0),
    }


# ---------------------------------------------------------------------------
# Trial
# ---------------------------------------------------------------------------

def start_trial() -> int:
    """Record trial start time. Returns remaining trial days."""
    tf = _trial_file()
    if not tf.exists():
        tf.write_text(str(int(time.time())))
    return trial_days_left()


def trial_days_left() -> int:
    """Get remaining trial days. -1 = expired, 0 = last day."""
    tf = _trial_file()
    if not tf.exists():
        return _TRIAL_DAYS
    try:
        started = int(tf.read_text().strip())
    except Exception:
        return _TRIAL_DAYS
    elapsed = (time.time() - started) / 86400
    remaining = max(-1, int((_TRIAL_DAYS - elapsed) + 0.5))
    return remaining


def has_trial_expired() -> bool:
    """True if trial has expired (no file = never started = not expired)."""
    tf = _trial_file()
    if not tf.exists():
        return False
    return trial_days_left() < 0


# ---------------------------------------------------------------------------
# Top-level flow & info
# ---------------------------------------------------------------------------

def check_and_activate() -> str:
    """Full license flow. Returns: 'active' | 'trial' | 'expired'"""
    try:
        check_license()
        return "active"
    except (FileNotFoundError, ValueError):
        pass
    tf = _trial_file()
    if not tf.exists():
        return "none"
    if has_trial_expired():
        return "expired"
    return "trial"


def get_license_info() -> dict:
    """Get full license info for display. Returns {status, exp_date, days_left, mid}."""
    status = check_and_activate()
    if status == "active":
        try:
            lf = _get_base_dir() / _LICENSE_FILE
            raw = lf.read_bytes()
            try:
                payload = _aes_gcm_decrypt(raw, _APP_ID)
            except ImportError:
                payload = _pure_aes_decrypt(raw)
            saved = json.loads(payload.decode())
            exp_date = saved.get("exp_date", "")
            days = saved.get("days_left", 0)
            return {
                "status": "active",
                "mid": saved.get("mid", "")[:8] + "—",
                "days_left": days,
                "exp_date": exp_date,
            }
        except Exception:
            return {"status": "expired"}
    if status == "trial":
        remaining = trial_days_left()
        return {
            "status": "trial",
            "days_left": remaining,
        }
    if status == "expired":
        return {"status": "expired"}
    return {"status": "none"}


def _fmt_date(timestamp) -> str:
    """Format timestamp to date string."""
    return time.strftime("%Y-%m-%d", time.localtime(int(timestamp)))


# ---------------------------------------------------------------------------
# Config value encryption (for api_keys etc.)
# ---------------------------------------------------------------------------

def encrypt_config_value(plaintext: str) -> str:
    """Encrypt a sensitive config value. Returns base64-encoded string."""
    if not plaintext:
        return ""
    aad = b"CONFIG"
    data = plaintext.encode("utf-8")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(_LICENSE_KEY)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, data, aad)
        blob = nonce + ct
    except ImportError:
        nonce = os.urandom(12)
        keystream = _pure_aes_ctr_keystream(_LICENSE_KEY, nonce, len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, keystream))
        tag = hmac.new(_LICENSE_KEY, nonce + ciphertext + aad, hashlib.sha256).digest()[:16]
        blob = nonce + tag + ciphertext
    encoded = base64.b64encode(blob).decode()
    return encoded


def decrypt_config_value(encoded: str) -> str:
    """Decrypt a sensitive config value. Returns plaintext string."""
    if not encoded:
        return ""
    aad = b"CONFIG"
    blob = base64.b64decode(encoded.encode())
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = blob[:12]
        ct = blob[12:]
        aesgcm = AESGCM(_LICENSE_KEY)
        data = aesgcm.decrypt(nonce, ct, aad)
    except ImportError:
        nonce = blob[:12]
        tag = blob[12:28]
        ciphertext = blob[28:]
        expected = hmac.new(
            _LICENSE_KEY, nonce + ciphertext + aad, hashlib.sha256
        ).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            return ""
        keystream = _pure_aes_ctr_keystream(_LICENSE_KEY, nonce, len(ciphertext))
        data = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return data.decode("utf-8", errors="replace")
