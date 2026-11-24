# Informe de análisis técnico — Reiter Peruvian Berry S.A.C.

**Fecha:** 21 de noviembre de 2026  
**Alcance:** código, arquitectura, pruebas, base de datos, despliegue, documentación y operación.  
**Estado:** análisis en solo lectura sobre el repositorio. No se ha editado ningún archivo del proyecto salvo este informe. Los cambios previos (`AGENTS.md` y `AGENTS.md.bak`) siguen intactos. El antiguo `informe_proyecto.md` ya no está en el directorio de trabajo; no lo he borrado yo.

> Este informe sustituye a la versión anterior del mismo día. La novedad principal es que la verificación se ha repetido contra **PostgreSQL 16.16**, no solo contra SQLite. Eso ha permitido ejecutar las pruebas de seguridad de base de datos que antes se omitían, ha destapado un fallo nuevo y ha dejado el diagnóstico en verde con la configuración correcta.

---

## 1. Resumen ejecutivo

Seguimos ante un proyecto serio, no ante un prototipo. La web de revisión, la API de la app móvil y el worker de IA están bien separados; las reglas de negocio viven en servicios, la matriz de permisos es única, la auditoría es inmutable y la concurrencia está resuelta con bloqueos y colas en la propia base de datos. Las decisiones importantes están además documentadas en nueve ADR.

La buena noticia de esta pasada es que **la capa de base de datos resiste la revisión con PostgreSQL real**: RLS activo en todas las tablas, roles de la Data API sin permisos, disparador de solo inserción en la auditoría y 50 restricciones `CHECK` funcionando. Las cinco pruebas específicas de seguridad pasan. Las ocho pruebas del detector ONNX también pasan una vez instaladas las dependencias opcionales. Ya no queda ninguna prueba omitida.

La mala noticia es que la suite sigue en rojo: **240 pruebas, 11 fallos, 0 omitidas**. Diez son las regresiones conocidas de la web; el undécimo es nuevo y solo aparece con PostgreSQL: una prueba asume un orden alfabético que en SQLite sale de una forma y en PostgreSQL de otra por la colación del cluster. Es un problema de portabilidad de la prueba, no de la regla de negocio.

El veredicto no cambia en lo esencial: **no hay un problema de arquitectura**. Hay diez regresiones de entrega, una prueba dependiente de colación, brechas de autorización en la API y un despliegue que todavía no sabe hacer copias ni retroceder. Con la suite en verde, CI sobre PostgreSQL 16 y un runbook de respaldo, el proyecto quedaría en condiciones reales de piloto.

---

## 2. Qué se ha ejecutado exactamente

Todo se ha hecho con `.venv/bin/python` (Python 3.12.16, Django 5.2.17). El `python` del sistema no tiene Django. Para PostgreSQL se levantó un contenedor desechable con la imagen que ya estaba descargada:

```bash
podman run -d --name riachuelo-pg16-check \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=riachuelo_local_test \
  -e POSTGRES_DB=riachuelo_test -p 5433:5432 docker.io/library/postgres:16
```

La URL usada fue `postgresql://postgres:riachuelo_local_test@127.0.0.1:5433/riachuelo_test` con `DB_SSLMODE=disable`, porque es un contenedor local sin TLS. El servidor responde como **PostgreSQL 16.16 (Debian 16.16-1.pgdg13+1)**.

| Comprobación | SQLite (situación inicial) | PostgreSQL 16 (esta pasada) |
|---|---|---|
| `manage.py check` | 0 errores, 1 aviso `riachuelo.W008` | Igual |
| `manage.py makemigrations --check --dry-run` | `No changes detected` | Igual |
| `manage.py comprobar_bd` | — | Conectado en 12–20 ms, contraseña enmascarada |
| `manage.py migrate --noinput` | No ejecutado para no tocar la BD del usuario | 57 migraciones aplicadas en el contenedor de prueba |
| `manage.py test` | 240 pruebas · **10 fallos** · 13 omitidas · 6,7 s | 240 pruebas · **11 fallos** · **0 omitidas** · 24 s |
| `manage.py diagnostico` | 8 correctos · 3 avisos · 7 errores | **22 correctos · 6 avisos · 0 errores** con datos demo y `DJANGO_DEBUG=true` |
| `manage.py medir_rendimiento` | No ejecutable sin datos | Ejecutado con datos demo; tabla de tiempos más abajo |

