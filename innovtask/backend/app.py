"""
app.py - Backend principal de INNOVTASK.

Sirve el frontend (index.html) y expone la API REST.
Reglas de rol implementadas:
  - analista  : solo crea SOLICITUDES (tareas en estado 'todo') dirigidas a un admin.
                No ve analitica.
  - coordinador: ve todas las tareas, supervisa, ve avance del equipo. No se mide su eficiencia.
  - procesos  : igual a coordinador + indices detallados, % de efectividad,
                y puede clasificar tareas como contextual_assessment / certificaciones.
  - admin     : ejecuta tareas asignadas, actualiza estado/avance, recibe correo,
                tiene resumen de "que hace hoy / esta semana".
"""
import os
import sys
import datetime
import sqlite3
import webbrowser
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import database as db
from database import _conn, _email_index
import mailer
import classifier
import holidays_co
import google_cal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

app = Flask(__name__, static_folder=None)
CORS(app)

# Inicializa la base al importar el modulo. Esto es necesario en Render,
# donde la app la arranca gunicorn y NO se ejecuta el bloque __main__.
# Es seguro llamarlo siempre: crea tablas solo si no existen y siembra
# los usuarios solo si la tabla esta vacia.
try:
    db.init_db()
except Exception as _e:
    print("Aviso: init_db al importar fallo:", _e)


@app.route("/setup")
def _setup():
    """Ruta temporal de diagnostico: crea las tablas y siembra usuarios.
    Si algo falla, muestra el error exacto en pantalla. Borrar despues de usar."""
    import traceback
    try:
        db.init_db()
        fixed = db.sync_seed_roles()
        msg = "OK: base inicializada. Tablas creadas y usuarios sembrados."
        if fixed:
            msg += "\n\nRoles corregidos:\n" + "\n".join(fixed)
        msg += "\n\nYa puedes iniciar sesion."
        return msg, 200
    except Exception as e:
        return "ERROR al inicializar la base:\n\n" + traceback.format_exc(), 500


# ---------------------------------------------------------------------------
# Google Calendar (solo lectura)
# ---------------------------------------------------------------------------
@app.route("/api/google/status")
def google_status():
    """Indica si el usuario ya conecto su Google Calendar y si la integracion
    esta configurada en el servidor."""
    email = request.args.get("email", "")
    return jsonify({
        "ok": True,
        "configured": google_cal.is_configured(),
        "connected": db.has_google_connected(email) if email else False,
    })


@app.route("/api/google/connect")
def google_connect():
    """Inicia el flujo: redirige al usuario a Google para autorizar.
    Se identifica al usuario con 'state' = su email."""
    email = request.args.get("email", "")
    if not google_cal.is_configured():
        return "La integracion con Google no esta configurada en el servidor.", 503
    if not email:
        return "Falta el correo del usuario.", 400
    url = google_cal.build_auth_url(state=email)
    # Redireccion HTTP a Google
    from flask import redirect
    return redirect(url)


@app.route("/oauth/google/callback")
def google_callback():
    """Google devuelve aqui tras autorizar. Guardamos el refresh_token."""
    from flask import redirect
    code = request.args.get("code", "")
    email = request.args.get("state", "")
    err = request.args.get("error", "")
    if err or not code or not email:
        return redirect("/?google=error")
    try:
        tok = google_cal.exchange_code(code)
        refresh = tok.get("refresh_token")
        if refresh:
            db.save_google_token(email, refresh)
            return redirect("/?google=ok")
        # Si no vino refresh_token (ya habia autorizado antes), igual lo damos por conectado
        return redirect("/?google=ok")
    except Exception:
        return redirect("/?google=error")


