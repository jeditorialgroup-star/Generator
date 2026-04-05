#!/usr/bin/env python3
"""
daily-refresh.py — Actualización y naturalización diaria de posts (Batch API)

Arquitectura en dos fases:
  Fase A (mañana): Selecciona 3-4 posts, prepara prompts, envía batch a Anthropic
  Fase B (mismo run o siguiente): Recoge resultados del batch, aplica cambios en WP + GSC

Filtros:
  - Posts con post_date o post_modified en los últimos 40 días → SKIP
  - Posts ya marcados con _ir_last_refresh reciente → SKIP

Uso:
  python3 daily-refresh.py            # ciclo normal (A si no hay batch, B si hay batch pendiente)
  python3 daily-refresh.py --dry-run  # sin guardar cambios ni enviar batch real
  python3 daily-refresh.py --check    # solo comprueba si el batch pendiente está listo
"""

import argparse
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import anthropic
import mysql.connector
from dotenv import load_dotenv

# Cargar .env.projects antes de leer cualquier variable de entorno
load_dotenv(Path.home() / ".env.projects", override=False)
import requests
import google.auth.transport.requests
import google.oauth2.service_account

# ── Naturalizer v4 ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "naturalizer"))
try:
    from naturalizer import naturalize as _naturalize_v4
    NATURALIZER_AVAILABLE = True
except Exception as _nat_err:
    NATURALIZER_AVAILABLE = False
    _nat_err_msg = str(_nat_err)

# ── Configuración ─────────────────────────────────────────────────────────────

WP_PATH = "/var/www/inforeparto"
WP_URL = "https://inforeparto.com"

DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)

CREDENTIALS_PATH = "/home/devops/.credentials/gsc-serviceaccount.json"
INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"

SCRIPTS_DIR = Path(__file__).parent
LOGS_DIR = SCRIPTS_DIR / "logs"
BATCH_STATE_FILE = SCRIPTS_DIR / "batch_state.json"
LOGS_DIR.mkdir(exist_ok=True)

LOG_FILE = LOGS_DIR / f"daily-refresh-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))

META_KEY = "_ir_last_refresh"
POSTS_PER_RUN = 4
MIN_AGE_DAYS = 100         # solo actualizar posts con 100+ días sin refresh
BATCH_MAX_WAIT_HOURS = 23  # si el batch lleva más de esto, lo marcamos como expirado

# Performance gate: NO actualizar posts que ya están funcionando bien
# Un post se considera "bien" si: posición <= 20 Y clicks_30d > 15
PERF_GATE_MAX_POSITION = 35   # posición peor que esto → candidato a refresh
PERF_GATE_MIN_CLICKS = 15     # clicks < esto Y posición < 20 → también candidato

EMBEDDINGS_CACHE_FILE = SCRIPTS_DIR / "post_embeddings.json"
AFFILIATE_CATALOG_FILE = SCRIPTS_DIR / "affiliate_catalog.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# ── Prompts ───────────────────────────────────────────────────────────────────