Para llegar a cero omitidas hicieron falta dos cosas que el entorno local no tenía: los roles `anon` y `authenticated` que existen en Supabase (se crearon solo dentro del contenedor) y las dependencias opcionales de IA. El venv no traía `pip`, así que se arrancó con `ensurepip` y se instaló `requirements-ia.txt`: quedaron numpy **2.5.5** y onnxruntime **1.32.0**.

Con eso, las cinco pruebas de `auditoria.tests.test_seguridad_bd` terminan en `OK`, y las ocho pruebas de inferencia ONNX pasan también. Conviene dejar constancia de un detalle: esas versiones son el resultado de `numpy>=2.0` y `onnxruntime>=1.20`, sin fijar. Una reconstrucción futura puede traer otras.

---

## 3. Lo que ha cambiado respecto al informe anterior

Hay cuatro puntos que conviene dejar claros porque corrigen afirmaciones que se hicieron antes:

1. **Ya no se pueden dar por “no verificadas” las defensas de base de datos.** Con SQLite se omitían 13 pruebas; con PostgreSQL y los roles de Supabase creados, se ejecutan las 240 y no queda ninguna omitida. RLS, trigger y `CHECK` están comprobados de verdad.
2. **Aparece un fallo nuevo que SQLite no veía**, en `campo.tests.test_catalogos.Segmentos.test_dividir_reemplaza_y_conserva_historia`. Es por la colación del cluster (`en_US.utf8`), no por la lógica de división de hileras.
3. **La matriz de permisos tiene 18 entradas, no 19.** El 19 venía del informe del 19/11.
4. **Las “seis consultas” son por petición HTTP, no por pantalla completa.** La prueba mide el GET principal; la bandeja además pide el fragmento de descartadas por HTMX al cargar y al cambiar filtros.

Sobre el locale `es-pe`: Django sí lo resuelve al locale español, que usa coma decimal. El problema real es que el filtro `pctnum()` está deliberadamente sin localizar y se usa como texto visible.

---

## 4. El fallo nuevo: una prueba que depende de la colación

La prueba divide una hilera en tres segmentos y comprueba el orden de los marcadores activos. Espera esto:

```text
H05 S1 inicio, H05 S2 inicio, H05 S3 inicio, H05 fin
```

En SQLite sale así. En PostgreSQL con `en_US.utf8`, la comparación `‘H05 fin’ < ‘H05 S1 inicio’` es **verdadera**, así que el marcador final aparece primero y la prueba falla:

```text
H05 fin, H05 S1 inicio, H05 S2 inicio, H05 S3 inicio
```

La lógica de negocio está bien: los segmentos son `(1,129)`, `(130,257)` y `(258,385)`, los antiguos quedan inactivos y la división funciona. Lo que ocurre es que `order_by("code")` delega el orden al locale de la base. Supabase también usa PostgreSQL, así que este orden puede cambiar entre entornos y afectar al plano y al mapa, no solo al test.

La solución limpia es dar un **orden semántico explícito** —por posición (`INICIO`, intermedios, `FIN`) o con un `Case/When`— en lugar de depender de `code`. Si el orden no importa para esa comprobación, basta con hacer la aserción independiente del orden (`assertCountEqual`) y dejar la ordenación visual para otro sitio. Lo que no conviene es cambiar la colación de la base para que el test pase.

---

## 5. Cómo está montado el sistema

Hay una imagen Docker única para la web, la API y el worker. En desarrollo se usan SQLite, Cloudinary simulado, detector simulado y WhatsApp por consola. En piloto se exigen `DJANGO_SECRET_KEY` y `DATABASE_URL`, se fuerza HTTPS y se conecta a Supabase mediante *session pooler* en el puerto 5432.

El recorrido de una foto es este:

```text
App móvil (JWT + X-Device-Id)
  → sincroniza sesiones, pasadas, secuencias e incidencias (idempotente por UUID)
  → pide un ticket firmado para subir la imagen
  → sube directamente a Cloudinary (o usa el multipart antiguo)
  → confirma la captura: Capture + QualityResult + AiTask en una transacción
  → worker_ia reclama la tarea con SKIP LOCKED y aplica el detector
  → guarda cajas, aplica triage y abre un caso por lugar (con dos cámaras)
  → el especialista decide o corrige; la corrección crea otra fila
  → se encola el aviso de WhatsApp y se envía
  → cada paso deja un evento de auditoría con su traceId
```

