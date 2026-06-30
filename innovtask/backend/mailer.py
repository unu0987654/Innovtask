"""
mailer.py - Envio real de notificaciones por correo (SMTP).

Para no quedar "pegado" (bloqueado) al enviar, el envio corre en un hilo aparte.
Las credenciales se leen de db/smtp_config.json (NO se hardcodean en el codigo).

Ejemplo de smtp_config.json (Gmail con App Password):
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "tucuenta@gmail.com",
  "password": "xxxx xxxx xxxx xxxx",
  "from_name": "INNOVTASK"
}

Si el archivo no existe, el envio se simula (se registra en consola) para no romper la app.
"""
import os
import json
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "db", "smtp_config.json")


def _load_config():
    # 1) En la nube (Render): leer de variables de entorno.
    #    Asi no hay que subir ningun archivo de credenciales al repositorio.
    env_user = os.environ.get("SMTP_USER")
    env_pass = os.environ.get("SMTP_PASSWORD")
    if env_user and env_pass:
        return {
            "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            "port": int(os.environ.get("SMTP_PORT", "587")),
            "user": env_user,
            "password": env_pass,
            "from_name": os.environ.get("SMTP_FROM_NAME", "INNOVTASK"),
        }
    # 2) En local: leer del archivo db/smtp_config.json (como antes).
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _send_sync(to_email, subject, body_html):
    cfg = _load_config()
    if not cfg:
        print(f"[MAILER:SIMULADO] Para: {to_email} | Asunto: {subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg.get('from_name','INNOVTASK')} <{cfg['user']}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["user"], [to_email], msg.as_string())
        server.quit()
        print(f"[MAILER:OK] Enviado a {to_email}")
        return True
    except Exception as e:
        print(f"[MAILER:ERROR] {e}")
        return False


def send_notification(to_email, subject, body_html):
    """Dispara el correo en un hilo aparte para no bloquear la app (anti-pegado)."""
    t = threading.Thread(target=_send_sync, args=(to_email, subject, body_html), daemon=True)
    t.start()


def build_task_email(admin_name, task_name, requester_name, prio):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;
         border:1px solid #E0F0FB;border-radius:12px;overflow:hidden">
      <div style="background:#0D2E5A;color:#fff;padding:18px 24px">
        <strong style="font-size:18px">INNOVTASK</strong>
        <div style="font-size:11px;opacity:.7;letter-spacing:.1em">PEOPLE'S VOICE</div>
      </div>
      <div style="padding:24px;color:#0D2E5A">
        <p>Hola <strong>{admin_name}</strong>,</p>
        <p>Tienes una nueva tarea asignada en INNOVTASK:</p>
        <div style="background:#F4F9FF;border-left:4px solid #1A5FA8;padding:12px 16px;
             border-radius:6px;margin:14px 0">
          <strong>{task_name}</strong><br>
          <span style="font-size:13px;color:#4A7FA8">
            Solicitada por: {requester_name} &nbsp;·&nbsp; Prioridad: {prio.upper()}
          </span>
        </div>
        <p style="font-size:13px;color:#4A7FA8">
          Ingresa a la aplicacion para ver los detalles y actualizar el estado.
        </p>
      </div>
    </div>
    """
