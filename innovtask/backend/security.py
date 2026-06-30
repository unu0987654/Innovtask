"""
security.py - Capa de privacidad y seguridad de datos para INNOVTASK.

Estrategia:
  - Contrasenas: hash PBKDF2-HMAC-SHA256 con salt por usuario (nunca se guarda la clave en claro).
  - Datos sensibles (nombre, correo): cifrado simetrico AES (Fernet) en reposo dentro de SQLite.
  - La clave maestra se deriva de una passphrase de la app y se guarda fuera de la BD.

Esto permite empaquetar a .exe sin dependencias nativas fragiles (no requiere SQLCipher).
"""
import os
import base64
import hashlib
import hmac
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ---------------------------------------------------------------------------
# Clave maestra de cifrado de campos
# ---------------------------------------------------------------------------
_KEY_FILE = os.path.join(os.path.dirname(__file__), "db", "master.key")


def _ensure_master_key() -> bytes:
    """Carga la clave maestra Fernet.

    Prioridad:
      1) Variable de entorno MASTER_KEY  (asi se usa en Render: la clave
         es estable entre despliegues y los datos cifrados siguen siendo
         legibles aunque el disco se reinicie).
      2) Archivo local db/master.key     (para uso en tu PC).
    """
    env_key = os.environ.get("MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8") if isinstance(env_key, str) else env_key

    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    if not os.path.exists(_KEY_FILE):
        key = Fernet.generate_key()
        with open(_KEY_FILE, "wb") as f:
            f.write(key)
        # Permisos restrictivos donde el SO lo permita
        try:
            os.chmod(_KEY_FILE, 0o600)
        except Exception:
            pass
    with open(_KEY_FILE, "rb") as f:
        return f.read()


_fernet = Fernet(_ensure_master_key())


def encrypt_field(value: str) -> str:
    """Cifra un string para guardarlo en reposo. Devuelve texto base64."""
    if value is None:
        return None
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_field(token: str) -> str:
    """Descifra un campo previamente cifrado."""
    if token is None:
        return None
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        # Si por alguna razon el dato no estaba cifrado (migracion), lo devolvemos tal cual
        return token


# ---------------------------------------------------------------------------
# Hashing de contrasenas (PBKDF2)
# ---------------------------------------------------------------------------
_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    """Devuelve 'salt$hash' en hex. Salt aleatorio por usuario."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    """Verifica una contrasena contra el formato 'salt$hash'."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tokens de sesion simples (firmados)
# ---------------------------------------------------------------------------
def make_token(email: str) -> str:
    raw = email + ":" + os.urandom(8).hex()
    sig = hmac.new(_ensure_master_key(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode((raw + ":" + sig).encode()).decode()