La web usa HTMX para fragmentos, con sondeos de 15 segundos en la bandeja y 20 en la actividad. HTMX y Leaflet están dentro del repo. Las URLs de las fotos no se guardan nunca: se firman al mostrar.

---

## 6. Lo que está especialmente bien hecho

Conviene decirlo antes de entrar en los problemas, porque es mucho:

- **Autorización centralizada.** `web/permissions.py` concentra 18 permisos y `@web_view` se ejecuta antes que la validación del método HTTP. La prueba de rutas lo comprueba.
- **Servicios como única fuente de reglas.** Web, admin y comandos llaman a las mismas funciones.
- **Bandeja con presupuesto fijo**: seis consultas por petición, defendidas por una prueba.
- **Concurrencia bien resuelta**: `select_for_update`, `SKIP LOCKED`, leases, reintentos con espera y códigos 409 para decisiones obsoletas.
- **Auditoría inmutable**, con un disparador PostgreSQL que impide editar o borrar eventos y con `traceId` en cada paso.
- **Seguridad de base de datos en capas**, verificada ahora en PostgreSQL: RLS sin políticas, `REVOKE` a `anon`/`authenticated`, *default privileges* y 50 `CHECK` generados desde los `TextChoices`.
- **Idempotencia real** por UUID del lado de la app, con constraints parciales y un cursor de borrados que no salta filas con la misma marca de tiempo.
- **Decisiones inmutables**: una corrección crea una fila nueva con `supersedes`.
- **Catálogos desactivables**, con identificadores estables.
- **Paridad dev/piloto muy cuidada**: Cloudinary, IA y WhatsApp tienen versiones simuladas.
- **Contenedor muy aislado**: usuario sin privilegios, sistema de archivos de solo lectura, sin capacidades de Linux, límites de memoria y CPU, logs con tope y Traefik intacto.
- **Diagnóstico muy completo**: ocho bloques, explicaciones accionables y código de salida.

---

## 7. Hallazgos P0 — antes de cualquier piloto real

### 7.1 Las once pruebas en rojo

Diez son regresiones de texto o de marca de las mejoras visuales de noviembre; la undécima es la de colación ya explicada.

| Prueba | Qué falla |
|---|---|
| `campo.tests.test_catalogos...dividir_reemplaza...` | Orden de marcadores distinto por colación (`en_US.utf8`). **Nueva con PostgreSQL.** |
| `revision.tests.test_dos_camaras...` | El texto sobre “la otra cámara” ya no coincide. |
| `web.tests.test_avisos_simulados...` | No aparece “Simulado (no enviado)”. |
| `web.tests.test_descartadas_ia...` (2) | Cambió el formato de confianza y umbral; falta “máx. 0,35”. |
| `web.tests.test_extras...` | `base.html` referencia `apple-touch-icon.png`, que no existe. También falta `favicon.ico`. |
| `web.tests.test_views...` (2 de administración) | Desaparecieron “Reglas de las cuentas” y el texto completo de la contraseña temporal. |
| `web.tests.test_views...` (2 de caso) | `caso.html` no renderiza `aviso_ia` ni incluye el panel de decisión del supervisor. |
| `web.tests.test_views...` (matriz de permisos) | `modulos_casetas` no lleva `@web_view`. |

El caso de `modulos_casetas` es el único con consecuencias de seguridad. Está en `web/views.py:898-900` con `@login_required`, así que cualquier usuario autenticado puede entrar. `@web_view` hace más cosas: obliga a cambiar la contraseña cuando hace falta, exige el rol correcto y redirige bien las peticiones HTMX al caducar la sesión. Todo eso se salta. Además, el enlace del menú está fuera de cualquier `{% if puede... %}` y aparece para todos los roles. La pantalla hoy es estática, pero es una puerta abierta en cuanto reciba datos. Lo natural es añadir `sesiones.ver` a la matriz, cambiar el decorador y proteger el enlace.

Con los textos hay que decidir cuál es la redacción definitiva y ponerla en `web/messages.py`. Si el texto nuevo es el deseado, se actualizan las pruebas; si el antiguo era un requisito, se restaura en la plantilla. Lo que no debe pasar es que el mismo mensaje viva en varios sitios.