@app.route("/api/google/events")
def google_events():
    """Devuelve los eventos del Google Calendar del usuario (proximos 30 dias)."""
    email = request.args.get("email", "")
    if not email or not google_cal.is_configured():
        return jsonify({"ok": True, "events": []})
    refresh = db.get_google_token(email)
    if not refresh:
        return jsonify({"ok": True, "events": [], "connected": False})
    try:
        tokresp = google_cal.refresh_access_token(refresh)
        access = tokresp.get("access_token")
        if not access:
            return jsonify({"ok": True, "events": [], "connected": False})
        events = google_cal.list_events(access, days_ahead=30)
        return jsonify({"ok": True, "events": events, "connected": True})
    except Exception:
        return jsonify({"ok": True, "events": [], "connected": True})


@app.route("/api/google/disconnect", methods=["POST"])
def google_disconnect():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    if email:
        db.save_google_token(email, None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso():
    return datetime.datetime.now().isoformat()


def task_to_dict(row):
    return {
        "id": row["code"],
        "name": row["name"],
        "desc": row["descr"],
        "assignee": row["assignee_email_idx"],
        "requester": row["requester_email_idx"],
        "supervisor": row["supervisor_email_idx"],
        "status": row["status"],
        "prio": row["prio"],
        "type": row["ttype"],
        "process_kind": row["process_kind"],
        "date": row["date"],
        "start_time": row["start_time"] if "start_time" in row.keys() else "",
        "end_time": row["end_time"] if "end_time" in row.keys() else "",
        "time": row["time_spent"],
        "progress": row["progress"],
    }


def name_for_idx(idx):
    for u in db.list_users():
        if _email_index(u["email"]) == idx:
            return u["name"]
    return "—"


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:fname>")
def static_files(fname):
    return send_from_directory(FRONTEND_DIR, fname)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = db.verify_user(email, password)
    if not user:
        return jsonify({"ok": False, "error": "Correo o contraseña incorrectos."}), 401
    user["email_idx"] = _email_index(user["email"])
    # Si entro con la clave inicial, debe crear la suya
    user["must_change"] = (password == db.DEFAULT_PASSWORD)
    return jsonify({"ok": True, "user": user})


@app.route("/api/users")
def api_users():
    users = db.list_users()
    for u in users:
        u["email_idx"] = _email_index(u["email"])
    return jsonify(users)


@app.route("/api/change-password", methods=["POST"])
def change_password():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    current = data.get("current") or ""
    new = data.get("new") or ""
    if len(new) < 6:
        return jsonify({"ok": False, "error": "La nueva contraseña debe tener al menos 6 caracteres."}), 400
    user = db.verify_user(email, current)
    if not user:
        return jsonify({"ok": False, "error": "La contraseña actual no es correcta."}), 401
    db.update_password(email, new)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@app.route("/api/tasks")
def api_tasks():
    role = request.args.get("role", "")
    email = (request.args.get("email") or "").lower()
    idx = _email_index(email) if email else ""
    c = _conn()
    rows = c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    c.close()
    tasks = [task_to_dict(r) for r in rows]
    # admin solo ve las suyas; analista ve las que solicito; coord/procesos ven todo
    if role == "admin":
        tasks = [t for t in tasks if t["assignee"] == idx]
    elif role == "analista":
        tasks = [t for t in tasks if t["requester"] == idx]
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(force=True)
    role = data.get("role", "")
    requester_email = (data.get("requester_email") or "").lower()
    assignee_idx = data.get("assignee")          # email_idx del admin
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "El nombre es obligatorio."}), 400

    # Reglas por rol
    ttype = data.get("type", "general")
    if role not in ("coordinador", "procesos", "analista"):
        return jsonify({"ok": False, "error": "Tu rol no puede crear tareas."}), 403

    # Tipo de proceso: cualquiera que solicite puede marcarlo (CA / certificaciones / otro).
    # Si no lo marca, se detecta del texto (nombre + descripcion) por palabras clave.
    process_kind = data.get("process_kind")
    valid_kinds = ("contextual_assessment", "certificaciones", "otro")
    if process_kind not in valid_kinds:
        detected, _label, _conf = classifier.detect_process_kind(
            name + " " + data.get("desc", ""))
        process_kind = detected

    import random
    code = "WOS-" + datetime.datetime.now().strftime("%H%M%S") + str(random.randint(10, 99))
    requester_idx = _email_index(requester_email)
    # El supervisor es quien crea (coordinador/procesos). Si crea un analista, queda sin supervisor fijo.
    supervisor_idx = requester_idx if role in ("coordinador", "procesos") else ""

    c = _conn()
    c.execute("""INSERT INTO tasks
        (code,name,descr,assignee_email_idx,requester_email_idx,supervisor_email_idx,
         status,prio,ttype,process_kind,date,start_time,end_time,time_spent,progress,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, name, data.get("desc", ""), assignee_idx, requester_idx, supervisor_idx,
         "todo", data.get("prio", "med"), ttype, process_kind, data.get("date", ""),
         data.get("start_time", ""), data.get("end_time", ""),
         0, 0, now_iso(), now_iso()))
    c.commit()
    c.close()

    # Notificacion + correo al admin asignado
    if assignee_idx:
        _notify_admin(assignee_idx, name, requester_idx, data.get("prio", "med"))

    return jsonify({"ok": True, "code": code})


def _notify_admin(assignee_idx, task_name, requester_idx, prio):
    admin = None
    for u in db.list_users():
        if _email_index(u["email"]) == assignee_idx:
            admin = u
            break
    if not admin:
        return
    # Notificacion in-app
    c = _conn()
    c.execute("INSERT INTO notifications(user_email_idx,text,kind,read,created_at) VALUES(?,?,?,?,?)",
              (assignee_idx, f'Nueva tarea: "{task_name[:30]}"', "info", 0, now_iso()))
    c.commit()
    c.close()
    # Correo real
    subject = "INNOVTASK · Nueva tarea asignada"
    html = mailer.build_task_email(admin["name"], task_name, name_for_idx(requester_idx), prio)
    mailer.send_notification(admin["email"], subject, html)


@app.route("/api/tasks/<code>", methods=["PUT"])
def update_task(code):
    data = request.get_json(force=True)
    role = data.get("role", "")
    fields, vals = [], []
    # admin solo puede tocar status y progress
    allowed = ["status", "progress"] if role == "admin" else \
              ["name", "descr", "status", "prio", "ttype", "process_kind", "date", "start_time", "end_time", "progress", "assignee_email_idx"]
    mapping = {"desc": "descr", "type": "ttype", "assignee": "assignee_email_idx"}
    for k, v in data.items():
        col = mapping.get(k, k)
        if col in allowed:
            fields.append(f"{col}=?")
            vals.append(v)
    if not fields:
        return jsonify({"ok": False, "error": "Nada para actualizar."}), 400
    fields.append("updated_at=?")
    vals.append(now_iso())
    vals.append(code)
    c = _conn()
    c.execute(f"UPDATE tasks SET {','.join(fields)} WHERE code=?", vals)
    c.commit()
    c.close()
    return jsonify({"ok": True})


@app.route("/api/tasks/<code>", methods=["DELETE"])
def delete_task(code):
    c = _conn()
    c.execute("DELETE FROM tasks WHERE code=?", (code,))
    c.commit()
    c.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Analitica: efectividad (solo procesos) y resumen de admins
# ---------------------------------------------------------------------------
@app.route("/api/suggest-kind")
def suggest_kind():
    """Sugiere el tipo de proceso a partir del texto (deteccion por palabras clave)."""
    text = request.args.get("text", "")
    kind, label, conf = classifier.detect_process_kind(text)
    return jsonify({"kind": kind, "label": label, "confidence": conf})


@app.route("/api/effectiveness")
def effectiveness():
    """
    Indicadores detallados para el panel de Harold y German (rol procesos).
    Entrega TODO lo necesario para las graficas:
      - by_kind: total, completadas, avance promedio y % efectividad por tipo
      - volume: cuantas de cada tipo (incluye 'otro')
      - status_breakdown: conteo por estado (todo/prog/rev/block/done)
      - by_admin: efectividad de cada admin dentro de cada tipo
      - trend: creadas vs completadas por semana (ultimas 6 semanas)
    """
    role = request.args.get("role", "")
    if role != "procesos":
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    c = _conn()
    rows = c.execute("SELECT * FROM tasks").fetchall()
    c.close()

    kinds = ("contextual_assessment", "certificaciones", "otro")

    # 1) by_kind + 2) volume + 3) avance
    by_kind, volume = {}, {}
    for kind in kinds:
        subset = [r for r in rows if r["process_kind"] == kind]
        total = len(subset)
        done = len([r for r in subset if r["status"] == "done"])
        avg_prog = round(sum(r["progress"] for r in subset) / total, 1) if total else 0
        eff = round((done / total) * 100, 1) if total else 0
        by_kind[kind] = {"total": total, "done": done,
                         "avg_progress": avg_prog, "effectiveness": eff}
        volume[kind] = total

    # 4) status breakdown global
    status_breakdown = {}
    for st in ("todo", "prog", "rev", "block", "done"):
        status_breakdown[st] = len([r for r in rows if r["status"] == st])

    # 5) efectividad por admin dentro de cada tipo
    by_admin = []
    for adm in db.users_by_role("admin"):
        idx = _email_index(adm["email"])
        entry = {"name": adm["name"]}
        for kind in ("contextual_assessment", "certificaciones"):
            subset = [r for r in rows if r["assignee_email_idx"] == idx
                      and r["process_kind"] == kind]
            total = len(subset)
            done = len([r for r in subset if r["status"] == "done"])
            entry[kind] = {
                "total": total,
                "done": done,
                "effectiveness": round((done / total) * 100, 1) if total else 0,
            }
        by_admin.append(entry)

    # 6) tendencia: creadas vs completadas por semana (ultimas 6)
    today = datetime.date.today()
    weeks = []
    for w in range(5, -1, -1):
        start = today - datetime.timedelta(days=today.weekday() + w * 7)
        end = start + datetime.timedelta(days=6)
        created = completed = 0
        for r in rows:
            try:
                cd = datetime.datetime.fromisoformat(r["created_at"]).date()
                if start <= cd <= end:
                    created += 1
                    if r["status"] == "done":
                        completed += 1
            except Exception:
                pass
        weeks.append({"label": start.strftime("%d/%m"),
                      "created": created, "completed": completed})

    # 7) carga por persona (deteccion de sobrecarga) y prediccion
    workload = []
    for adm in db.users_by_role("admin"):
        idx = _email_index(adm["email"])
        mine = [r for r in rows if r["assignee_email_idx"] == idx]
        pendientes = len([r for r in mine if r["status"] != "done"])
        en_progreso = len([r for r in mine if r["status"] == "prog"])
        vencidas = 0
        today_s = datetime.date.today().isoformat()
        for r in mine:
            if r["status"] != "done" and r["date"] and r["date"] < today_s:
                vencidas += 1
        workload.append({
            "name": adm["name"],
            "pendientes": pendientes,
            "en_progreso": en_progreso,
            "vencidas": vencidas,
            "total": len(mine),
        })
    # nivel de sobrecarga: media de pendientes; quien supere 1.5x se marca
    avg_pend = (sum(w["pendientes"] for w in workload) / len(workload)) if workload else 0
    for w in workload:
        if avg_pend and w["pendientes"] > avg_pend * 1.5:
            w["nivel"] = "alto"
        elif w["pendientes"] >= avg_pend:
            w["nivel"] = "medio"
        else:
            w["nivel"] = "bajo"

    # 8) prediccion simple del sprint segun ritmo de completado
    total_tasks = len(rows)
    total_done = len([r for r in rows if r["status"] == "done"])
    pend_total = total_tasks - total_done
    # ritmo: completadas en las ultimas 2 semanas / 14 dias
    last14 = 0
    cutoff = datetime.date.today() - datetime.timedelta(days=14)
    for r in rows:
        if r["status"] == "done":
            try:
                ud = datetime.datetime.fromisoformat(r["updated_at"]).date()
                if ud >= cutoff:
                    last14 += 1
            except Exception:
                pass
    rate_per_day = last14 / 14.0 if last14 else 0
    if rate_per_day > 0:
        dias_estimados = round(pend_total / rate_per_day)
    else:
        dias_estimados = None
    prediction = {
        "pendientes": pend_total,
        "ritmo_dia": round(rate_per_day, 2),
        "dias_estimados": dias_estimados,
        "completadas_total": total_done,
        "total": total_tasks,
    }

    return jsonify({
        "ok": True,
        "by_kind": by_kind,
        "volume": volume,
        "status_breakdown": status_breakdown,
        "by_admin": by_admin,
        "trend": weeks,
        "workload": workload,
        "prediction": prediction,
    })


@app.route("/api/admin-summary")
def admin_summary():
    """Resumen de que hace cada admin hoy / esta semana, para no chocar agendas."""
    horizon = request.args.get("horizon", "today")  # today | week
    today = datetime.date.today()
    if horizon == "week":
        end = today + datetime.timedelta(days=7)
    else:
        end = today
    c = _conn()
    rows = c.execute("SELECT * FROM tasks").fetchall()
    c.close()
    summary = []
    for adm in db.users_by_role("admin"):
        idx = _email_index(adm["email"])
        mine = [r for r in rows if r["assignee_email_idx"] == idx]
        doing = [task_to_dict(r) for r in mine if r["status"] in ("prog", "rev")]
        todo = []
        for r in mine:
            if r["status"] in ("todo", "prog", "block") and r["date"]:
                try:
                    d = datetime.date.fromisoformat(r["date"])
                    if today <= d <= end:
                        todo.append(task_to_dict(r))
                except Exception:
                    pass
        summary.append({
            "name": adm["name"],
            "email": adm["email"],
            "active": len([r for r in mine if r["status"] != "done"]),
            "doing": doing,
            "upcoming": todo,
        })
    return jsonify({"ok": True, "horizon": horizon, "data": summary})


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@app.route("/api/notifications")
def get_notifications():
    email = (request.args.get("email") or "").lower()
    idx = _email_index(email)
    c = _conn()
    rows = c.execute("SELECT * FROM notifications WHERE user_email_idx=? ORDER BY id DESC LIMIT 30",
                     (idx,)).fetchall()
    c.close()
    return jsonify([{"id": r["id"], "text": r["text"], "kind": r["kind"],
                     "read": r["read"], "created_at": r["created_at"]} for r in rows])


# ---------------------------------------------------------------------------
# Festivos de Colombia (cualquier año)
# ---------------------------------------------------------------------------
@app.route("/api/holidays")
def api_holidays():
    year = int(request.args.get("year", datetime.date.today().year))
    return jsonify(holidays_co.holidays_for_year(year))


# ---------------------------------------------------------------------------
# Disponibilidad: que hace y que espacios libres tiene un admin
# ---------------------------------------------------------------------------
def _free_slots(busy, day_start="08:00", day_end="18:00"):
    """Dado una lista de (inicio,fin) ocupados, calcula los huecos libres."""
    def to_min(t):
        h, m = t.split(":"); return int(h) * 60 + int(m)
    def to_str(x):
        return f"{x//60:02d}:{x%60:02d}"
    busy = sorted([(to_min(s), to_min(e)) for s, e in busy if s and e])
    free, cursor = [], to_min(day_start)
    end = to_min(day_end)
    for s, e in busy:
        if s > cursor:
            free.append((to_str(cursor), to_str(min(s, end))))
        cursor = max(cursor, e)
    if cursor < end:
        free.append((to_str(cursor), to_str(end)))
    return free


@app.route("/api/availability")
def availability():
    """Que hace cada admin hoy y que espacios libres tiene (segun horas de tareas)."""
    date = request.args.get("date", datetime.date.today().isoformat())
    c = _conn()
    rows = c.execute("SELECT * FROM tasks WHERE date=?", (date,)).fetchall()
    c.close()
    result = []
    for adm in db.users_by_role("admin"):
        idx = _email_index(adm["email"])
        mine = [r for r in rows if r["assignee_email_idx"] == idx]
        timed = [(r["start_time"], r["end_time"]) for r in mine
                 if (r["start_time"] if "start_time" in r.keys() else "")
                 and (r["end_time"] if "end_time" in r.keys() else "")]
        doing = [task_to_dict(r) for r in mine if r["status"] in ("prog", "rev")]
        result.append({
            "name": adm["name"],
            "email": adm["email"],
            "tasks_today": [task_to_dict(r) for r in mine],
            "doing_now": doing,
            "free_slots": _free_slots(timed),
            "busy_count": len(timed),
        })
    return jsonify({"ok": True, "date": date, "data": result})


# ---------------------------------------------------------------------------
# Resumen diario por usuario (para la IA: "hoy completaste X...")
# ---------------------------------------------------------------------------
@app.route("/api/daily-summary")
def daily_summary():
    email = (request.args.get("email") or "").lower()
    role = request.args.get("role", "")
    idx = _email_index(email)
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    c = _conn()
    rows = c.execute("SELECT * FROM tasks").fetchall()
    c.close()
    if role == "admin":
        mine = [r for r in rows if r["assignee_email_idx"] == idx]
    elif role == "analista":
        mine = [r for r in rows if r["requester_email_idx"] == idx]
    else:
        mine = list(rows)
    done_today = len([r for r in mine if r["status"] == "done"
                      and (r["updated_at"] or "").startswith(today)])
    pending = len([r for r in mine if r["status"] != "done"])
    tomorrow_tasks = len([r for r in mine if r["date"] == tomorrow and r["status"] != "done"])
    return jsonify({
        "ok": True,
        "completed_today": done_today,
        "pending": pending,
        "tomorrow": tomorrow_tasks,
    })


# ---------------------------------------------------------------------------
# Recordatorios inteligentes: tareas que vencen en 3 dias, 1 dia, o vencidas
# ---------------------------------------------------------------------------
@app.route("/api/reminders")
def reminders():
    email = (request.args.get("email") or "").lower()
    role = request.args.get("role", "")
    idx = _email_index(email)
    today = datetime.date.today()
    c = _conn()
    rows = c.execute("SELECT * FROM tasks").fetchall()
    c.close()
    if role == "admin":
        mine = [r for r in rows if r["assignee_email_idx"] == idx]
    elif role == "analista":
        mine = [r for r in rows if r["requester_email_idx"] == idx]
    else:
        mine = list(rows)
    out = []
    for r in mine:
        if r["status"] == "done" or not r["date"]:
            continue
        try:
            d = datetime.date.fromisoformat(r["date"])
        except Exception:
            continue
        diff = (d - today).days
        if diff < 0:
            out.append({"task": r["name"], "code": r["code"], "kind": "vencida",
                        "text": f'Vencida: "{r["name"][:30]}"', "days": diff})
        elif diff == 0:
            out.append({"task": r["name"], "code": r["code"], "kind": "hoy",
                        "text": f'Vence hoy: "{r["name"][:30]}"', "days": 0})
        elif diff == 1:
            out.append({"task": r["name"], "code": r["code"], "kind": "1dia",
                        "text": f'Falta 1 día: "{r["name"][:30]}"', "days": 1})
        elif diff == 3:
            out.append({"task": r["name"], "code": r["code"], "kind": "3dias",
                        "text": f'Faltan 3 días: "{r["name"][:30]}"', "days": 3})
    out.sort(key=lambda x: x["days"])
    return jsonify({"ok": True, "data": out})


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", "5000"))
    on_render = bool(os.environ.get("PORT"))  # Render define PORT; tu PC no
    if not on_render and "--no-browser" not in sys.argv:
        threading.Timer(1.2, open_browser).start()
    # 0.0.0.0 = escucha en toda la red, para que el tunel (cloudflared)
    # pueda alcanzar la app y otras personas entren por el enlace publico.
    app.run(host="0.0.0.0", port=port, debug=False)
