# INNOVTASK - Backend seguro (Fase 1)

## Que ya funciona y esta probado
- Servidor Flask que sirve el frontend y expone la API REST.
- Base de datos SQLite con los 20 usuarios reales sembrados.
- 4 roles: coordinador (6), procesos (2: Harold y German), admin (3), analista (9).
- Login real contra la BD (rechaza contrasena incorrecta).
- Privacidad de datos: correos y nombres CIFRADOS en reposo (AES/Fernet);
  contrasenas en hash PBKDF2. Verificado: "peoplesvoice" no aparece en claro
  en el archivo de la BD.
- Envio de correo por SMTP REAL en hilo aparte (no bloquea / no se queda pegado).
  Lee credenciales de backend/db/smtp_config.json (no hardcodeadas).
- Endpoints listos: /api/login, /api/users, /api/tasks (GET/POST/PUT/DELETE),
  /api/effectiveness (solo procesos), /api/admin-summary (hoy/semana),
  /api/notifications.

## Contrasena inicial de todos los usuarios
innovtask2026  (se puede cambiar luego)

## Para correr
cd backend
pip install -r requirements.txt
python app.py
# abre http://127.0.0.1:5000

## Correo real (opcional, para la prueba con alejandra.gomez)
Crear backend/db/smtp_config.json:
{
  "host": "smtp.gmail.com",
  "port": 587,
  "user": "TU_CUENTA@gmail.com",
  "password": "APP_PASSWORD_DE_GMAIL",
  "from_name": "INNOVTASK"
}
Sin este archivo, el envio se simula en consola (no rompe la app).

## Lo que falta (siguientes fases)
- Conectar el frontend a la API (hoy aun usa localStorage).
- Vistas/permisos por los 4 roles en el front.
- Paneles de "procesos": indices detallados, % efectividad,
  asignacion contextual_assessment / certificaciones.
- Resumen "que hace cada admin hoy / esta semana".
- Arreglar todos los botones (el de Filtrar es solo decorativo hoy).
- Empaquetado a .exe con PyInstaller.