### 7.2 API y ciclo de vida de credenciales

El contrato está muy bien trazado —JWT con rotación y lista negra, `X-Device-Id`, idempotencia, errores uniformes con `traceId` y roles separados—, pero hay brechas reales:

**Cambiar la contraseña desde la app no revoca los refresh tokens.** `app_change_password` actualiza la contraseña y el flag, pero no llama a la lista negra. Un refresh robado seguiría válido catorce días. El cambio desde el administrador sí lo hace.

**El dispositivo autenticado se recibe pero no se usa.** `SessionUpsertView` pasa `request.device_id` a `upsert_session`, y el servicio lo ignora: crea dispositivos con lo que viene en el cuerpo y solo comprueba que los usuarios existan, sin mirar rol ni estado. Cualquier token de campo puede atribuir una sesión a otro operador. Es el hallazgo más delicado de la API.

**El límite de intentos mira la IP equivocada.** Detrás de Traefik, Django ve la IP del proxy. Los límites de 10 login/minuto y 10 reset/hora pueden volverse globales para toda la flota.

**La subida v2 no verifica el MD5 real.** El ticket firma `publicId` y tiempo; la confirmación coteja `publicId`, bytes y firma de Cloudinary. El `md5` que envía la app se guarda, pero nunca se contrasta con el contenido subido.

Otros detalles que conviene conocer:

| Hallazgo | Por qué importa |
|---|---|
| Reasignar un dispositivo a otro usuario no revoca las sesiones anteriores. | El celular viejo conserva credenciales válidas. |
| `X-Device-Id` es opcional en el autenticador, aunque la doc lo diga obligatorio. | Contrato y código no coinciden. |
| El logout revoca un solo refresh, no todos los del dispositivo. | El esquema promete “del dispositivo”. |
| `must_change_password` se expone en `/auth/me` pero no se exige en la API. | Se puede operar con contraseña temporal. |
| En dev, la miniatura de “Ubicar plaga” apunta a `/dev/media/...`, que exige sesión web. | La app recibe 403; la prueba no lo ve porque usa Cloudinary falso. |
| `since` sin zona horaria se compara con fechas con zona. | Avisos de Django y cursor posiblemente incorrecto. |
| `GET /captures/{id}` no comprueba propiedad ni devuelve 410 tras borrado. | Respuestas coherentes solo a medias. |
| `pest-reports` no pagina de verdad (tope 500) y firma una URL por fila. | Coste creciente con muchos casos. |
| El correo de reset es `CharField` y un `except Exception` silencia fallos. | Entradas basura y fallos invisibles. |
| Campos desconocidos solo avisan por consola. | Decisión deliberada, pero puede esconder deriva app/servidor. |
| OpenAPI no declara `X-Device-Id` y dice versión 1.0.0 frente al contrato 2.0. | Documentación automática desactualizada. |
| `_catalog_version` guarda entradas en caché sin TTL. | Crece con cada contenido distinto tras `cache.clear()`. |
| La guía de integración no menciona `/mobile/deleted-captures` ni los 410. | La app puede no enterarse de borrados. |

### 7.3 Operación: copias, migraciones y despliegue

Es el punto que más preocuparía en un piloto con evidencia real.

**No hay una copia de seguridad ejecutable.** El comando `respaldo` usa `pg_dump`, pero la imagen no instala `postgresql-client`, el contenedor es de solo lectura y no hay volumen donde escribir el archivo. Supabase Free no incluye backups automáticos. Si se borra algo o falla una migración, no hay camino de vuelta.

**Las migraciones corren solas al arrancar**, sin copia previa. `actualizar.sh` reconstruye, reinicia y hace `image prune -f`, descartando la imagen anterior. Una migración fallida deja el sitio caído sin punto de restauración.

**El despliegue ignora el diagnóstico.** Tanto `actualizar.sh` como `instalar.sh` lo llaman con `|| true`. Aunque falte el modelo de IA o WhatsApp siga en consola, el script acaba como si nada. El `up -d` también lleva `|| true`, y el healthcheck busca el contenedor por el nombre literal `riachuelo-web-1`, que cambia si cambia el nombre del proyecto.

