"""
cargar_tareas.py - Inserta las 11 tareas (las del hilo de Google Drive) en TU
base de datos local, usando TU propia llave de cifrado.

Como hablas con TU base (no una traida de afuera), no hay problema de llave.

Pasos:
  1. Pon este archivo dentro de la carpeta "backend" (junto a app.py).
  2. Abre una terminal en esa carpeta.
  3. Corre:  python cargar_tareas.py
  4. Abre tu app normal:  python app.py

Si lo corres dos veces no duplica nada: revisa por nombre antes de insertar.
"""
import datetime
import random

import database as db
import classifier

db.init_db()
idx = db._email_index


def iso(m, d, h=10, mi=0):
    return datetime.datetime(2026, m, d, h, mi).isoformat()


# name, desc, correo_admin, correo_solicitante, tipo, estado, avance, fecha, creada
TAREAS = [
    ("Dynamic Report - ABC",
     "Generar el Dynamic Report de la empresa ABC. Bloqueado: el modelo 104 para este producto digital aun no esta disponible.",
     "david.acosta@peoplesvoice.co", "sebastian.sandoval@peoplesvoice.co", "otro", "block", 20, "2026-06-09", iso(6, 9, 16, 21)),
    ("Pulse Assessment - ABC",
     "Generar el Pulse Assessment de la empresa ABC. Bloqueado: el modelo 104 aun no esta disponible (en pruebas, pendiente aval de German).",
     "david.acosta@peoplesvoice.co", "sebastian.sandoval@peoplesvoice.co", "contextual_assessment", "block", 20, "2026-06-09", iso(6, 9, 16, 30)),
    ("CA por Areas - Colfondos",
     "Generar el CA por Areas de la empresa Colfondos S.A Pensiones y Cesantias.",
     "", "operaciones@peoplesvoice.co", "contextual_assessment", "todo", 0, "2026-06-13", iso(6, 13, 9, 0)),
    ("CA Consolidado - Colfondos",
     "Generar el CA Consolidado de Colfondos S.A Pensiones y Cesantias. Enviado a los usuarios Mgarzon@colfondos.com.co y magarzon@colfondos.com.co.",
     "mayra.garcia@peoplesvoice.co", "operaciones@peoplesvoice.co", "contextual_assessment", "done", 100, "2026-06-16", iso(6, 16, 10, 0)),
    ("Dynamic Report - Vision Software",
     "Generar el DR de Vision Software S.A.S. DR disponible para revision.",
     "david.acosta@peoplesvoice.co", "carolina.rodriguezr@peoplesvoice.co", "otro", "done", 100, "2026-06-16", iso(6, 16, 22, 32)),
    ("Dynamic Report - Alimentos Polar",
     "Generar el DR de Alimentos Polar Colombia S.A.S. DR disponible.",
     "david.acosta@peoplesvoice.co", "carolina.rodriguezr@peoplesvoice.co", "otro", "done", 100, "2026-06-16", iso(6, 16, 22, 44)),
    ("CA Consolidado - Fiduagraria",
     "Generar el CA Consolidado de Fiduagraria S.A. Disponible para revision.",
     "david.acosta@peoplesvoice.co", "nicolas.beltran@peoplesvoice.co", "contextual_assessment", "done", 100, "2026-06-17", iso(6, 17, 9, 37)),
    ("CA por Areas - Fiduagraria",
     "Generar el CA por Areas de Fiduagraria S.A. CA disponible para revision, se asignaron los 2 usuarios solicitados.",
     "david.acosta@peoplesvoice.co", "nicolas.beltran@peoplesvoice.co", "contextual_assessment", "done", 100, "2026-06-17", iso(6, 17, 12, 5)),
    ("CA Consolidado - Marcali",
     "Generar el CA Consolidado de Comercializadora de Autos Marcali S.A.S.",
     "david.acosta@peoplesvoice.co", "julian.baquero@peoplesvoice.co", "contextual_assessment", "done", 100, "2026-06-17", iso(6, 17, 16, 22)),
    ("CA por Areas - Marcali",
     "Generar el CA por Areas de Comercializadora de Autos Marcali S.A.S.",
     "david.acosta@peoplesvoice.co", "julian.baquero@peoplesvoice.co", "contextual_assessment", "done", 100, "2026-06-17", iso(6, 17, 16, 54)),
    ("Certificacion - Siemens Healthcare",
     "Empresa certificada. El sello debe ir de Jun 2026 a Jun 2027.",
     "alejandra.gomez@peoplesvoice.co", "felipe.gutierrez@peoplesvoice.co", "certificaciones", "done", 100, "2026-06-17", iso(6, 17, 17, 0)),
]


def main():
    c = db._conn()
    creadas = 0
    saltadas = 0

    for (name, desc, correo_admin, correo_req, tipo, estado, avance, fecha, creada) in TAREAS:
        # Evitar duplicados: si ya existe una tarea con ese nombre, la saltamos.
        existe = c.execute("SELECT 1 FROM tasks WHERE name=?", (name,)).fetchone()
        if existe:
            print(f"  (ya existe, se salta)  {name}")
            saltadas += 1
            continue

        a_idx = idx(correo_admin) if correo_admin else ""
        r_idx = idx(correo_req) if correo_req else ""

        tipo_valido = ("contextual_assessment", "certificaciones", "otro")
        if tipo not in tipo_valido:
            tipo, _, _ = classifier.detect_process_kind(name + " " + desc)

        code = "WOS-" + datetime.datetime.fromisoformat(creada).strftime("%m%d%H%M") + str(random.randint(10, 99))
        prio = "high" if estado == "block" else "med"

        c.execute("""INSERT INTO tasks
            (code,name,descr,assignee_email_idx,requester_email_idx,supervisor_email_idx,
             status,prio,ttype,process_kind,date,start_time,end_time,time_spent,progress,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (code, name, desc, a_idx, r_idx, "", estado, prio, "general", tipo, fecha,
                   "", "", 0, avance, creada, creada))
        print(f"  creada [{estado:5}]  {name}")
        creadas += 1

    c.commit()
    total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    c.close()

    print()
    print(f"Listo. Creadas: {creadas} | Saltadas (ya estaban): {saltadas} | Total en la BD: {total}")
    print("Ahora abre tu app normal:  python app.py")


if __name__ == "__main__":
    main()
