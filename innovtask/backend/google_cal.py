"""
google_cal.py - Integracion con Google Calendar (solo LECTURA).

No usa las librerias pesadas de Google; hace las peticiones HTTP directas con
urllib (incluido en Python), para que el despliegue en Render sea liviano y sin
dependencias extra.

Flujo OAuth (autorizacion):
  1) El usuario hace clic en "Conectar Google Calendar".
  2) Se le redirige a Google para que autorice (solo lectura de su calendario).
  3) Google devuelve un "code" a /oauth/google/callback.
  4) Cambiamos ese code por tokens (access_token + refresh_token).
  5) Guardamos el refresh_token cifrado en la BD, asociado al usuario.
  6) Cuando se necesitan eventos, usamos el refresh_token para pedir un
     access_token nuevo y consultar la API de Calendar.

Variables de entorno necesarias (se configuran en Render):
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI   (ej: https://innovtask.onrender.com/oauth/google/callback)
"""
import os
import json
import urllib.parse
import urllib.request
import datetime

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
)
# Solo lectura del calendario
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


def _client_id():
    return os.environ.get("GOOGLE_CLIENT_ID", "")


def _client_secret():
    return os.environ.get("GOOGLE_CLIENT_SECRET", "")


def _redirect_uri():
    return os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "https://innovtask.onrender.com/oauth/google/callback",
    )


def is_configured():
    """True si las credenciales de Google estan disponibles."""
    return bool(_client_id() and _client_secret())


def build_auth_url(state):
    """Construye la URL a la que se envia al usuario para autorizar."""
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",      # para recibir refresh_token
        "prompt": "consent",           # asegura refresh_token la primera vez
        "state": state,                # para identificar al usuario al volver
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def exchange_code(code):
    """Cambia el 'code' de Google por tokens. Devuelve el dict de la respuesta."""
    return _post_form(TOKEN_URL, {
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    })


def refresh_access_token(refresh_token):
    """Obtiene un access_token nuevo a partir del refresh_token guardado."""
    return _post_form(TOKEN_URL, {
        "refresh_token": refresh_token,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "grant_type": "refresh_token",
    })


def list_events(access_token, days_ahead=30):
    """Lee los proximos eventos del calendario principal del usuario.
    Devuelve una lista simplificada: [{title, date, start, end, all_day}]."""
    now = datetime.datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + datetime.timedelta(days=days_ahead)).isoformat() + "Z"
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
    }
    url = CALENDAR_EVENTS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + access_token)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = []
    for it in data.get("items", []):
        start = it.get("start", {})
        end = it.get("end", {})
        # eventos de dia completo usan 'date'; con hora usan 'dateTime'
        if "date" in start:
            day = start["date"]
            out.append({
                "title": it.get("summary", "(sin titulo)"),
                "date": day,
                "start": "",
                "end": "",
                "all_day": True,
            })
        else:
            dt = start.get("dateTime", "")
            day = dt[:10] if dt else ""
            hhmm = dt[11:16] if len(dt) >= 16 else ""
            edt = end.get("dateTime", "")
            ehhmm = edt[11:16] if len(edt) >= 16 else ""
            out.append({
                "title": it.get("summary", "(sin titulo)"),
                "date": day,
                "start": hhmm,
                "end": ehhmm,
                "all_day": False,
            })
    return out
