# Despliegue en k3s (local, académico)

Adaptación de `reiter-pod.yaml` a manifiestos Kubernetes para k3s. Entorno local `APP_ENV=dev`. No usa `piloto`, Supabase, Cloudinary real ni WhatsApp real. No modifica código de la aplicación.

## Arquitectura

| Recurso | Nombre | Detalle |
|---|---|---|
| Namespace | `reiter` | Aísla todos los recursos |
| ConfigMap | `reiter-db-init` | `01-roles.sql` idempotente: crea roles `anon` y `authenticated` (NOLOGIN) |
| PVC | `reiter-pgdata` | 1Gi, RWO, StorageClass `local-path` (default), montado en `/var/lib/postgresql/data` |
| PVC | `reiter-media` | 1Gi, RWO, StorageClass `local-path`, compartido por web y worker en `/app/media` |
| Service | `reiter-web` | NodePort `8000:30800/TCP` |
| Deployment | `reiter` | `replicas: 1`, `strategy: Recreate`, 1 initContainer + 3 contenedores |

Contenedores del Pod:

| Contenedor | Imagen | Usuario | Rol |
|---|---:|---:|---|
| `fix-media-perms` (init) | `localhost/reiter-app:latest` | root (0) | `chown -R 10001:10001 /app/media` antes de arrancar la app |
| `db` | `docker.io/library/postgres:16` | imagen | PostgreSQL; `PGDATA=/var/lib/postgresql/data/pgdata` |
| `web` | `localhost/reiter-app:latest` | 10001 | `migrate --noinput` en bucle, luego gunicorn en `:8000`; readinessProbe `/api/v1/health` |
| `worker` | `localhost/reiter-app:latest` | 10001 | espera `migrate --check`, luego `python manage.py worker_ia` |

Los 3 contenedores comparten red del Pod: la BD se alcanza en `127.0.0.1:5432`. `media` es un volumen compartido.

## Prerrequisitos

- k3s instalado (este entorno: v1.37.2+k3s1, sin Traefik).
- `kubectl` configurado (`KUBECONFIG` exportado).
- StorageClass por defecto disponible (`local-path` en k3s).
- Puerto 30800 libre en el host.
- Imagen `localhost/reiter-app:latest` disponible en containerd de k3s (namespace `k8s.io`).

Importar imagen tras construirla con Podman (requiere sudo):

```bash
podman save localhost/reiter-app:latest | sudo k3s ctr -n k8s.io images import -
```

Verificar (puede requerir sudo según configuración):

```bash
sudo k3s ctr -n k8s.io images ls | grep reiter-app
```

## Aplicar

```bash
kubectl apply -f reiter-k3s.yaml
```

## Verificar

```bash
kubectl -n reiter get pods,svc,pvc -o wide
kubectl -n reiter logs deploy/reiter -c db --tail=80
kubectl -n reiter logs deploy/reiter -c web --tail=80
kubectl -n reiter logs deploy/reiter -c worker --tail=80
curl -sI http://127.0.0.1:30800/
curl -sI http://127.0.0.1:30800/api/v1/health
curl -sI http://127.0.0.1:30800/ingresar/
# obtener CSS enlazado y comprobarlo
curl -s http://127.0.0.1:30800/ingresar/ | grep -oE 'href="[^"]+\.css[^"]*"'
curl -sI http://127.0.0.1:30800/static/web/app.css
kubectl -n reiter exec deploy/reiter -c web -- python manage.py check
kubectl -n reiter exec deploy/reiter -c db -- psql -U postgres reiter -c "\du"
```

Esperado: pod `3/3 Running`, reinicios 0 tras estabilizar; `/` 302, `/api/v1/health` 200, `/ingresar/` 200, CSS 200; `check` sin issues; `anon` y `authenticated` con `Cannot login`.

## Crear superusuario

No se ejecuta automáticamente (interactivo):

```bash
kubectl -n reiter exec -it deploy/reiter -c web -- python manage.py createsuperuser
```

## Cargar datos demo

Idempotente: si ya hay sesiones, no agrega evidencia salvo `--mas`.

