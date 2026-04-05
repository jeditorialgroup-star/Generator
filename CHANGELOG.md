# CHANGELOG — inforeparto.com Content Pipeline

Formato: [tipo] descripción — motivo

---

## 2026-04-05 — Limpieza Fase 0.3

### fix: mover credenciales hardcodeadas a variables de entorno

**Archivos:** `scripts/autopublisher.py`, `scripts/daily-refresh.py`, `scripts/gsc-topic-discovery.py`, `naturalizer/naturalizer.py`, `~/.env.projects`

**Problema:** La contraseña de MariaDB (`2R9EUs4FDYlc`) y el token del bot de Telegram estaban literalmente en el código fuente de 4 archivos. Cualquier acceso al repositorio exponía estas credenciales.

**Cambio:**
- `DB = dict(password="...")` → `DB = dict(password=os.environ.get("WP_DB_PASSWORD", ""))`
- `TELEGRAM_BOT_TOKEN = "8558..."` → `TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")`
- Añadidos `WP_DB_HOST`, `WP_DB_USER`, `WP_DB_PASSWORD`, `WP_DB_NAME`, `TELEGRAM_CHAT_ID` a `~/.env.projects`
- `naturalizer.py` DB_CONFIGS usa ahora env vars en lugar de valores literales

---

### feat: añadir python-dotenv para carga automática de entorno

**Archivos:** `requirements.txt`, todos los scripts principales

**Problema:** Los scripts dependían de que el entorno ya estuviese cargado (vía `source ~/.env.projects`) antes de ejecutarse. Llamarlos directamente sin sourcing fallaba con errores crípticos. Además, cada script tenía su propio parser manual del .env que no era fiable (faltaba manejo del prefijo `export`).

**Cambio:**
- Añadido `python-dotenv>=1.0.0` a `requirements.txt`
- Añadido `from dotenv import load_dotenv` + `load_dotenv(Path.home() / ".env.projects", override=False)` al inicio de cada script
- Eliminado el bloque de parseo manual del env en `main()` de los 3 scripts que lo tenían

---

### fix: estandarizar logging — eliminar print() en gsc-topic-discovery.py e index_urls.py

**Archivos:** `scripts/gsc-topic-discovery.py`, `gsc-indexing/index_urls.py`

**Problema:** Estos dos scripts usaban `print()` para todo su output. A diferencia de `autopublisher.py` y `daily-refresh.py`, no tenían fichero de log, no tenían timestamp ni nivel, y su output no quedaba registrado en ningún sitio cuando corrían via cron.

**Cambio:**
- Añadido `logging.basicConfig()` con `FileHandler` + `StreamHandler` en ambos scripts
- `gsc-topic-discovery.py`: logs en `scripts/logs/gsc-topic-discovery-YYYY-MM-DD.log`
- `index_urls.py`: logs en `/var/log/projects/gsc-indexing-YYYY-MM-DD.log` (por fecha, ya no sobreescribe)
- Todos los `print()` en `main()` reemplazados por `log.info()` / `log.warning()` / `log.error()`

---

### docs: añadir docstrings a funciones sin documentar

**Archivos:** `scripts/gsc-topic-discovery.py`, `scripts/daily-refresh.py`, `gsc-indexing/index_urls.py`

**Problema:** ~30 funciones sin docstring. Hace más difícil entender el código y usar herramientas de análisis estático.

**Cambio:** Añadidas docstrings de una línea a todas las funciones públicas sin documentar. No se han modificado las funciones que ya las tenían.

Funciones documentadas:
- `gsc-topic-discovery.py`: `telegram_send`, `db_connect`, `_gsc_token`, `load_embeddings_cache`, `get_embedding`, `cosine_similarity`, `main`
- `daily-refresh.py`: `db_connect`, `get_post_data`, `set_post_meta`, `load_batch_state`, `save_batch_state`, `clear_batch_state`, `get_image_query`, `should_replace_image`, `gsc_index_url`, `ollama_available`, `get_embedding`, `cosine_similarity`, `get_all_posts_meta`, `get_post_content_only`, `load_embeddings_cache`, `save_embeddings_cache`, `find_similar_posts`, `load_affiliate_catalog`, `update_post_in_wp`, `set_featured_image`, `telegram_send`, `main`
- `index_urls.py`: `get_access_token`, `get_post_urls`, `notify_url`, `main`

---

