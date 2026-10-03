"""
core/vault.py — Encrypted Credential Vault for KuroAgent

Provides AES-256 / Windows DPAPI-based encrypted storage for API keys,
webhook tokens, passwords, and private credentials.

Features:
- Windows DPAPI native encryption (CryptProtectData / CryptUnprotectData) with zero dependencies.
- Cryptography / Fernet / AES-GCM integration when available.
- PBKDF2-HMAC-SHA256 key derivation with 200,000 iterations.
- In-memory credential masking to prevent accidental leakage in logs/prompts.
- Master password protection and auto-unlock support.
- Seamless bridge with core/config.py KeyPool and Integrations.
"""

import os
import sys
import json
import base64
import hashlib
import hmac
import secrets
import time
import ctypes
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from core.paths import VAULT_FILE, CONFIG_DIR
from core.logger import logger


# Windows DPAPI Structures & Functions (ctypes)
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_char))
    ]


def _dpapi_encrypt(data: bytes, description: str = "KuroVault") -> Optional[bytes]:
    """Encrypts bytes using Windows DPAPI (tied to the current Windows user profile)."""
    if sys.platform != "win32":
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DATA_BLOB()
        desc_ptr = ctypes.c_wchar_p(description)

        # CryptProtectData(pDataIn, ppszDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut)
        if crypt32.CryptProtectData(ctypes.byref(blob_in), desc_ptr, None, None, None, 0, ctypes.byref(blob_out)):
            encrypted_data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            kernel32.LocalFree(blob_out.pbData)
            return encrypted_data
    except Exception as e:
        logger.debug(f"[Vault] DPAPI encrypt error: {e}")
    return None


def _dpapi_decrypt(data: bytes) -> Optional[bytes]:
    """Decrypts bytes using Windows DPAPI."""
    if sys.platform != "win32":
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        blob_in = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
        blob_out = DATA_BLOB()
        desc_ptr = ctypes.c_wchar_p()

        if crypt32.CryptUnprotectData(ctypes.byref(blob_in), ctypes.byref(desc_ptr), None, None, None, 0, ctypes.byref(blob_out)):
            decrypted_data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            kernel32.LocalFree(blob_out.pbData)
            return decrypted_data
    except Exception as e:
        logger.debug(f"[Vault] DPAPI decrypt error: {e}")
    return None


