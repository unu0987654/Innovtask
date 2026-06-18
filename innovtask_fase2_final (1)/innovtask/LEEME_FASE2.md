# INNOVTASK - Fase 2 COMPLETA (funcional + estetica)

## Login y cuentas
- Login real contra base de datos cifrada. 20 usuarios, 4 roles.
- PRIMER INGRESO: al entrar con la clave inicial (innovtask2026) el sistema
  OBLIGA a crear tu propia contrasena antes de continuar. Ya no hay "Crear cuenta".
- Cambio de contrasena cuando quieras (menu Tema > Sesion).
- Login con Google validado contra el backend (muestra tu foto de Gmail en el avatar).

## 4 roles
- analista  : solo solicita tareas a un admin. Sin analitica.
- coordinador: supervisa, ve todas las tareas.
- procesos  : todo lo del coordinador + PANEL DE EFECTIVIDAD con graficas
              (exclusivo Harold y German). La etiqueta ya dice "Procesos".
- admin     : ejecuta, actualiza estado/avance, recibe correo.

## Tareas
- Una tarea = un admin. Con HORA de inicio y fin opcionales.
- Tipo de proceso CA / Certificaciones / Otro, marcado o DETECTADO del texto.
- Aparecen en Tabla y Kanban (mismo filtrado en ambas).
- Correo real al admin al asignarle una tarea.

## IA (asistente, esquina inferior)
Responde con datos reales:
- "Que debo hacer ahora?" / "Mi resumen del dia" -> completadas hoy, pendientes,
  manana, y la siguiente tarea.
- "Que espacios libres tiene Alejandra hoy?" -> calcula huecos segun las horas.
- "Que hace Alejandra hoy?" / "Carga del equipo esta semana".
- Boton "Que debo hacer ahora?" en la Agenda de hoy.

## Calendario (tipo Google)
- Toca un dia para ver/agendar. Muestra tareas, eventos y FESTIVOS.
- Festivos de Colombia CALCULADOS para cualquier ano (2026, 2027, 2028...).

## Recordatorios inteligentes (campana)
- Avisa cuando faltan 3 dias, falta 1 dia, o la tarea esta vencida.

## Efectividad (Harold y German)
- KPIs de % por tipo + 5 graficas (efectividad, volumen, estados, tendencia,
  por administrador).

## Estetica
- Disponibilidad de un clic: toca el punto verde junto a tu avatar para rotar
  Disponible / Ocupado / En pausa.
- Personalizacion: mas colores (incluye rosa) y tipografias (incluida cursiva).
- Nombre corregido a People's Voice.

## Correr
cd backend
pip install -r requirements.txt
python app.py
# Entra con tu correo y la clave inicial innovtask2026 (te pedira cambiarla)

## Correo real (opcional): backend/db/smtp_config.json
{ "host":"smtp.gmail.com","port":587,"user":"tucuenta@gmail.com",
  "password":"clave de aplicacion 16 digitos","from_name":"INNOVTASK" }

## Ultimo paso pendiente
- Despliegue a la nube (Render) para que todo el equipo comparta datos.