**El worker no tiene healthcheck ni alerta de cola.** Si el detector entra en bucle de error, la cola crece en silencio y solo se descubre ejecutando el diagnóstico a mano.

También está el cruce entre subida y capacidad: con `API_SUBIDA_MULTIPART=true`, fotos de hasta 10 MB y `/tmp` de 64 MB, Django vuelca a disco lo que pasa de 2,5 MB. Con ocho hilos trabajando a la vez, el tmpfs puede agotarse. Pasar al ticket v2 evita que las fotos pasen por el servidor.

Puntos operativos adicionales:

- La confianza del proxy HTTPS es muy amplia (`--forwarded-allow-ips=*`) y el firewall sigue pendiente.
- `CloudApiClient` asume que la respuesta de WhatsApp siempre trae `messages[0].id`; un 200 inesperado lanza un `KeyError` no capturado y deja el aviso bloqueado hasta que expire el lease.
- Las dependencias IA van con rangos y la imagen base es un tag flotante: esta misma pasada instaló numpy 2.5.5 y onnxruntime 1.32.0, pero una reconstrucción puede traer otras.
- `CSRF_COOKIE_HTTPONLY=False` amplía la exposición ante XSS sin una necesidad clara.
- El límite del endpoint de errores del navegador también depende de la IP del proxy.
- `TESTING = "test" in sys.argv` es frágil: cualquier comando con “test” en el nombre activa MD5 y Cloudinary falso.
- Un filtro de `warnings` oculta la falta de `staticfiles/` con `DEBUG=false`.
- `scripts/iniciar.sh` dice que admite Python 3.10–3.13, pero el código admite 3.14; y un `PUERTO` personalizado no se propaga a `PUBLIC_BASE_URL`.
- `medir_rendimiento` se cae con `ValueError: Missing staticfiles manifest entry for 'web/img/icon-logo.png'` si se ejecuta con `DEBUG=false` sin `collectstatic`. Funciona bien con `DJANGO_DEBUG=true`, pero el comando debería avisar en vez de terminar en traceback.
- No hay CI: todo depende de que alguien recuerde ejecutar las comprobaciones.

---

## 8. Hallazgos P1 — antes de escalar

### 8.1 Rendimiento, con números reales

Con los datos demo cargados en PostgreSQL, `medir_rendimiento` da estos resultados:

| Pantalla | Mediana | p95 | Consultas | KB |
|---|---:|---:|---:|---:|
| Bandeja (pendientes, pág. 1) | 60 ms | 66 ms | 6 | 77 |
| Bandeja (todos, confianza, pág. 50) | 56 ms | 60 ms | 6 | 67 |
| Caso | 180 ms | 184 ms | 12 | 20 |
| `mapa/datos` sin filtros | 17 ms | 19 ms | 6 | 4 |
| `mapa/datos` un lote, confirmados | 12 ms | 13 ms | 6 | 1 |
| Plano de un lote | 28 ms | 30 ms | 10 | 82 |
| Panel (30 días) | 17 ms | 17 ms | 7 | 16 |

La bandeja cumple el presupuesto de seis consultas también con PostgreSQL. La pantalla de caso es la más cara, con doce consultas y 180 ms, y es el sitio donde conviene mirar primero si hay que optimizar.

Hay además trabajo desperdiciado: el panel calcula ocho indicadores —lotes procesados, frecuencia de captura, porcentaje de rechazadas, tiempo medio de IA, cola, espera de decisión y otros— que **ninguna plantilla muestra**. `dashboard.html` dice “Pendiente de integración” y “Aún no se calcula la frecuencia de captura”. La frecuencia se calcula cargando todas las fechas del periodo en memoria; la media de intervalos consecutivos es `(máx - mín) / (n - 1)` y cabe en un solo agregado SQL. Con 100.000 fotos la diferencia es grande.

También hay un N+1 acotado en la cobertura por lote y un acoplamiento que conviene romper: la API importa `web.queries.map_layers`. Ese servicio debería vivir en `campo` o en un módulo compartido.

### 8.2 Reglas de dominio y trazabilidad

**El reanálisis borra cajas ya revisadas.** `save_analysis_result` elimina todas las `Detection` y las vuelve a crear con nuevos IDs. Si el caso ya estaba decidido, la auditoría registra `ANALISIS_POSTERIOR_A_DECISION`, pero `HumanReview.rejected_detection_ids` sigue apuntando a IDs que ya no existen y se pierde el estado de cada caja. Ya no se puede reconstruir qué confirmó o descartó el especialista. Conviene conservar las cajas versionadas o guardar una instantánea en la revisión.