COMBINED_SYSTEM = """Eres el editor de inforeparto.com, blog para repartidores y riders en España.
Actualiza los datos del post que te mando. La naturalización se aplica en un paso separado.

ACTUALIZACIÓN DE DATOS:
- Actualiza años (2024→2025, 2025→2026) solo si el contexto lo permite y la info sigue siendo válida.
- Actualiza cifras que conozcas con certeza (SMI, cuotas RETA si cambiaron).
- NO inventes datos que no conoces. Si no estás seguro, déjalo.
- Si el post trata sobre algo completamente obsoleto (empresa cerrada, normativa derogada), responde SOLO: "OBSOLETE: <motivo breve>"

CONTENIDO PROTEGIDO — NO modificar:
- Bloques con clase "aviso-afiliados", "aviso-actualizacion", disclaimers
- Enlaces amazon.es/dp/
- Tablas HTML con datos
- Shortcodes de WordPress

RESPUESTA:
- Post viable: devuelve SOLO el HTML completo y actualizado, sin explicaciones previas.
- Post obsoleto: devuelve SOLO "OBSOLETE: <motivo>"
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```html ... ```) that Claude sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1:]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return text.strip()


# ── DB helpers ─────────────────────────────────────────────────────────────────

def db_connect():
    """Return a new MariaDB connection using DB config from environment."""
    return mysql.connector.connect(**DB)


def get_posts_to_refresh(limit=POSTS_PER_RUN):
    """
    Posts >MIN_AGE_DAYS sin refresh que NO están rindiendo bien.
    Performance gate: excluye posts con avg_position <= 20 Y clicks >= PERF_GATE_MIN_CLICKS.
    Posts sin métricas GSC siempre se incluyen (no hay datos para protegerlos).
    """
    cutoff = (datetime.now() - timedelta(days=MIN_AGE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.ID
        FROM wp_posts p
        LEFT JOIN wp_postmeta m ON m.post_id = p.ID AND m.meta_key = '{META_KEY}'
        LEFT JOIN ir_naturalization_log nl ON nl.wp_post_id = p.ID
            AND nl.metrics_updated_at IS NOT NULL
        WHERE p.post_status = 'publish'
          AND p.post_type = 'post'
          AND GREATEST(p.post_date, p.post_modified) < %s
          AND NOT (
            nl.avg_position IS NOT NULL
            AND nl.avg_position <= 20
            AND nl.pageviews_30d >= {PERF_GATE_MIN_CLICKS}
          )
        ORDER BY COALESCE(m.meta_value, '0') ASC, p.post_date ASC
        LIMIT %s
    """, (cutoff, limit))
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_post_data(post_id):
    """Fetch post content, title, slug and featured image data from MariaDB."""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT ID, post_title, post_content, post_name, post_date FROM wp_posts WHERE ID = %s",
        (post_id,)
    )
    post = cur.fetchone()
    cur.execute(
        "SELECT meta_value FROM wp_postmeta WHERE post_id = %s AND meta_key = '_thumbnail_id'",
        (post_id,)
    )
    thumb = cur.fetchone()
    cur.close()
    conn.close()

    featured_image_url = None
    featured_image_id = None
    if thumb:
        featured_image_id = int(thumb["meta_value"])
        r = subprocess.run(
            ["wp", "post", "get", str(featured_image_id), "--field=guid", f"--path={WP_PATH}"],
            capture_output=True, text=True
        )
        featured_image_url = r.stdout.strip()

    post["featured_image_url"] = featured_image_url
    post["featured_image_id"] = featured_image_id
    return post


def set_post_meta(post_id, key, value):
    """Upsert a WP post meta key/value pair directly in MariaDB."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT meta_id FROM wp_postmeta WHERE post_id = %s AND meta_key = %s", (post_id, key)
    )
    if cur.fetchone():
        cur.execute(
            "UPDATE wp_postmeta SET meta_value = %s WHERE post_id = %s AND meta_key = %s",
            (value, post_id, key)
        )
    else:
        cur.execute(
            "INSERT INTO wp_postmeta (post_id, meta_key, meta_value) VALUES (%s, %s, %s)",
            (post_id, key, value)
        )
    conn.commit()
    cur.close()
    conn.close()


# ── Batch state ────────────────────────────────────────────────────────────────

def load_batch_state():
    """Load Anthropic batch state from the local JSON file. Returns None if not found."""
    if BATCH_STATE_FILE.exists():
        with open(BATCH_STATE_FILE) as f:
            return json.load(f)
    return None


def save_batch_state(state):
    """Persist the current Anthropic batch state to the local JSON file."""
    with open(BATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def clear_batch_state():
    """Delete the batch state file after a batch completes or expires."""
    if BATCH_STATE_FILE.exists():
        BATCH_STATE_FILE.unlink()


# ── Imagen ─────────────────────────────────────────────────────────────────────

def get_image_query(post_title, snippet):
    """Use Claude Haiku to generate a 2-4 word Pexels search query for the post."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=60,
        messages=[{"role": "user", "content": f"Post title: {post_title}\nSnippet: {snippet[:400]}\nGenerate ONE English 2-4 word Pexels search query for a relevant professional photo. Only the query, nothing else."}]
    )
    return msg.content[0].text.strip().strip('"')


