"""
database.py - Capa de datos de INNOVTASK sobre SQLite con cifrado de campos.

Roles:
  coordinador  -> supervisa tareas, ve avance del equipo
  procesos     -> como coordinador PERO con indices detallados, % efectividad,
                  y asignacion por tipo (contextual_assessment / certificaciones)
  admin        -> ejecuta tareas; tiene resumen de carga/agenda; recibe correo
  analista     -> solo SOLICITA cosas a los admin; sin datos de analisis

Los correos/nombres se guardan cifrados en reposo (security.encrypt_field).
Las contrasenas se guardan como hash PBKDF2.
"""
import os
import sqlite3
import json
import datetime
from security import (
    encrypt_field, decrypt_field, hash_password, verify_password
)

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "innovtask.db")

# ---------------------------------------------------------------------------
# Usuarios reales (semilla). Contrasena inicial por defecto: "innovtask2026"
# El usuario puede cambiarla luego. Se hashea al sembrar.
# ---------------------------------------------------------------------------
DEFAULT_PASSWORD = "innovtask2026"

SEED_USERS = [
    # Coordinadores
    ("Marcella Córdoba",   "marcella.cordoba@peoplesvoice.co",   "coordinador"),
    ("Ángela Álvarez",     "angela.alvarez@peoplesvoice.co",     "coordinador"),
    ("Alejandro Garzón",   "alejandro.garzon@peoplesvoice.co",   "coordinador"),
    ("Francisco González", "francisco.gonzales@peoplesvoice.co", "coordinador"),
    ("Christian Pinilla",  "christian.pinilla@peoplesvoice.co",  "coordinador"),
    ("Felipe Gutiérrez",   "felipe.gutierrez@peoplesvoice.co",   "coordinador"),
    # Profesionales en procesos (coordinador + indices detallados)
    ("Harold Cárdenas",    "harold.cardenas@peoplesvoice.co",    "procesos"),
    ("German Romero",      "german.romero@peoplesvoice.co",      "procesos"),
    # Administradores
    ("Alejandra Gomez",    "alejandra.gomez@peoplesvoice.co",    "admin"),
    ("David Acosta",       "david.acosta@peoplesvoice.co",       "admin"),
    ("Mayra Garcia",       "mayra.garcia@peoplesvoice.co",       "admin"),
    # Analistas (solo solicitan)
    ("Natalia Leguizamón", "natalia.leguizamon@peoplesvoice.co", "analista"),
    ("Valeria Cepeda",     "valeria.cepeda@peoplesvoice.co",     "analista"),
    ("Carolina Rodríguez", "carolina.rodriguezr@peoplesvoice.co","analista"),
    ("Lina Almanza",       "lina.almanza@peoplesvoice.co",       "analista"),
    ("Julián Baquero",     "julian.baquero@peoplesvoice.co",     "analista"),
    ("Mildreth Díaz",      "mildreth.diaz@peoplesvoice.co",      "analista"),
    ("Sebastián Sandoval", "sebastian.sandoval@peoplesvoice.co", "analista"),
    ("Nicolás Beltrán",    "nicolas.beltran@peoplesvoice.co",    "analista"),
    ("Laura Gamba",        "laura.gamba@peoplesvoice.co",        "analista"),
]


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_enc TEXT UNIQUE,      -- correo cifrado
            email_idx TEXT UNIQUE,      -- hash del correo para buscar sin descifrar
            name_enc TEXT,              -- nombre cifrado
            role TEXT,
            pass_hash TEXT,
            color TEXT,
            created_at TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            descr TEXT,
            assignee_email_idx TEXT,    -- a quien se asigna (admin)
            requester_email_idx TEXT,   -- quien solicito (analista/coordinador)
            supervisor_email_idx TEXT,  -- coordinador que supervisa
            status TEXT,                -- todo/prog/rev/block/done
            prio TEXT,                  -- low/med/high
            ttype TEXT,                 -- general/contextual_assessment/certificaciones
            process_kind TEXT,          -- para perfil procesos
            date TEXT,
            start_time TEXT,            -- hora inicio opcional HH:MM
            end_time TEXT,              -- hora fin opcional HH:MM
            time_spent INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0, -- % avance 0-100
            created_at TEXT,
            updated_at TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, date TEXT, time TEXT, color TEXT,
            owner_email_idx TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email_idx TEXT,
            text TEXT, kind TEXT, read INTEGER DEFAULT 0,
            created_at TEXT
        )""")
    c.commit()
    # Migracion: anadir columnas de hora si la BD es vieja
    for col in ("start_time", "end_time"):
        try:
            cur.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
        except Exception:
            pass  # ya existe
    c.commit()
    _seed_users(c)
    c.close()


def _email_index(email: str) -> str:
    import hashlib
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def _seed_users(c):
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM users")
    if cur.fetchone()["n"] > 0:
        return
    palette = ["#4A9FD4", "#1A9E6E", "#E8930A", "#D93B3B", "#2272C3", "#0D7A6B"]
    now = datetime.datetime.now().isoformat()
    for i, (name, email, role) in enumerate(SEED_USERS):
        cur.execute(
            "INSERT INTO users(email_enc,email_idx,name_enc,role,pass_hash,color,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (encrypt_field(email), _email_index(email), encrypt_field(name),
             role, hash_password(DEFAULT_PASSWORD), palette[i % len(palette)], now)
        )
    c.commit()


# ---------------------------------------------------------------------------
# Operaciones de usuario
# ---------------------------------------------------------------------------
def get_user_by_email(email: str):
    c = _conn()
    row = c.execute("SELECT * FROM users WHERE email_idx=?", (_email_index(email),)).fetchone()
    c.close()
    if not row:
        return None
    return _user_to_dict(row)


def _user_to_dict(row):
    return {
        "id": row["id"],
        "email": decrypt_field(row["email_enc"]),
        "name": decrypt_field(row["name_enc"]),
        "role": row["role"],
        "color": row["color"],
    }


def verify_user(email: str, password: str):
    c = _conn()
    row = c.execute("SELECT * FROM users WHERE email_idx=?", (_email_index(email),)).fetchone()
    c.close()
    if not row:
        return None
    if not verify_password(password, row["pass_hash"]):
        return None
    return _user_to_dict(row)


def list_users():
    c = _conn()
    rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
    c.close()
    return [_user_to_dict(r) for r in rows]


def users_by_role(role: str):
    return [u for u in list_users() if u["role"] == role]


def update_password(email: str, new_password: str):
    c = _conn()
    c.execute("UPDATE users SET pass_hash=? WHERE email_idx=?",
              (hash_password(new_password), _email_index(email)))
    c.commit()
    c.close()
