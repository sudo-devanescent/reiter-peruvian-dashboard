# Instrucciones para agentes (OpenCode)

Proyecto Django 5.2 único: web HTMX en `/`, admin en `/gestion/`, API de la app en `/api/v1/` y `worker_ia` como proceso aparte. Fuentes de verdad: `config/settings.py`, `web/permissions.py` y `web/messages.py` (no dupliques permisos ni textos en plantillas).

## Entorno y arranque
- `./scripts/iniciar.sh` (Linux/macOS) o `iniciar.bat` → `scripts/iniciar.ps1` (Windows) crea `.venv` y `.env` desde `.env.example`, migra, siembra demo la primera vez y arranca web + worker. Opciones: `DEMO=1`, `IA=1`, `SIN_WORKER=1`, `PUERTO=8080` (`-Demo`, `-IA`, `-SinWorker`, `-Puerto 8080` en Windows).
- `APP_ENV=dev` → SQLite, Cloudinary simulado, IA simulada, WhatsApp por consola. `APP_ENV=piloto` exige `DJANGO_SECRET_KEY` y `DATABASE_URL` (Supabase **session pooler**, puerto 5432) y fuerza HTTPS. Nunca subas `.env` ni secretos; no uses las claves anon/service_role ni crees tablas o RLS desde el panel de Supabase.
- `requirements.txt` fija Django 5.2.17 LTS: no subir a 6.x mientras simplejwt no lo soporte. `requirements-ia.txt` es opcional (detector ONNX). Python local 3.10–3.14; Docker 3.12.
- En dev no hace falta `collectstatic`; en piloto se ejecuta al construir la imagen (WhiteNoise con hash).

## Verificación
- Al terminar: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py test`.
- Enfocado: `python manage.py test web.tests.test_extras web.tests.test_views api simulador`. En pruebas se usan hash MD5 y un Cloudinary simulado con credenciales ficticias (`TESTING` en `config/settings.py`).
- `python manage.py diagnostico` (`--sin-color`, `--red`) y `python manage.py medir_rendimiento` para revisar configuración, red y tiempos.

## Reglas que se rompen (detalle en `docs/CONTEXTO_WEB.md` §§19–22 y `docs/adr/`)
- Sin CDN, npm ni frameworks JS: HTMX y Leaflet están en `web/static/web/vendor/`. Sin JS en línea (`<script>` sin `src`, `onclick=`): va en `app.js`, `caso.js` o `mapa.js`. `web/tests/test_extras.py` lo comprueba, junto con los iconos del sprite y la ausencia de secretos en el navegador.
- Toda vista de la web lleva `@web_view("permiso")`, salvo login/logout/cambio de contraseña; la matriz está en `web/permissions.py`. Los textos al usuario van en `web/messages.py`.
- La bandeja hace exactamente 6 consultas: no añadas consultas en `base.html` ni en `web/context_processors.py` (`test_bandeja_sin_consultas_n_mas_1`).
- La IA **sugiere indicios**, nunca diagnostica; los colores indican estado de revisión, nunca gravedad. No guardes URLs de fotos: genera URLs firmadas al mostrar.
- Números en atributos o CSS sin localizar (`|pctnum`, `|stringformat`; es-pe usa coma decimal).
- Decisiones de revisión: nunca editar ni borrar; las correcciones crean otra fila. Catálogos: desactivar, nunca borrar; los IDs no cambian. Tablas solo mediante migraciones.
- `sembrar_demo` solo en dev: con `APP_ENV=piloto` el comando falla con `CommandError`, incluido `--solo-catalogos`.

## Fuentes y despliegue
- `docs/REPORTE_AVANCE.md` (formato de la §23.2): añade una entrada al terminar cada tarea de la web (W-24). Los documentos `MAESTRO_WEB`/`MAESTRO_APP_MOVIL` que cita `CLAUDE.md` no están hoy en el repo; usa `docs/CONTEXTO_WEB.md` y `docs/adr/` como fuente de reglas.
- VPS: `cd /srv/riachuelo && git pull && bash deploy/actualizar.sh` reconstruye la imagen, aplica migraciones al arrancar y reinicia web + worker. No modifiques Traefik/OpenClaw; el usuario ejecuta los comandos del VPS, la IA no pide ni escribe contraseñas.