def fetch_and_upload_image(post_id, post_title, post_content, dry_run=False):
    """Busca imagen en Pexels y la sube a WP. Devuelve attachment_id o None."""
    if not PEXELS_API_KEY:
        return None
    snippet = re.sub(r"<[^>]+>", " ", post_content)[:400]
    query = get_image_query(post_title, snippet)
    log.info(f"  Pexels query: '{query}'")

    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "per_page": 3, "orientation": "landscape"},
        timeout=10
    )
    if resp.status_code != 200 or not resp.json().get("photos"):
        log.warning("  Sin resultados en Pexels")
        return None

    photo = resp.json()["photos"][0]
    img_url = photo["src"]["large2x"]

    if dry_run:
        log.info(f"  [dry-run] Subiría: {img_url}")
        return None

    import tempfile
    r = requests.get(img_url, timeout=30)
    if r.status_code != 200:
        return None
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name

    result = subprocess.run(
        ["wp", "media", "import", tmp_path, f"--post_id={post_id}",
         f"--title={post_title}", f"--alt={post_title}", "--porcelain", f"--path={WP_PATH}"],
        capture_output=True, text=True
    )
    os.unlink(tmp_path)
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


def should_replace_image(post):
    """Return True if the post's featured image is missing or judged irrelevant by Haiku."""
    if not post.get("featured_image_url"):
        return True
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": f"Post: {post['post_title']}\nImage URL: {post['featured_image_url']}\nIs this image relevant and professional? Reply YES or NO only."}]
    )
    return msg.content[0].text.strip().upper().startswith("NO")


# ── GSC ────────────────────────────────────────────────────────────────────────

def gsc_index_url(url):
    """Send a URL_UPDATED notification to the Google Indexing API. Returns True on success."""
    try:
        creds = google.oauth2.service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH, scopes=["https://www.googleapis.com/auth/indexing"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        resp = requests.post(
            INDEXING_API,
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
            json={"url": url, "type": "URL_UPDATED"},
            timeout=15
        )
        return resp.status_code == 200
    except Exception as e:
        log.warning(f"  GSC error: {e}")
        return False


# ── Internal linking ─────────────────────────────────────────────────────────

def ollama_available() -> bool:
    """Check if the local Ollama instance is running with nomic-embed-text loaded."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        return any("nomic-embed-text" in m for m in models)
    except Exception:
        return False


def get_embedding(text: str):
    """Request a nomic-embed-text embedding from the local Ollama instance. Returns list or None."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30,
        )
        return resp.json().get("embedding")
    except Exception as e:
        log.warning(f"  Embedding error: {e}")
        return None


def cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def get_all_posts_meta():
    """Return ID, title, and slug for all published posts."""
    conn = db_connect()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT ID, post_title, post_name FROM wp_posts "
        "WHERE post_status = 'publish' AND post_type = 'post'"
    )
    posts = cur.fetchall()
    cur.close()
    conn.close()
    return posts