**La confirmación automática por IA tensiona la regla de que la IA solo sugiere.** Está aceptada en un ADR y desactivada por defecto, así que hoy no dispara. Pero el propio ADR admite falsos positivos con confianzas de 0,6 a 0,8, y un aviso ya enviado no se retira. Antes de activar el umbral haría falta evidencia de validación del modelo y dejar claro en el mensaje que es una alerta automática revisable.

**“Un caso por lugar” no está garantizado en la base.** La unicidad se sostiene con un bloqueo de fila en la aplicación; no hay restricción única sobre la secuencia. La reparación de duplicados solo une casos pendientes, no decididos. Una importación o un error de servicio podría crear dos casos decididos y duplicar avisos.

**El admin de catálogos puede saltarse los servicios.** Impide borrar y cambiar IDs, pero deja editar códigos, rangos y coordenadas sin validar el código único ni auditar. Mejor hacerlo solo lectura o enrutarlo por servicios.

Hay una contradicción menor de redacción: el docstring de `HumanReview` dice que nunca se edita, pero al corregir se marca `is_current=False`. Es correcto; lo que conviene es precisar que el contenido es inmutable y solo cambia la vigencia.

### 8.3 Documentación desincronizada

| Documento | Lo que dice | Lo que ocurre |
|---|---|---|
| `ARQUITECTURA_DATOS.md:211`, `CONTEXTO_WEB.md:873` | `sembrar_demo --solo-catalogos` permitido en piloto. | El comando falla siempre con `APP_ENV=piloto`. |
| `README.md:30-34` | IA e integración “previstas”. | Están implementadas. |
| `CLAUDE.md:3-5` | Leer `MAESTRO_WEB` y `MAESTRO_APP_MOVIL`. | No están en el repo. |
| `CONTEXTO_WEB.md:887` | 170 pruebas. | Hay 240, con 11 fallos y 0 omitidas con PostgreSQL. |
| `CONTEXTO_WEB.md:916-924` | ADR hasta 006, 007 “próximo”. | Hay ADR hasta 009. |
| `CONTEXTO_WEB.md` | Mapa con OSM y centro en Chincha. | El código usa teselas Esri/OSM y otro centro. |
| `INTEGRACION_APP.md` | No aparece `/mobile/deleted-captures`. | Existe y la app debería conocerlo. |
| `.env.example`, plantilla de piloto | Transformaciones Cloudinary con nombre. | Desde v1.3.1 son inline. |
| `deploy/LEEME.md` | Despliegue con `tar.gz`. | El runbook vigente es `git pull` + `actualizar.sh`. |
| `ARQUITECTURA_DATOS.md` | Supabase Pro. | El diagnóstico trabaja con Free de 500 MB. |
| ADR-W-003 y reporte | Migrar al ticket v2 antes del piloto. | El piloto está vivo y multipart sigue en `true`. |
| `REPORTE_AVANCE.md` | Cabecera “~90 %” y T-W00..T-W19. | Las últimas entradas no siguen el formato W-24. |
| `docs/perf/datos_sinteticos.sql` | Dataset de referencia. | Es anterior a v1.3: no cubre triage, dos cámaras ni casetas. |
| `ARQUITECTURA_DATOS.md:38-80,200-202` | 38 tablas y “no se borra nada hasta decidir”. | Faltan tablas nuevas y ADR-W-008 permite borrar descartadas. |

Sigue sin decidirse qué hacer con `AGENTS.md` y `AGENTS.md.bak`. Son cambios previos del usuario y no se han tocado, pero conviene elegir uno.

### 8.4 Detalles de la web

- Hay **teselas externas** de ArcGIS y OpenStreetMap en `mapa.js:43,53`. La prueba W-01 solo revisa `src` y `href` de plantillas, así que no lo detecta. Es una excepción consciente, pero debería documentarse o servirse cacheado.
- Quedan **textos de usuario fuera de `messages.py`**: respuestas JSON del editor de mapa, algunos `ValidationError`, títulos de actividad, el saludo y cadenas en los archivos JavaScript.
- `detecciones.html` y `modulos_casetas.html` son **pantallas placeholder enlazadas en el menú**, con datos inventados y filtros deshabilitados. En un piloto pueden confundir. Usan además glifos Unicode en vez del sprite.
- `pctnum` se usa como texto visible en tres plantillas. Está pensado para atributos y CSS y emite punto decimal; en `es-pe` debería verse `46,48 %` y se ve `46.48 %`.
- Queda **CSS huérfano** que referencia `img/hoja.svg`, archivo que no existe y cuyas clases nadie usa.