```bash
kubectl -n reiter exec deploy/reiter -c web -- python manage.py sembrar_demo
```

Cuentas demo: `admin@demo.pe`, `especialista@demo.pe`, `supervisor@demo.pe`, `operador@demo.pe` (`Demo2026`), `temporal@demo.pe` (`Temp2026`), `bloqueado@demo.pe`, `pendiente@demo.pe`.

## Actualizar imagen tras rebuild

```bash
podman build --env STATICFILES_BACKEND=django.contrib.staticfiles.storage.StaticFilesStorage -t localhost/reiter-app:latest .
podman save localhost/reiter-app:latest | sudo k3s ctr -n k8s.io images import -
kubectl -n reiter rollout restart deploy/reiter
kubectl -n reiter rollout status deploy/reiter
```

## Detener / escalar a 0

```bash
kubectl -n reiter scale deploy/reiter --replicas=0
# volver a levantar
kubectl -n reiter scale deploy/reiter --replicas=1
```

## Reinicio total (destructivo)

**Borra datos/PVC**. Pedir confirmación antes de ejecutarlo.

```bash
kubectl delete namespace reiter
```

## Solución de problemas

- **ErrImageNeverPull / ImagePullBackOff** con `imagePullPolicy: Never`: la imagen no está en containerd de k3s. Importar con `podman save localhost/reiter-app:latest | sudo k3s ctr -n k8s.io images import -`. No usar sudo sin confirmación del usuario.
- **PVC Pending**: `local-path` usa `WaitForFirstConsumer`; debe pasar a `Bound` cuando el Pod se programa. Si persiste, revisar `kubectl -n reiter describe pvc ...` y logs de `local-path-provisioner` en `kube-system`.
- **Permisos en `/app/media`**: se usa `fsGroup: 10001`, `runAsUser: 10001` en web/worker y un initContainer root que hace `chown -R 10001:10001 /app/media`. Esto cubre el caso de `local-path` hostPath donde kubelet no aplica fsGroup. Si aun así falla, no pasar a root sin analizar; comprobar owner con `kubectl -n reiter exec deploy/reiter -c web -- ls -ld /app/media`.
- **CSRF / origen**: `APP_ENV=dev` tiene `ALLOWED_HOSTS=["*"]` y `CSRF_TRUSTED_ORIGINS=[]`, por lo que `http://localhost:30800` funciona sin cambios. `PUBLIC_BASE_URL` se fija a `http://localhost:30800` en el YAML.
- **Web no lista**: revisar readinessProbe y logs `web`; la sonda usa `/api/v1/health`.
- **Worker sin modelo activo**: normal antes de `sembrar_demo`; tras cargar demo debe quedar el detector simulado listo.

## Decisiones tomadas

- **Deployment Recreate + 3 contenedores en el mismo Pod**: conserva `127.0.0.1:5432` y el volumen `media` compartido, igual que el diseño Podman.
- **Sin `hostPort`; Service NodePort 30800**: acceso estable por servicio Kubernetes.
- **`PGDATA=/var/lib/postgresql/data/pgdata`**: evita problemas con el punto de montaje raíz del volumen.
- **`runAsUser: 10001` + `fsGroup: 10001` + initContainer `chown`**: web/worker sin root; el initContainer root solo ajusta permisos del volumen local-path antes de arrancar.
- **`--no-control-socket` en gunicorn**: el home de uid 10001 en la imagen es `/app` (no escribible cómodamente para el control socket por defecto de gunicorn en `/root` en otros contextos); evita fallo de arranque por permisos. No cambia la lógica de la app.
- **`readinessProbe` HTTP `/api/v1/health`**; sin liveness agresiva.
- **`PUBLIC_BASE_URL=http://localhost:30800`**; en dev no requiere cambios de ALLOWED_HOSTS/CSRF.
- **Mismo `env` duplicado** en web y worker, sin aliases YAML.
- **Imagen con `STATICFILES_BACKEND=django.contrib.staticfiles.storage.StaticFilesStorage`**: heredada del build existente; workaround por `web/static/web/img/hoja.svg` faltante. No se tocó código.