def get_post_content_only(post_id: int) -> str:
    """Return the raw post_content HTML for a given post ID."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT post_content FROM wp_posts WHERE ID = %s", (post_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else ""


def load_embeddings_cache() -> dict:
    """Load the local post embeddings cache from disk. Returns empty dict if not found."""
    if EMBEDDINGS_CACHE_FILE.exists():
        with open(EMBEDDINGS_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_embeddings_cache(cache: dict) -> None:
    """Persist the updated embeddings cache to disk."""
    with open(EMBEDDINGS_CACHE_FILE, "w") as f:
        json.dump(cache, f)


def build_embeddings_cache(all_posts: list, cache: dict) -> None:
    """Embed posts missing from cache. Slow on first run (~62 Ollama calls), fast afterwards."""
    for post in all_posts:
        key = str(post["ID"])
        if key in cache:
            continue
        content = get_post_content_only(post["ID"])
        text = f"{post['post_title']}. {re.sub(r'<[^>]+>', ' ', content)}"[:2000]
        emb = get_embedding(text)
        if emb:
            cache[key] = {
                "title": post["post_title"],
                "slug": post["post_name"],
                "embedding": emb,
            }
            log.info(f"  Embedding → {post['ID']}: {post['post_title'][:45]}")


def find_similar_posts(post_id: int, embedding: list, cache: dict, n: int = 4) -> list:
    """Return the N most semantically similar posts (by cosine similarity) for internal linking."""
    sims = []
    for key, data in cache.items():
        if int(key) == post_id:
            continue
        emb = data.get("embedding")
        if not emb:
            continue
        sim = cosine_similarity(embedding, emb)
        sims.append((sim, {"id": int(key), "title": data["title"], "slug": data["slug"]}))
    sims.sort(reverse=True)
    return [item for _, item in sims[:n]]


def enrich_internal_links(post_id: int, content: str, title: str, cache: dict) -> str:
    """Insert 2-3 internal links via Claude Haiku. Returns original on any failure."""
    try:
        text = f"{title}. {re.sub(r'<[^>]+>', ' ', content)}"[:2000]
        embedding = get_embedding(text)
        if not embedding:
            return content

        similar = find_similar_posts(post_id, embedding, cache)
        if not similar:
            return content

        links_info = "\n".join(
            f"- {p['title']}: https://inforeparto.com/{p['slug']}/"
            for p in similar
        )
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": (
                f"Eres el editor de inforeparto.com. Añade 2-3 enlaces internos naturales en este post HTML.\n\n"
                f"Post: {title}\n"
                f"HTML:\n{content}\n\n"
                f"Posts relacionados (elige los que mejor encajen):\n{links_info}\n\n"
                f"Reglas:\n"
                f"- Integra los enlaces en texto existente, sin añadir párrafos nuevos\n"
                f"- Texto ancla descriptivo y natural (nunca 'haz clic aquí')\n"
                f"- Formato: <a href=\"URL\">texto ancla</a>\n"
                f"- No añadas rel=\"nofollow\" (son internos)\n"
                f"- Si no encaja naturalmente, no fuerces el enlace\n"
                f"- Devuelve SOLO el HTML completo, sin explicaciones"
            )}]
        )
        result = strip_code_fences(msg.content[0].text)
        if result:
            # Update embedding in cache for the refreshed content
            new_emb = get_embedding(f"{title}. {re.sub(r'<[^>]+>', ' ', result)}"[:2000])
            if new_emb:
                cache[str(post_id)] = {
                    "title": title,
                    "slug": cache.get(str(post_id), {}).get("slug", ""),
                    "embedding": new_emb,
                }
            log.info(f"  Enlazado interno OK (similares: {[p['title'][:30] for p in similar[:2]]})")
            return result
        return content
    except Exception as e:
        log.warning(f"  enrich_internal_links error: {e}")
        return content


# ── Affiliate linking ─────────────────────────────────────────────────────────

def load_affiliate_catalog() -> list:
    """Load the Amazon affiliate product catalog from disk. Returns empty list if not found."""
    if AFFILIATE_CATALOG_FILE.exists():
        with open(AFFILIATE_CATALOG_FILE) as f:
            return json.load(f)
    return []


def enrich_affiliate_links(content: str, title: str) -> str:
    """Insert Amazon affiliate links from catalog via Claude Haiku. Returns original on failure."""
    try:
        catalog = load_affiliate_catalog()
        if not catalog:
            return content

        catalog_str = "\n".join(
            f"- Palabras clave: {', '.join(e['keywords'])} | ASIN: {e['asin']} | Producto: {e['name']}"
            for e in catalog
        )
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": (
                f"Eres el editor de inforeparto.com. Añade enlaces de afiliado de Amazon donde sea apropiado.\n\n"
                f"Post: {title}\n"
                f"HTML:\n{content}\n\n"
                f"Catálogo de productos (SOLO usa estos ASINs, no inventes otros):\n{catalog_str}\n\n"
                f"Reglas:\n"
                f"- Máximo 5-8 enlaces de afiliado en total\n"
                f"- No modifiques enlaces amazon.es/dp/ existentes\n"
                f"- Integra el enlace de forma natural dentro del texto existente\n"
                f'- Formato: <a href="https://www.amazon.es/dp/ASIN/ref=nosim?tag=inforeparto-21" target="_blank" rel="nofollow noopener">texto ancla</a>\n'
                f"- Si añades algún enlace Y no hay bloque aviso-afiliados, añádelo tras el primer párrafo:\n"
                f'  <p class="aviso-afiliados"><em>Este artículo contiene enlaces de afiliado de Amazon. Si compras a través de ellos, inforeparto recibe una pequeña comisión sin coste adicional para ti. Esto nos ayuda a mantener el sitio.</em></p>\n'
                f"- No modifiques el bloque aviso-afiliados si ya existe\n"
                f"- Si el catálogo no tiene nada relevante para este post, devuelve el HTML sin cambios\n"
                f"- Devuelve SOLO el HTML completo, sin explicaciones"
            )}]
        )
        result = strip_code_fences(msg.content[0].text)
        if result:
            added = result.count("amazon.es/dp/") - content.count("amazon.es/dp/")
            if added > 0:
                log.info(f"  Enlazado afiliación: +{added} enlaces insertados")
            return result
        return content
    except Exception as e:
        log.warning(f"  enrich_affiliate_links error: {e}")
        return content


# ── WP update ─────────────────────────────────────────────────────────────────

def update_post_in_wp(post_id, new_content, dry_run=False):
    """Update post_content in WP via WP-CLI. Returns True on success."""
    if dry_run:
        log.info(f"  [dry-run] Actualizaría post {post_id}")
        return True
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = subprocess.run(
        ["wp", "post", "update", str(post_id),
         f"--post_content={new_content}",
         f"--post_modified={today_str}",
         f"--path={WP_PATH}"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def set_featured_image(post_id, attachment_id):
    """Set the WP featured image (_thumbnail_id) for the given post via WP-CLI."""
    subprocess.run(
        ["wp", "post", "meta", "update", str(post_id), "_thumbnail_id", str(attachment_id),
         f"--path={WP_PATH}"],
        capture_output=True, text=True
    )


# ── Telegram ───────────────────────────────────────────────────────────────────

def telegram_send(text):
    """Send an HTML-formatted message to the configured Telegram chat. Silently fails on error."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram error: {e}")