---

## 9. Plan de acción

### Antes de cualquier piloto real

1. **Poner la suite en verde.** Empezar por `modulos_casetas`, seguir por los iconos, unificar los textos en `messages.py` y arreglar el orden de marcadores con una ordenación semántica o una aserción independiente del locale.
2. **Cerrar las brechas de API**: lista negra al cambiar contraseña, validación real del dispositivo en la sincronización y resolución de la IP detrás del proxy.
3. **Hacer que el despliegue sepa recuperarse**: instalar `pg_dump`, guardar copias fuera del contenedor, probar una restauración, respaldar antes de migrar, conservar la imagen anterior y dejar que el diagnóstico pueda fallar el deploy.
4. **Añadir salud y alertas al worker.**
5. **Cerrar la checklist de habilitación**: modelo YOLO, WhatsApp real, GeoJSON, destinatarios con consentimiento y plan de Supabase con backups.

### Antes de escalar

6. Alinear documentación y runbooks, incluidas las cifras de pruebas y el formato W-24.
7. Mostrar los KPIs ya calculados o quitar el cálculo muerto; sustituir la lista de fechas por un agregado SQL; eliminar el N+1.
8. Pasar al ticket v2 de subida o ampliar `/tmp`; mover `map_layers` fuera de la capa web.
9. Dar trazabilidad al reanálisis, reforzar la restricción de “un caso por lugar” y cerrar el admin de catálogos.
10. **Montar CI con PostgreSQL 16**, creando los roles `anon`/`authenticated` e instalando `requirements-ia.txt`. Ese es el único modo de repetir los 240 tests sin omitidas. Añadir `check` y `makemigrations --check` como puerta de merge.

### Limpieza

11. Localizar los porcentajes visibles, centralizar los copys, documentar la excepción de teselas, ocultar o señalar las pantallas placeholder, limpiar el CSS huérfano, fijar versiones de IA y digest de la imagen base, revisar la heurística de `TESTING` y hacer que `medir_rendimiento` avise si falta `collectstatic`.

---

## 10. Conclusión

El proyecto está muy bien construido. La separación de responsabilidades, la defensa de las reglas en los servicios, la seguridad en capas y la forma de resolver la concurrencia son decisiones pensadas. Esta pasada con PostgreSQL lo confirma: la base y sus defensas aguantan la revisión, y las pruebas de seguridad e IA que antes no se ejecutaban pasan.

Lo que no está a la altura es la última milla: once pruebas en rojo, un permiso mal puesto, credenciales que no se revocan donde deberían, despliegue sin copia de seguridad y documentación atrasada. Nada de eso exige rehacer la arquitectura. Es trabajo de orden, automatización y disciplina de entrega.

Con los cinco primeros pasos la suite vuelve a verde. Con los cinco siguientes el piloto deja de depender de la suerte. Y con la limpieza final el repo vuelve a contar la misma historia que el código.

---

## Anexo — Estado del entorno de verificación

- Contenedor `riachuelo-pg16-check`, PostgreSQL 16.16, puerto 5433, base `riachuelo_test`. Creado solo para esta revisión.
- Roles `anon` y `authenticated` creados únicamente en ese clúster, para reproducir Supabase.
- `sembrar_demo` ejecutado solo en ese contenedor; no se tocó la base local del usuario.
- `pip` arrancado con `ensurepip` en `.venv` e instalado `requirements-ia.txt` (numpy 2.5.5, onnxruntime 1.32.0).
- No se ejecutaron `migrate`, `collectstatic` ni `sembrar_demo` contra la base ni el entorno del usuario.
- Estado Git final: `M AGENTS.md`, `?? AGENTS.md.bak` y `?? informe_reiter_dash.md`. El informe anterior del 19/11 ya no aparece en el directorio de trabajo; esta revisión no lo eliminó.