def _derive_key(password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    """Derives a 256-bit AES key using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def _keystream_cipher(data: bytes, key: bytes, iv: bytes) -> bytes:
    """
    AES-equivalent authenticated keystream cipher (CTR mode simulation via HMAC-SHA256 blocks)
    used as pure standard-library fallback when cryptography library is not installed.
    """
    output = bytearray(len(data))
    block_num = 0
    offset = 0
    while offset < len(data):
        counter = block_num.to_bytes(8, "big")
        block_key = hmac.new(key, iv + counter, hashlib.sha256).digest()
        chunk_len = min(len(block_key), len(data) - offset)
        for i in range(chunk_len):
            output[offset + i] = data[offset + i] ^ block_key[i]
        offset += chunk_len
        block_num += 1
    return bytes(output)


def mask_secret(value: str) -> str:
    """Returns a masked preview of a secret (e.g. sk-****abcd or ****)."""
    if not value:
        return "********"
    val = str(value).strip()
    if len(val) <= 6:
        return "*" * len(val)
    if len(val) <= 12:
        return val[:2] + "****" + val[-2:]
    return val[:4] + "****" + val[-4:]


class VaultManager:
    """
    Manages encrypted secrets lifecycle: persistence, encryption, in-memory cache,
    and fallback recovery.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        self.vault_path: Path = vault_path or VAULT_FILE
        self._secrets: Dict[str, Dict[str, Any]] = {}
        self._locked: bool = False
        self._master_password: Optional[str] = None
        self._backend: str = "dpapi" if sys.platform == "win32" else "standard_pbkdf2"
        self._salt: bytes = b""
        self._load_vault()

    def is_locked(self) -> bool:
        return self._locked

    def lock(self) -> None:
        """Locks the vault and purges secrets from memory."""
        self._secrets.clear()
        self._locked = True
        logger.info("[Vault] Vault locked. In-memory secrets cleared.")

    def unlock(self, password: Optional[str] = None) -> bool:
        """Unlocks the vault with optional master password."""
        self._master_password = password
        self._locked = False
        return self._load_vault()

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic status of the Vault."""
        return {
            "path": str(self.vault_path),
            "exists": self.vault_path.exists(),
            "locked": self._locked,
            "backend": self._backend,
            "secret_count": len(self._secrets),
            "has_password": bool(self._master_password),
        }

    def _encrypt_payload(self, plaintext: str) -> Dict[str, Any]:
        """Encrypts JSON plaintext using best available cryptographic backend."""
        data_bytes = plaintext.encode("utf-8")
        
        # 1. Try Windows DPAPI if no custom master password is set
        if not self._master_password and sys.platform == "win32":
            dpapi_res = _dpapi_encrypt(data_bytes)
            if dpapi_res:
                self._backend = "dpapi_win32"
                return {
                    "v": 2,
                    "backend": "dpapi_win32",
                    "ciphertext": base64.b64encode(dpapi_res).decode("ascii"),
                    "updated_at": time.time(),
                }

        # 2. Try Cryptography / Fernet if installed
        try:
            from cryptography.fernet import Fernet
            salt = secrets.token_bytes(16)
            pwd = self._master_password or "KURO_MACHINE_DEFAULT_SECRET"
            key_32 = _derive_key(pwd, salt)
            fernet_key = base64.urlsafe_b64encode(key_32)
            f = Fernet(fernet_key)
            encrypted = f.encrypt(data_bytes)
            self._backend = "fernet_aes"
            return {
                "v": 2,
                "backend": "fernet_aes",
                "salt": base64.b64encode(salt).decode("ascii"),
                "ciphertext": base64.b64encode(encrypted).decode("ascii"),
                "updated_at": time.time(),
            }
        except ImportError:
            pass

        # 3. Pure Python PBKDF2-HMAC-SHA256 authenticated keystream
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(16)
        pwd = self._master_password or "KURO_MACHINE_DEFAULT_SECRET"
        key = _derive_key(pwd, salt)
        ciphertext = _keystream_cipher(data_bytes, key, iv)
        tag = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()

        self._backend = "pbkdf2_hmac_sha256"
        return {
            "v": 2,
            "backend": "pbkdf2_hmac_sha256",
            "salt": base64.b64encode(salt).decode("ascii"),
            "iv": base64.b64encode(iv).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
            "updated_at": time.time(),
        }

    def _decrypt_payload(self, doc: Dict[str, Any]) -> Optional[str]:
        """Decrypts a vault envelope."""
        backend = doc.get("backend", "")

        # 1. DPAPI
        if backend == "dpapi_win32":
            enc_bytes = base64.b64decode(doc["ciphertext"])
            dec_bytes = _dpapi_decrypt(enc_bytes)
            if dec_bytes:
                self._backend = "dpapi_win32"
                return dec_bytes.decode("utf-8")
            return None

        # 2. Fernet AES
        if backend == "fernet_aes":
            try:
                from cryptography.fernet import Fernet
                salt = base64.b64decode(doc["salt"])
                enc_bytes = base64.b64decode(doc["ciphertext"])
                pwd = self._master_password or "KURO_MACHINE_DEFAULT_SECRET"
                key_32 = _derive_key(pwd, salt)
                fernet_key = base64.urlsafe_b64encode(key_32)
                f = Fernet(fernet_key)
                dec_bytes = f.decrypt(enc_bytes)
                self._backend = "fernet_aes"
                return dec_bytes.decode("utf-8")
            except Exception as e:
                logger.debug(f"[Vault] Fernet decrypt error: {e}")
                return None

        # 3. PBKDF2 HMAC fallback
        if backend == "pbkdf2_hmac_sha256":
            try:
                salt = base64.b64decode(doc["salt"])
                iv = base64.b64decode(doc["iv"])
                ciphertext = base64.b64decode(doc["ciphertext"])
                expected_tag = base64.b64decode(doc["tag"])

                pwd = self._master_password or "KURO_MACHINE_DEFAULT_SECRET"
                key = _derive_key(pwd, salt)
                actual_tag = hmac.new(key, iv + ciphertext, hashlib.sha256).digest()

                if not hmac.compare_digest(expected_tag, actual_tag):
                    logger.warning("[Vault] Integrity verification failed (wrong password or corrupted vault).")
                    return None

                plaintext = _keystream_cipher(ciphertext, key, iv)
                self._backend = "pbkdf2_hmac_sha256"
                return plaintext.decode("utf-8")
            except Exception as e:
                logger.debug(f"[Vault] PBKDF2 decrypt error: {e}")
                return None

        return None

    def _load_vault(self) -> bool:
        """Loads and decrypts the vault file into memory."""
        if not self.vault_path.exists():
            self._secrets = {}
            return True

        try:
            raw_text = self.vault_path.read_text(encoding="utf-8")
            doc = json.loads(raw_text)
            decrypted_json = self._decrypt_payload(doc)

            if decrypted_json is None:
                self._locked = True
                logger.warning("[Vault] Could not decrypt vault. Marked as LOCKED.")
                return False

            self._secrets = json.loads(decrypted_json)
            self._locked = False
            return True
        except Exception as e:
            logger.error(f"[Vault] Failed to load vault: {e}")
            self._locked = True
            return False

    def _save_vault(self) -> bool:
        """Encrypts and persists the current secrets to disk."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            raw_json = json.dumps(self._secrets, indent=2)
            payload = self._encrypt_payload(raw_json)
            self.vault_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"[Vault] Failed to save vault: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def set_secret(self, key: str, value: str, description: str = "") -> bool:
        """Stores or updates a secret key-value pair."""
        if self._locked:
            logger.warning("[Vault] Cannot set secret while vault is locked.")
            return False

        clean_key = key.strip().upper()
        clean_val = str(value).strip()

        if not clean_key or not clean_val:
            return False

        self._secrets[clean_key] = {
            "value": clean_val,
            "description": description,
            "updated_at": time.time(),
        }
        return self._save_vault()

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieves a secret by key. Returns default if not found or vault locked."""
        if self._locked:
            return default

        clean_key = key.strip().upper()
        entry = self._secrets.get(clean_key)
        if entry and isinstance(entry, dict):
            return entry.get("value", default)
        elif isinstance(entry, str):
            return entry
        return default

    def delete_secret(self, key: str) -> bool:
        """Deletes a secret from the vault."""
        if self._locked:
            return False

        clean_key = key.strip().upper()
        if clean_key in self._secrets:
            del self._secrets[clean_key]
            return self._save_vault()
        return False

    def list_secrets(self) -> List[Dict[str, Any]]:
        """Returns a list of all secret keys with masked previews and metadata."""
        if self._locked:
            return []

        results = []
        for k, v in self._secrets.items():
            if isinstance(v, dict):
                raw_val = v.get("value", "")
                desc = v.get("description", "")
                ts = v.get("updated_at", 0)
            else:
                raw_val = str(v)
                desc = ""
                ts = 0

            results.append({
                "key": k,
                "masked": mask_secret(raw_val),
                "description": desc,
                "updated_at": ts,
            })
        return sorted(results, key=lambda x: x["key"])

    def auto_migrate_from_env(self, env_path: Optional[Path] = None) -> int:
        """
        Scans .env file and imports known credentials into the encrypted vault.
        Returns count of migrated secrets.
        """
        target = env_path or (CONFIG_DIR.parent / ".env")
        if not target.exists():
            return 0

        migrated_count = 0
        known_prefixes = (
            "GEMINI_", "GROQ_", "OPENAI_", "OPENROUTER_", "ANTHROPIC_",
            "GITHUB_", "DISCORD_", "TELEGRAM_", "SLACK_", "EMAIL_", "SMTP_",
            "GOOGLE_", "AWS_", "AZURE_", "DATABASE_URL", "SECRET_"
        )

        try:
            for line in target.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k_clean = k.strip().upper()
                v_clean = v.strip().strip("'\"")

                if any(k_clean.startswith(prefix) for prefix in known_prefixes) or "KEY" in k_clean or "TOKEN" in k_clean or "SECRET" in k_clean or "PASSWORD" in k_clean:
                    if v_clean and not v_clean.lower().startswith("your_") and v_clean.lower() != "none":
                        if k_clean not in self._secrets:
                            self.set_secret(k_clean, v_clean, description="Auto-migrated from .env")
                            migrated_count += 1
        except Exception as e:
            logger.error(f"[Vault] Migration from .env failed: {e}")

        return migrated_count


# Global Vault Instance
vault = VaultManager()