# ── FASE A: Preparar y enviar batch ───────────────────────────────────────────

def phase_a_submit(dry_run=False):
    """Selecciona posts y envía batch a Anthropic."""
    post_ids = get_posts_to_refresh()
    if not post_ids:
        log.info("No hay posts que cumplan los criterios (>40 días sin refresh).")
        telegram_send("📋 Daily refresh: no hay posts que actualizar hoy (todos recientes o ya procesados).")
        return

    log.info(f"Posts seleccionados: {post_ids}")
    posts = [get_post_data(pid) for pid in post_ids]

    # Preparar requests del batch
    batch_requests = []
    post_meta = {}  # custom_id → info del post
    today = date.today().isoformat()

    for post in posts:
        custom_id = f"post-{post['ID']}"
        prompt = f"""Fecha de hoy: {today}
Título: {post['post_title']}
Fecha original del post: {post['post_date']}

HTML del post:
{post['post_content']}"""

        batch_requests.append({
            "custom_id": custom_id,
            "params": {
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": COMBINED_SYSTEM,
                "messages": [{"role": "user", "content": prompt}]
            }
        })
        post_meta[custom_id] = {
            "post_id": post["ID"],
            "title": post["post_title"],
            "slug": post["post_name"],
            "featured_image_url": post["featured_image_url"],
            "featured_image_id": post["featured_image_id"],
        }

    if dry_run:
        log.info(f"[dry-run] Enviaría batch con {len(batch_requests)} requests")
        log.info(f"[dry-run] Posts: {[p['post_title'] for p in posts]}")
        telegram_send(f"🧪 [dry-run] Batch de {len(batch_requests)} posts preparado (no enviado).")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    log.info(f"Enviando batch con {len(batch_requests)} posts a Anthropic...")
    batch = client.messages.batches.create(requests=batch_requests)
    log.info(f"Batch enviado: {batch.id} — status: {batch.processing_status}")

    state = {
        "batch_id": batch.id,
        "submitted_at": datetime.now().isoformat(),
        "post_meta": post_meta,
    }
    save_batch_state(state)

    titles = [p["post_title"][:50] for p in posts]
    titles_str = "\n".join(f"  • {t}" for t in titles)
    telegram_send(
        f"📤 <b>Batch enviado ({len(batch_requests)} posts)</b>\n"
        f"ID: <code>{batch.id}</code>\n\n"
        f"{titles_str}\n\n"
        f"Procesando en Anthropic (hasta 24h, 50% más barato). "
        f"Resultados se aplicarán en la próxima ejecución."
    )


