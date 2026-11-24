# Contenerización del proyecto (Podman + kube play)

Documento de trabajo académico, entorno local (`APP_ENV=dev`). No usa `piloto`, Supabase, Cloudinary real ni WhatsApp real. No modifica código de la aplicación.

## Arquitectura

| Contenedor | Imagen | Rol | Puerto | Persistencia |
|---|---|---|---|---|
| `reiter-db` | `docker.io/library/postgres:16` | Base de datos PostgreSQL | 5432 solo dentro del pod | PVC `reiter-pgdata` en `/var/lib/postgresql/data` |
| `reiter-web` | `localhost/reiter-app:latest` | Web + API: espera BD, ejecuta migraciones y arranca gunicorn | `8000:8000` en el host | PVC `reiter-media` en `/app/media` |
| `reiter-worker` | `localhost/reiter-app:latest` | Worker IA: espera migraciones aplicadas y ejecuta `worker_ia` | sin puertos | PVC `reiter-media` en `/app/media` |

Los tres contenedores corren en el pod `reiter` y comparten red: la base se alcanza en `127.0.0.1:5432`. Solo `web` ejecuta migraciones; `worker` espera con `migrate --check`. La imagen propia se construye con el `Dockerfile` existente.

## Prerrequisitos

- Podman 4.x o superior con soporte `kube play` (ConfigMap, PVC, `securityContext`, `hostPort`). Verificado: Podman 6.2.0, rootless.
- Puerto `8000` libre en el host.
- Red para descargar imágenes base y paquetes Python durante el build.
- Espacio en disco suficiente para la imagen (~390 MB) y las capas de build.

## Construir la imagen

Desde la raíz del repo:

```bash
podman build --env STATICFILES_BACKEND=django.contrib.staticfiles.storage.StaticFilesStorage -t localhost/reiter-app:latest .
```

> **Nota:** el `--env STATICFILES_BACKEND=...` es un workaround de build. El `Dockerfile` ejecuta `collectstatic` con el backend de manifiesto de WhiteNoise; en el estado actual del repo, `web/static/web/app.css` referencia `web/img/hoja.svg`, que no existe, y `collectstatic` falla. La variable ya está soportada por `config/settings.py:166` y evita tocar código. El workaround no cambia la lógica de la app en ejecución.

## Arrancar

```bash
podman kube play reiter-pod.yaml
```

Crea el ConfigMap `reiter-db-init` (roles `anon` y `authenticated`, NOLOGIN, idempotente), los PVC `reiter-pgdata` y `reiter-media`, y el pod `reiter`.

## Verificar

```bash
podman pod ps
podman ps -a --pod
podman logs --tail 60 reiter-db
podman logs --tail 60 reiter-web
podman logs --tail 60 reiter-worker
curl -sI http://127.0.0.1:8000/
curl -sI http://127.0.0.1:8000/api/v1/health
podman exec reiter-web python manage.py check
podman exec reiter-db psql -U postgres reiter -c "\du"
```

Esperado: 3 contenedores `Running`, sin reinicios en bucle; web responde `302` en `/` y `200` en `/api/v1/health`; `check` sin issues; `\du` muestra `anon` y `authenticated` con `Cannot login`.

## Crear superusuario

No se ejecuta automáticamente (requiere entrada interactiva). Comando exacto:

```bash
podman exec -it reiter-web python manage.py createsuperuser
```

## Cargar datos demo

El comando es idempotente para los catálogos y usuarios; si ya hay sesiones, no agrega evidencia salvo `--mas`.

```bash
podman exec reiter-web python manage.py sembrar_demo
```

Cuentas demo creadas por el comando: `admin@demo.pe`, `especialista@demo.pe`, `supervisor@demo.pe`, `operador@demo.pe` (contraseña `Demo2026`), `temporal@demo.pe` (`Temp2026`), `bloqueado@demo.pe`, `pendiente@demo.pe`.

## Detener, recrear y reinicio total

Detener y eliminar el pod (conserva volúmenes/PVC):

```bash
podman kube down reiter-pod.yaml
```

Volver a levantar (reutiliza datos existentes):

```bash
podman kube play reiter-pod.yaml
```

Reinicio total **destructivo** (borra datos): requiere confirmación previa. No lo ejecutes sin pedirla.

```bash
# DESTRUCTIVO: elimina volúmenes y datos
podman kube down reiter-pod.yaml
podman volume rm reiter-pgdata reiter-media
```

## Solución de problemas

- **`web` o `worker` en bucle esperando BD/migraciones:** revisar `podman logs reiter-db` y `podman logs reiter-web`. La BD tarda unos segundos en inicializar el primer arranque.
- **Puerto 8000 ocupado:** `ss -ltn | grep 8000`; detener el proceso que lo usa o cambiar `hostPort` en `reiter-pod.yaml` (y `PUBLIC_BASE_URL`).
- **`collectstatic` falla por `hoja.svg`:** usar el comando de build con `--env STATICFILES_BACKEND=...` indicado arriba. Es un problema del código/CSS, no del despliegue.
- **Permisos sobre `/app/media` o datos de Postgres:** en rootless, `runAsUser: 0` en el contenedor mapea al usuario del host; es la configuración usada en `web` y `worker`. Si `db` falla por permisos de volumen, la corrección mínima sería añadir `securityContext.runAsUser: 0` también a `db`.
- **El worker avisa “No hay modelo de IA activo”:** esperado en un entorno recién migrado sin datos demo. Tras `sembrar_demo` carga el modelo demo y queda listo.
- **Ver estado real de contenedores:** `podman ps -a --pod --format '{{.Names}} {{.Status}} {{.RestartCount}}'` (si el formato está disponible) o revisar `podman ps -a --pod`.

## Decisiones tomadas

- **`reiter-pod.yaml` y `CONTENERIZACION.md`** son los únicos archivos creados; no se modificó código, Dockerfile, `.dockerignore`, `.env*`, `deploy/`, `AGENTS.md`, ni archivos existentes.
- **`runAsUser: 0` en `web` y `worker`:** la imagen corre como uid 10001; en Podman rootless, uid 0 dentro del contenedor mapea al usuario del host, permitiendo escribir en los PVC montados.
- **`MEDIA_ROOT` = `/app/media`:** confirmado desde `config/settings.py` (`BASE_DIR=/app`), coherente con el `mountPath`.
- **`worker_ia` sin flags extra:** corre en bucle indefinido por defecto; `--once` solo es para pruebas.
- **`DB_SSLMODE=disable`:** PostgreSQL local dentro del pod sin TLS; el default de settings es `require`.
- **Roles `anon`/`authenticated`:** creados por init script idempotente del ConfigMap; necesarios para `auditoria/seguridad_bd.py` post-migrate y diagnóstico.
- **Build con `--env STATICFILES_BACKEND=...`:** workaround por el asset faltante `web/img/hoja.svg` referenciado desde `app.css`. No se tocó código de la app; se documenta como problema detectado.
- **No se ejecutó `createsuperuser`:** se dejó comando exacto.
- **Limpieza menor realizada:** se eliminaron imágenes `<none>` generadas por el build fallido inicial (artefactos del propio intento, sin datos).