### docs: crear documentación completa del proyecto (Fase 0.2)

**Archivos creados:** `README.md`, `ARCHITECTURE.md`, `AUDIT.md`, `.env.example`, `requirements.txt`

**Descripción:**
- `README.md`: descripción del sistema, requisitos, estructura de directorios, cómo ejecutar cada proceso, troubleshooting
- `ARCHITECTURE.md`: diagrama ASCII de los 4 procesos, flujo de datos, schemas de las 3 tablas MariaDB, tabla de APIs con límites y costes
- `AUDIT.md`: mapa de archivos, dependencias reales, problemas encontrados ordenados por severidad, diagrama Mermaid del flujo de datos
- `.env.example`: plantilla de todas las variables de entorno necesarias con comentarios
- `requirements.txt`: 6 dependencias Python reales del pipeline activo

---

## 2026-04-05 — Correcciones de producción (sesión anterior)

### fix: bloqueo y retry de autónomos en contenido generado
**Archivo:** `scripts/autopublisher.py`
- Añadida restricción legal en el prompt de generación (Ley Rider RDL 9/2021)
- Añadido bloqueo bloqueante post-generación: si el HTML contiene "autónomo/autónomos/RETA" sin contexto Amazon Flex → retry con brief reforzado → bloqueo si persiste
- Motivo: El primer post de prueba (ID 674) trató el régimen de autónomos para riders, lo que es incorrecto desde la Ley Rider

### fix: imágenes via REST API en lugar de wp media import
**Archivo:** `scripts/autopublisher.py`
- `wp media import` fallaba porque el usuario `devops` no pertenece al grupo `www-data`
- Cambiado a subida directa via WP REST API (`/wp-json/wp/v2/media`) con credenciales de app password
- Motivo: eliminar dependencia de permisos del sistema de archivos

### fix: imágenes inline en el cuerpo del artículo
**Archivo:** `scripts/autopublisher.py`
- Añadida función `inject_inline_images()`: 2 imágenes Pexels insertadas como `<figure>` después de la 1ª y 3ª sección H2
- Claude Haiku genera 2 queries complementarias (acción + detalle)

### fix: disclaimer único universal
**Archivos:** `naturalizer/contextos/inforeparto/editorial_rules.yaml`, `scripts/autopublisher.py`
- Fusionados 4 disclaimers separados (fiscal, legal_laboral, ganancias, convenio) en uno único universal
- Motivo: múltiples disclaimers al final de un post son redundantes y visualmente pesados

### fix: capitalización del título
**Archivo:** `scripts/autopublisher.py`
- El modelo generaba títulos completamente en minúsculas
- Añadido `title = title[0].upper() + title[1:]` tras extraer el título del HTML

### fix: calendario de publicación independiente
**Archivo:** `scripts/autopublisher.py`
- `get_last_scheduled_date()` ahora solo mira posts con meta `_ir_autopublished=1`
- Motivo: el primer test programó el post al 16 de mayo porque sumaba 3 días al último post del blog-generator

### fix: performance gate en daily-refresh
**Archivo:** `scripts/daily-refresh.py`
- Posts con `avg_position ≤ 20 AND clicks ≥ 15` excluidos del refresh
- Motivo: no tiene sentido tocar posts que ya están rindiendo bien

### fix: env parser en scripts (prefijo `export`)
**Archivos:** `scripts/autopublisher.py`, `scripts/daily-refresh.py`, `scripts/gsc-topic-discovery.py`
- El parser manual del .env no eliminaba el prefijo `export ` de las líneas
- Variables como `SERPER_API_KEY` se cargaban como `"export SERPER_API_KEY"` → bug silencioso
- Ahora resuelto mediante python-dotenv que maneja el prefijo correctamente

### fix: self-import circular en naturalizer.py
**Archivo:** `naturalizer/naturalizer.py`
- `from naturalizer import _get_db_config` dentro del mismo módulo causaba un import circular silencioso
- El log de naturalizaciones nunca se guardaba en `ir_naturalization_log`
- Eliminado el import, llamada directa a `_get_db_config(site)`

### fix: source_density hardcodeado en NaturalScorer
**Archivo:** `naturalizer/naturalizer.py`
- `NaturalScorer.score()` tenía `source_density = 0.5` hardcodeado, ignorando las fuentes reales
- Añadido `source_density: float = 0.5` como parámetro de la función