# ── FASE B: Recoger resultados y aplicar ──────────────────────────────────────

def phase_b_apply(state, dry_run=False):
    """Recoge resultados del batch y aplica cambios en WP."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    batch_id = state["batch_id"]
    post_meta = state["post_meta"]

    log.info(f"Comprobando batch {batch_id}...")
    batch = client.messages.batches.retrieve(batch_id)
    log.info(f"Status: {batch.processing_status} — {batch.request_counts}")

    if batch.processing_status == "in_progress":
        submitted_at = datetime.fromisoformat(state["submitted_at"])
        hours_elapsed = (datetime.now() - submitted_at).total_seconds() / 3600
        if hours_elapsed > BATCH_MAX_WAIT_HOURS:
            log.warning(f"Batch lleva {hours_elapsed:.1f}h sin completarse. Cancelando.")
            client.messages.batches.cancel(batch_id)
            clear_batch_state()
            telegram_send(f"⚠️ Batch {batch_id} cancelado por timeout ({hours_elapsed:.0f}h). Se reintentará mañana.")
        else:
            log.info(f"Batch en progreso ({hours_elapsed:.1f}h). Se revisará en la próxima ejecución.")
            telegram_send(f"⏳ Batch {batch_id} aún procesando ({hours_elapsed:.1f}h). Se revisará mañana.")
        return

    if batch.processing_status != "ended":
        log.warning(f"Batch en estado inesperado: {batch.processing_status}")
        return

    # Procesar resultados
    log.info("Batch completado. Procesando resultados...")
    results = {}
    for result in client.messages.batches.results(batch_id):
        results[result.custom_id] = result

    applied = []
    obsolete = []
    errors = []

    # Preparar embeddings para enlazado interno
    _use_linking = ollama_available()
    _embeddings_cache: dict = {}
    if _use_linking:
        log.info("Construyendo índice de embeddings para enlazado interno...")
        _all_posts_meta = get_all_posts_meta()
        _embeddings_cache = load_embeddings_cache()
        build_embeddings_cache(_all_posts_meta, _embeddings_cache)
        log.info(f"  Índice listo: {len(_embeddings_cache)} posts en cache")
    else:
        log.info("Ollama/nomic-embed-text no disponible — enlazado interno desactivado")

    for custom_id, meta in post_meta.items():
        post_id = meta["post_id"]
        result = results.get(custom_id)

        if not result or result.result.type == "errored":
            err = str(result.result.error) if result else "sin resultado"
            log.error(f"  Error en {custom_id}: {err}")
            errors.append({"post_id": post_id, "title": meta["title"], "error": err})
            continue

        content = strip_code_fences(result.result.message.content[0].text)

        if content.startswith("OBSOLETE:"):
            reason = content[9:].strip()
            log.warning(f"  Post {post_id} OBSOLETO: {reason}")
            obsolete.append({"post_id": post_id, "title": meta["title"], "reason": reason})
            telegram_send(
                f"⚠️ <b>Post obsoleto</b> (ID {post_id})\n"
                f"{meta['title']}\n"
                f"Motivo: {reason}\n"
                f"https://inforeparto.com/{meta['slug']}/\n\n"
                f"¿Lo eliminamos?"
            )
            continue

        # Naturalizer v4 — Capas 1+2+3+3b+7+8
        if NATURALIZER_AVAILABLE:
            try:
                nat = _naturalize_v4(content, meta['title'], site="inforeparto", post_id=post_id)
                content = nat['content']
                ns = nat['score']['overall']
                status = "⚠️ REVISAR" if nat['needs_review'] else "✅"
                log.info(f"  NaturalScore: {ns}/100 {status}")
                if nat.get('experiences_used'):
                    log.info(f"  Capa 4: {len(nat['experiences_used'])} experiencias inyectadas")
                if nat.get('sources_added'):
                    log.info(f"  Capa 5b: {len(nat['sources_added'])} fuentes añadidas")
                if nat.get('competitor_report'):
                    log.info(f"  Capa 6: análisis competitivo aplicado")
                if nat['issues']:
                    log.warning(f"  Integridad (Capa 8): {nat['issues']}")
            except Exception as e:
                log.warning(f"  Naturalizer v4 error (usando contenido sin naturalizar): {e}")
        else:
            log.debug(f"  Naturalizer no disponible: {_nat_err_msg}")

        # Layer 1: Enlazado interno (semántico via embeddings)
        if _use_linking:
            content = enrich_internal_links(post_id, content, meta['title'], _embeddings_cache)

        # Layer 2: Enlazado de afiliación (Amazon, según catálogo)
        content = enrich_affiliate_links(content, meta['title'])

        # Aplicar contenido actualizado + naturalizado + enlazado
        log.info(f"  Aplicando post {post_id}: {meta['title'][:50]}")
        ok = update_post_in_wp(post_id, content, dry_run=dry_run)

        # Imagen
        image_replaced = False
        fake_post = {"featured_image_url": meta["featured_image_url"], "post_title": meta["title"]}
        if should_replace_image(fake_post):
            attachment_id = fetch_and_upload_image(post_id, meta["title"], content, dry_run=dry_run)
            if attachment_id and not dry_run:
                set_featured_image(post_id, attachment_id)
                image_replaced = True
                log.info(f"  Imagen actualizada (attachment {attachment_id})")

        # GSC
        url = f"{WP_URL}/{meta['slug']}/"
        indexed = gsc_index_url(url) if not dry_run else False
        log.info(f"  GSC: {'OK' if indexed else 'skip/error'}")

        # Meta
        if not dry_run:
            set_post_meta(post_id, META_KEY, datetime.now().isoformat())

        applied.append({
            "post_id": post_id,
            "title": meta["title"],
            "url": url,
            "image_replaced": image_replaced,
            "indexed": indexed,
        })

    # Guardar cache de embeddings (incluye actualizaciones de este refresh)
    if _use_linking and _embeddings_cache:
        save_embeddings_cache(_embeddings_cache)

    # Limpiar estado
    if not dry_run:
        clear_batch_state()

    # Resumen Telegram
    if not dry_run:
        lines = [f"✅ <b>Batch completado — {date.today().isoformat()}</b>\n"]
        for r in applied:
            icons = ("🖼️ " if r["image_replaced"] else "") + ("📡 " if r["indexed"] else "")
            lines.append(f"✅ {icons}<a href='{r['url']}'>{r['title'][:55]}</a>")
        for r in obsolete:
            lines.append(f"⚠️ Obsoleto (ID {r['post_id']}): {r['reason'][:60]}")
        for r in errors:
            lines.append(f"❌ Error ID {r['post_id']}: {r['error'][:60]}")
        lines.append(f"\nLog: {LOG_FILE}")
        telegram_send("\n".join(lines))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """Entry point: run Fase A (prepare batch) or Fase B (apply results) of the daily refresh."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="Solo comprobar batch pendiente")
    args = parser.parse_args()

    global ANTHROPIC_API_KEY, PEXELS_API_KEY
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY no encontrada")
        sys.exit(1)

    log.info(f"{'[DRY-RUN] ' if args.dry_run else ''}Daily refresh — {date.today().isoformat()}")

    state = load_batch_state()

    if state:
        log.info(f"Batch pendiente encontrado: {state['batch_id']} (enviado {state['submitted_at']})")
        phase_b_apply(state, dry_run=args.dry_run)
        if not args.check:
            # Si el batch ya terminó y se aplicó, enviar nuevo batch hoy
            if not load_batch_state():  # se limpió → batch terminado
                log.info("Batch anterior procesado. Preparando nuevo batch...")
                phase_a_submit(dry_run=args.dry_run)
    else:
        if args.check:
            log.info("No hay batch pendiente.")
            return
        phase_a_submit(dry_run=args.dry_run)

    log.info("Completado.")


if __name__ == "__main__":
    main()
