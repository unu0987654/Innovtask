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
# Soporte para dos motores de base de datos:
#   - PostgreSQL  -> cuando existe la variable DATABASE_URL (en Render).
#                    Los datos NO se borran entre despliegues.
#   - SQLite      -> en tu PC, sin configurar nada.
#
# app.py y el resto del codigo siguen escribiendo SQL al estilo SQLite
# (marcador '?' y filas tipo row["campo"]). La capa de abajo traduce todo
# automaticamente cuando se usa Postgres, asi no hay que tocar app.py.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith("postgres")

if USE_PG:
    import psycopg2
    import psycopg2.extras

    # Render a veces entrega la URL como 'postgres://'; psycopg2 prefiere 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# Tipo de columna autoincremental segun el motor
_PK = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"


class _PgCursorWrap:
    """Hace que un cursor de Postgres se comporte como el de sqlite3:
    traduce los '?' a '%s' y permite encadenar .execute(...).fetchone()."""
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(sql.replace("?", "%s"), params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _PgConnWrap:
    """Envuelve la conexion de Postgres para imitar la API de sqlite3 que
    usa app.py: .execute(...), .cursor(), .commit(), .close()."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _PgCursorWrap(
            self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        )

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

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
    if USE_PG:
        return _PgConnWrap(psycopg2.connect(DATABASE_URL))
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    cur = c.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS users(
            id {_PK},
            email_enc TEXT UNIQUE,      -- correo cifrado
            email_idx TEXT UNIQUE,      -- hash del correo para buscar sin descifrar
            name_enc TEXT,              -- nombre cifrado
            role TEXT,
            pass_hash TEXT,
            color TEXT,
            created_at TEXT
        )""")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS tasks(
            id {_PK},
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
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS events(
            id {_PK},
            name TEXT, date TEXT, time TEXT, color TEXT,
            owner_email_idx TEXT
        )""")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS notifications(
            id {_PK},
            user_email_idx TEXT,
            text TEXT, kind TEXT, read INTEGER DEFAULT 0,
            created_at TEXT
        )""")
    c.commit()
    # Migracion: anadir columnas de hora si la BD es vieja (tolerante en ambos motores)
    for col in ("start_time", "end_time"):
        try:
            cur.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
            c.commit()
        except Exception:
            try:
                c.rollback()  # Postgres deja la transaccion abortada tras un error
            except Exception:
                pass  # ya existe la columna
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
