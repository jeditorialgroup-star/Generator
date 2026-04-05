#!/usr/bin/env python3
"""
autopublisher.py — Generación diaria de contenido nuevo para inforeparto.com

Pipeline:
  1. ¿Toca generar hoy? (cada día genera; se programa 3 días después del último)
  2. Selecciona tema de ir_topic_queue (prioridad desc)
  3. Research phase: competencia, fuentes, experiencias, links internos, afiliados
  4. Build brief estructurado
  5. Genera post (Sonnet)
  6. Naturaliza (capas 1+2+3+3b via naturalizer.py)
  7. Byline + Schema (6b)
  8. Score + Integridad (7+8)
  9. Si score >= 70: publica como 'future' en WP con fecha programada
     Si score < 70: guarda como draft, notifica Telegram
  10. Log en ir_naturalization_log + notifica Telegram

Cron: 05:00 diario
  cd /home/devops/projects/inforeparto/scripts && source /home/devops/.env.projects && python3 autopublisher.py

Uso manual:
  python3 autopublisher.py --dry-run
  python3 autopublisher.py --topic "desgravación móvil autónomo rider"
  python3 autopublisher.py --force   # genera aunque no "toque" hoy
"""

import argparse
import json
import logging
import math
import os
import random
import re
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import anthropic
import mysql.connector
import requests
import yaml
from dotenv import load_dotenv

# Cargar .env.projects antes de leer cualquier variable de entorno
load_dotenv(Path.home() / ".env.projects", override=False)

# ── Naturalizer v4 ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "naturalizer"))
try:
    from naturalizer import (
        load_config, load_voice, build_system_prompt,
        NaturalScorer, check_integrity, extract_protected, restore_protected,
        _naturalize_api_call, _strip_code_fences, _get_db_config,
    )
    from author_schema import inject_author_signals
    NATURALIZER_AVAILABLE = True
except Exception as _nat_err:
    NATURALIZER_AVAILABLE = False
    _nat_err_msg = str(_nat_err)

# ── Config (defaults — overridden per-site in main()) ─────────────────────────

SITE = "inforeparto"
WP_PATH = "/var/www/inforeparto"
WP_URL = "https://inforeparto.com"

DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))

SCRIPTS_DIR = Path(__file__).parent
NATURALIZER_DIR = Path(__file__).parent.parent / "naturalizer"
LOGS_DIR = SCRIPTS_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
AFFILIATE_CATALOG_FILE = SCRIPTS_DIR / "affiliate_catalog.json"
EMBEDDINGS_CACHE_FILE = SCRIPTS_DIR / "post_embeddings.json"
EDITORIAL_RULES_FILE = NATURALIZER_DIR / "contextos" / "inforeparto" / "editorial_rules.yaml"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

LOG_FILE = LOGS_DIR / f"autopublisher-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Publish schedule (overridden by site_config)
DAYS_BETWEEN_POSTS = 3
PUBLISH_HOUR_MIN = 8
PUBLISH_HOUR_MAX = 20
SCORE_THRESHOLD = 70
META_AUTOPUBLISHED = "_ir_autopublished"
TOPIC_QUEUE_TABLE = "ir_topic_queue"
NATURALIZATION_LOG_TABLE = "ir_naturalization_log"
AFFILIATE_TAG = "inforeparto-21"
AFFILIATE_DISCLOSURE = (
    "Este artículo contiene enlaces de afiliado de Amazon. "
    "Si compras a través de ellos, inforeparto recibe una pequeña comisión sin coste adicional para ti."
)


def apply_site_config(cfg: dict):
    """Override module-level globals with values from site_config.yaml."""
    global SITE, WP_PATH, WP_URL, DB, TELEGRAM_CHAT_ID
    global DAYS_BETWEEN_POSTS, PUBLISH_HOUR_MIN, PUBLISH_HOUR_MAX, SCORE_THRESHOLD
    global META_AUTOPUBLISHED, TOPIC_QUEUE_TABLE, NATURALIZATION_LOG_TABLE
    global AFFILIATE_CATALOG_FILE, AFFILIATE_TAG, AFFILIATE_DISCLOSURE
    global EDITORIAL_RULES_FILE, _GENERATION_SYSTEM

    SITE = cfg["site_id"]
    WP_PATH = cfg["wp_path"]
    WP_URL = cfg["wp_url"]
    DB = cfg["db"]
    TELEGRAM_CHAT_ID = cfg.get("telegram_chat_id", TELEGRAM_CHAT_ID)
    DAYS_BETWEEN_POSTS = cfg.get("post_interval_days", DAYS_BETWEEN_POSTS)
    PUBLISH_HOUR_MIN = cfg.get("publish_hour_min", PUBLISH_HOUR_MIN)
    PUBLISH_HOUR_MAX = cfg.get("publish_hour_max", PUBLISH_HOUR_MAX)
    SCORE_THRESHOLD = cfg.get("score_threshold", SCORE_THRESHOLD)
    META_AUTOPUBLISHED = cfg.get("meta_autopublished", META_AUTOPUBLISHED)
    TOPIC_QUEUE_TABLE = cfg.get("topic_queue_table", TOPIC_QUEUE_TABLE)
    NATURALIZATION_LOG_TABLE = cfg.get("naturalization_log_table", NATURALIZATION_LOG_TABLE)
    AFFILIATE_TAG = cfg.get("affiliate_tag") or ""
    AFFILIATE_DISCLOSURE = cfg.get("affiliate_disclosure") or ""
    if cfg.get("affiliate_catalog_path"):
        AFFILIATE_CATALOG_FILE = Path(cfg["affiliate_catalog_path"])
    EDITORIAL_RULES_FILE = NATURALIZER_DIR / "contextos" / SITE / "editorial_rules.yaml"
    _GENERATION_SYSTEM = _build_generation_system(cfg)

# ── Telegram ──────────────────────────────────────────────────────────────────

def telegram_send(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── DB ────────────────────────────────────────────────────────────────────────

def db_connect():
    return mysql.connector.connect(**DB)


def get_next_topic(conn) -> dict | None:
    """Get highest-priority pending topic from the site's topic queue."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT id, keyword, source, priority, gsc_impressions, gsc_avg_position
           FROM {TOPIC_QUEUE_TABLE}
           WHERE site = %s AND status = 'pending'
           ORDER BY priority DESC, created_at ASC
           LIMIT 1""",
        (SITE,),
    )
    row = cur.fetchone()
    cur.close()
    return row


def mark_topic_in_progress(conn, topic_id: int):
    cur = conn.cursor()
    cur.execute(f"UPDATE {TOPIC_QUEUE_TABLE} SET status='in_progress' WHERE id=%s", (topic_id,))
    conn.commit()
    cur.close()


def mark_topic_done(conn, topic_id: int, wp_post_id: int):
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TOPIC_QUEUE_TABLE} SET status='done', processed_at=NOW(), wp_post_id=%s WHERE id=%s",
        (wp_post_id, topic_id),
    )
    conn.commit()
    cur.close()


def mark_topic_pending(conn, topic_id: int, note: str = ""):
    """Reset to pending on failure."""
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TOPIC_QUEUE_TABLE} SET status='pending', notes=%s WHERE id=%s",
        (note[:500], topic_id),
    )
    conn.commit()
    cur.close()


# ── Publish calendar ──────────────────────────────────────────────────────────

def get_last_scheduled_date(conn) -> datetime | None:
    """
    Get latest post_date among autopublisher posts only (meta _ir_autopublished=1).
    This keeps the series independent from manually-created or blog-generator posts.
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT MAX(p.post_date)
           FROM wp_posts p
           INNER JOIN wp_postmeta m ON m.post_id = p.ID
               AND m.meta_key = %s AND m.meta_value = '1'
           WHERE p.post_status IN ('publish', 'future') AND p.post_type = 'post'""",
        (META_AUTOPUBLISHED,),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row and row[0] else None


def compute_next_publish_datetime(last_date: datetime | None) -> datetime:
    """
    Schedule DAYS_BETWEEN_POSTS days after last_date, random time 08-20h
    with random minutes, seconds, microseconds for naturalness.
    """
    base = last_date if last_date else datetime.now()
    # Strip time, add DAYS_BETWEEN_POSTS full days
    next_day = (base.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=DAYS_BETWEEN_POSTS))
    hour = random.randint(PUBLISH_HOUR_MIN, PUBLISH_HOUR_MAX - 1)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    microsecond = random.randint(0, 999999)
    return next_day.replace(hour=hour, minute=minute, second=second, microsecond=microsecond)


# ── Internal links (embeddings) ───────────────────────────────────────────────

def ollama_available() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        return any("nomic-embed-text" in m for m in models)
    except Exception:
        return False


def get_embedding(text: str):
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30,
        )
        return resp.json().get("embedding")
    except Exception:
        return None


def cosine_similarity(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def find_internal_links(keyword: str, cache: dict, n: int = 4) -> list[dict]:
    """Find most semantically similar existing posts for internal linking."""
    emb = get_embedding(keyword)
    if not emb:
        return []
    sims = []
    for key, data in cache.items():
        post_emb = data.get("embedding")
        if not post_emb:
            continue
        sim = cosine_similarity(emb, post_emb)
        sims.append((sim, {"title": data["title"], "slug": data["slug"], "sim": sim}))
    sims.sort(reverse=True)
    return [item for _, item in sims[:n] if _ > 0.5]


# ── Affiliate catalog ─────────────────────────────────────────────────────────

def load_affiliate_catalog() -> list:
    if AFFILIATE_CATALOG_FILE.exists():
        with open(AFFILIATE_CATALOG_FILE) as f:
            return json.load(f)
    return []


def find_affiliate_products(keyword: str, catalog: list) -> list[dict]:
    """Find catalog products relevant to keyword."""
    kw_words = set(re.findall(r"\b\w{4,}\b", keyword.lower()))
    relevant = []
    for product in catalog:
        product_words = set(
            w.lower() for kw in product.get("keywords", [])
            for w in re.findall(r"\b\w{4,}\b", kw)
        )
        overlap = kw_words & product_words
        if overlap:
            relevant.append({**product, "_overlap": len(overlap)})
    relevant.sort(key=lambda x: x["_overlap"], reverse=True)
    return relevant[:4]


# ── Editorial rules ───────────────────────────────────────────────────────────

def load_editorial_rules() -> dict:
    if EDITORIAL_RULES_FILE.exists():
        with open(EDITORIAL_RULES_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def check_prohibited_topic(keyword: str, rules: dict) -> tuple[bool, str]:
    """Returns (is_prohibited, reason)."""
    kw_lower = keyword.lower()
    for rule in rules.get("prohibited_topics", []):
        for pat in rule.get("keywords", []):
            if pat.lower() in kw_lower:
                # Check exceptions
                exceptions = [e.lower() for e in rule.get("exceptions", [])]
                if any(exc in kw_lower for exc in exceptions):
                    continue
                return True, rule.get("reason", f"Tema prohibido: {pat}")
    return False, ""


def inject_disclaimers(content: str, rules: dict) -> str:
    """Inject required disclaimers based on content keywords."""
    content_lower = content.lower()
    for name, trigger in rules.get("disclaimer_triggers", {}).items():
        keywords = trigger.get("trigger_keywords", [])
        if not any(kw.lower() in content_lower for kw in keywords):
            continue
        disclaimer_html = trigger.get("html", "").strip()
        if not disclaimer_html:
            continue
        placement = trigger.get("placement", "end_of_post")
        # Skip if already present (check for the class name)
        class_match = re.search(r'class="([^"]*disclaimer[^"]*)"', disclaimer_html)
        if class_match and class_match.group(1) in content:
            continue
        if placement == "end_of_post":
            content = content + "\n" + disclaimer_html
        elif placement == "before_first_h2":
            content = re.sub(r"(<h2)", disclaimer_html + r"\n\1", content, count=1)
        elif placement == "before_table":
            content = re.sub(r"(<table)", disclaimer_html + r"\n\1", content, count=1)
        log.info(f"  Disclaimer '{name}' inyectado ({placement})")
    return content


def check_red_flags(content: str, rules: dict) -> list[str]:
    """Return list of red flag matches found in content."""
    content_lower = content.lower()
    found = []
    for flag in rules.get("red_flags", []):
        if flag.get("pattern", "").lower() in content_lower:
            found.append(f"{flag['pattern']}: {flag.get('reason', '')}")
    return found


def strip_h1(content: str) -> str:
    """Remove <h1>...</h1> from content — WP manages the title as H1 via theme."""
    return re.sub(r"<h1[^>]*>.*?</h1>\s*", "", content, count=1, flags=re.IGNORECASE | re.DOTALL).strip()


# ── Image ─────────────────────────────────────────────────────────────────────

def fetch_featured_image(post_id: int, title: str, content: str, rules: dict, dry_run: bool) -> bool:
    """Fetch image from Pexels and set as featured image. Returns True if set."""
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if not pexels_key or dry_run:
        return False
    try:
        # Build search query with Spanish context
        search_ctx = rules.get("images", {}).get("search_context", "Spain")
        snippet = re.sub(r"<[^>]+>", " ", content)[:300]
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": (
                f"Post: {title}\nSnippet: {snippet}\n"
                f"Generate ONE 2-4 word Pexels search query for a professional photo relevant to this Spanish rider/delivery topic. "
                f"Context: {search_ctx}. Reply with ONLY the query."
            )}],
        )
        query = msg.content[0].text.strip().strip('"')
        log.info(f"  Pexels query: '{query}'")

        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": pexels_key},
            params={"query": query, "per_page": 5, "orientation": "landscape", "locale": "es-ES"},
            timeout=10,
        )
        if resp.status_code != 200 or not resp.json().get("photos"):
            log.warning("  Pexels: sin resultados")
            return False

        photo = resp.json()["photos"][0]
        img_url = photo["src"]["large2x"]

        r = requests.get(img_url, timeout=30)
        if r.status_code != 200:
            return False

        # Upload via WP REST API (avoids filesystem permission issues)
        wp_user = os.environ.get("WP_INFOREPARTO_USER", "")
        wp_pass = os.environ.get("WP_INFOREPARTO_APP_PASSWORD", "")
        wp_api  = os.environ.get("WP_INFOREPARTO_URL", f"{WP_URL}/wp-json/wp/v2")
        if not wp_user or not wp_pass:
            log.warning("  fetch_featured_image: WP_INFOREPARTO_USER/APP_PASSWORD no configurados")
            return False

        media_resp = requests.post(
            f"{wp_api}/media",
            auth=(wp_user, wp_pass),
            headers={
                "Content-Disposition": f'attachment; filename="{re.sub(r"[^a-z0-9]+", "-", title.lower())}.jpg"',
                "Content-Type": "image/jpeg",
            },
            data=r.content,
            timeout=30,
        )
        if media_resp.status_code not in (200, 201):
            log.warning(f"  Pexels upload error: {media_resp.status_code} {media_resp.text[:100]}")
            return False

        attachment_id = media_resp.json().get("id")
        if not attachment_id:
            return False

        # Set as featured image
        subprocess.run(
            ["wp", "post", "meta", "update", str(post_id), "_thumbnail_id", str(attachment_id),
             f"--path={WP_PATH}"],
            capture_output=True,
        )
        log.info(f"  Imagen destacada: attachment {attachment_id}")
        return True
    except Exception as e:
        log.warning(f"  fetch_featured_image error: {e}")
    return False


def _upload_image_to_wp(img_bytes: bytes, filename: str) -> str | None:
    """Upload raw image bytes to WP via REST API. Returns URL or None."""
    wp_user = os.environ.get("WP_INFOREPARTO_USER", "")
    wp_pass = os.environ.get("WP_INFOREPARTO_APP_PASSWORD", "")
    wp_api  = os.environ.get("WP_INFOREPARTO_URL", f"{WP_URL}/wp-json/wp/v2")
    if not wp_user or not wp_pass:
        return None
    resp = requests.post(
        f"{wp_api}/media",
        auth=(wp_user, wp_pass),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/jpeg",
        },
        data=img_bytes,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return resp.json().get("source_url")
    return None


def inject_inline_images(content: str, title: str, rules: dict) -> str:
    """
    Fetch 1-2 additional images from Pexels and insert them inline
    after the 1st and 3rd H2 sections (roughly 1/3 and 2/3 of post).
    No caption, no credits.
    """
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if not pexels_key:
        return content

    h2_positions = [m.start() for m in re.finditer(r"<h2[^>]*>", content, re.IGNORECASE)]
    if len(h2_positions) < 2:
        return content  # Not enough H2s to place images

    # Determine insertion points: after 1st H2 section end, after 3rd H2 section end
    insert_indices = []
    for h2_idx in [0, 2]:  # 1st and 3rd H2 (0-indexed)
        if h2_idx >= len(h2_positions):
            break
        section_start = h2_positions[h2_idx]
        # Find end of this H2 section = start of next H2 or end of content
        if h2_idx + 1 < len(h2_positions):
            section_end = h2_positions[h2_idx + 1]
        else:
            section_end = len(content)
        # Insert before the next H2 (or at end)
        insert_indices.append(section_end)

    if not insert_indices:
        return content

    search_ctx = rules.get("images", {}).get("search_context", "Spain")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    # Generate 2 different search queries for variety
    try:
        snippet = re.sub(r"<[^>]+>", " ", content)[:300]
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": (
                f"Post: {title}\nContext: {search_ctx}\n"
                f"Generate 2 different 2-4 word Pexels search queries for inline photos in this Spanish rider/delivery article. "
                f"Make them complementary (e.g. one action shot, one detail). Reply with ONLY: query1|query2"
            )}],
        )
        raw = msg.content[0].text.strip()
        queries = [q.strip().strip('"') for q in raw.split("|")][:2]
        if len(queries) < 2:
            queries = queries * 2
    except Exception:
        return content

    inserted = 0
    offset = 0  # track position shift as we insert HTML

    for i, (ins_pos, query) in enumerate(zip(insert_indices, queries)):
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": pexels_key},
                params={"query": query, "per_page": 5, "orientation": "landscape",
                        "locale": "es-ES", "page": i + 1},
                timeout=10,
            )
            if resp.status_code != 200 or not resp.json().get("photos"):
                continue
            photo = resp.json()["photos"][0]
            img_url = photo["src"]["large"]  # large (not large2x) for inline
            r = requests.get(img_url, timeout=30)
            if r.status_code != 200:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
            url = _upload_image_to_wp(r.content, f"{slug}-{i+1}.jpg")
            if not url:
                continue
            fig_html = (
                f'\n<figure class="wp-block-image size-large">'
                f'<img src="{url}" alt="{title}" loading="lazy"/>'
                f'</figure>\n'
            )
            real_pos = ins_pos + offset
            content = content[:real_pos] + fig_html + content[real_pos:]
            offset += len(fig_html)
            inserted += 1
            log.info(f"  Imagen inline {i+1}: '{query}' → {url[:60]}")
        except Exception as e:
            log.warning(f"  inline image {i+1} error: {e}")

    if inserted:
        log.info(f"  {inserted} imagen(es) inline insertada(s)")
    return content


# ── Research phase ────────────────────────────────────────────────────────────

def research_phase(keyword: str, api_key: str) -> dict:
    """
    Runs Capas 4, 5b (sources only), 6 as research.
    Returns structured brief data.
    """
    result = {
        "competitor_report": None,
        "sources": [],
        "experiences": [],
        "internal_links": [],
        "affiliate_products": [],
    }

    serper_key = os.environ.get("SERPER_API_KEY", "")
    jina_key = os.environ.get("JINA_API_KEY", "")

    # Capa 6: competitive analysis
    if serper_key:
        try:
            from competitor import CompetitorAnalyzer
            analyzer = CompetitorAnalyzer(SITE)
            result["competitor_report"] = analyzer.analyze(keyword, "")
            log.info("  Capa 6: análisis competitivo OK")
        except Exception as e:
            log.warning(f"  Capa 6 error: {e}")

    # Capa 5b: gather sources (without injecting yet)
    if serper_key:
        try:
            sources = _fetch_sources_for_brief(keyword, serper_key, jina_key)
            result["sources"] = sources
            log.info(f"  Capa 5b: {len(sources)} fuentes")
        except Exception as e:
            log.warning(f"  Capa 5b error: {e}")

    # Capa 4: experiences from ExperienceDB
    try:
        from experience_db import ExperienceDB
        exp_db = ExperienceDB(SITE)
        experiences = exp_db.get_for_topic(keyword, limit=3)
        result["experiences"] = experiences
        log.info(f"  Capa 4: {len(experiences)} experiencias")
    except Exception as e:
        log.warning(f"  Capa 4 error: {e}")

    # Internal links via embeddings
    if ollama_available():
        try:
            cache = {}
            if EMBEDDINGS_CACHE_FILE.exists():
                with open(EMBEDDINGS_CACHE_FILE) as f:
                    cache = json.load(f)
            result["internal_links"] = find_internal_links(keyword, cache)
            log.info(f"  Internal links: {len(result['internal_links'])} candidatos")
        except Exception as e:
            log.warning(f"  Internal links error: {e}")

    # Affiliate products
    catalog = load_affiliate_catalog()
    result["affiliate_products"] = find_affiliate_products(keyword, catalog)
    log.info(f"  Afiliados: {len(result['affiliate_products'])} productos relevantes")

    return result


def _fetch_sources_for_brief(keyword: str, serper_key: str, jina_key: str) -> list[dict]:
    """Fetch and verify 2-3 external sources for the brief."""
    headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
    fiscal_words = {"irpf", "reta", "modelo", "declaración", "hacienda", "tributaria",
                    "autónomo", "factura", "deducción", "cotización", "seguridad social"}
    is_fiscal = bool(fiscal_words & set(keyword.lower().split()))

    queries = []
    if is_fiscal:
        queries.append(f"{keyword} site:agenciatributaria.es OR site:seg-social.es OR site:boe.es")
        queries.append(f"{keyword} datos cifras 2026")
    else:
        queries.append(f"{keyword} España 2026 datos")
        queries.append(f"{keyword} normativa reglamento")

    sources = []
    seen_domains = set()

    for query in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "gl": "es", "hl": "es", "num": 5},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            for item in resp.json().get("organic", []):
                url = item.get("link", "")
                if not url or url.lower().endswith(".pdf") or "/pdf/" in url.lower():
                    continue
                domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                # Verify with Jina
                snippet = ""
                try:
                    jina_headers = {"Authorization": f"Bearer {jina_key}"} if jina_key else {}
                    jina_resp = requests.get(
                        f"https://r.jina.ai/{url}",
                        headers=jina_headers,
                        timeout=8,
                    )
                    if jina_resp.status_code == 200:
                        snippet = jina_resp.text[:600].strip()
                except Exception:
                    snippet = item.get("snippet", "")

                if snippet:
                    sources.append({
                        "url": url,
                        "title": item.get("title", domain),
                        "snippet": snippet,
                    })
                    if len(sources) >= 3:
                        return sources
        except Exception:
            continue

    return sources


# ── Brief builder ─────────────────────────────────────────────────────────────

def build_brief(keyword: str, research: dict) -> str:
    """Build structured brief for the generation prompt."""
    parts = [f"BRIEF DE GENERACIÓN — Tema: {keyword}\n"]

    if research["competitor_report"]:
        parts.append("═══════════════════════════════════════")
        parts.append("ANÁLISIS COMPETITIVO (lo que cubre la competencia)")
        parts.append("═══════════════════════════════════════")
        parts.append(research["competitor_report"])

    if research["sources"]:
        parts.append("\n═══════════════════════════════════════")
        parts.append("DATOS Y FUENTES VERIFICADAS (citar de forma natural)")
        parts.append("═══════════════════════════════════════")
        for s in research["sources"]:
            parts.append(f'• {s["title"]}: {s["snippet"][:300]}')
            parts.append(f'  Fuente: {s["url"]}')

    if research["experiences"]:
        parts.append("\n═══════════════════════════════════════")
        parts.append("EXPERIENCIAS REALES (integrar 1-2 de forma natural)")
        parts.append("═══════════════════════════════════════")
        for exp in research["experiences"]:
            type_labels = {
                "metric": "Dato propio", "anecdote": "Anécdota", "regulatory": "Normativa",
                "comparison": "Comparativa", "user_feedback": "Feedback", "process_insight": "Proceso",
            }
            label = type_labels.get(exp.get("type", ""), exp.get("type", ""))
            parts.append(f'  [{label}] "{exp["content"]}"')

    if research["internal_links"]:
        parts.append("\n═══════════════════════════════════════")
        parts.append("POSTS INTERNOS A ENLAZAR (integrar de forma natural en el cuerpo)")
        parts.append("═══════════════════════════════════════")
        for link in research["internal_links"]:
            parts.append(f'  • {link["title"]}: {WP_URL}/{link["slug"]}/')

    if research["affiliate_products"]:
        parts.append("\n═══════════════════════════════════════")
        parts.append("PRODUCTOS AFILIADOS (integrar en el PRIMER TERCIO del post, en sección de recomendaciones o dentro de un párrafo de consejo práctico)")
        parts.append("═══════════════════════════════════════")
        parts.append("Formato enlace: <a href=\"https://www.amazon.es/dp/ASIN/ref=nosim?tag=inforeparto-21\" target=\"_blank\" rel=\"nofollow noopener\">nombre del producto</a>")
        parts.append("Si añades afiliados, incluye este aviso ANTES del primer H2:")
        if AFFILIATE_DISCLOSURE:
            parts.append(f'<p class="aviso-afiliados"><em>{AFFILIATE_DISCLOSURE}</em></p>')
        for p in research["affiliate_products"]:
            parts.append(f'  • {p["name"]} (ASIN: {p["asin"]}) — keywords: {", ".join(p.get("keywords", [])[:3])}')

    return "\n".join(parts)


# ── Generation prompt ─────────────────────────────────────────────────────────

_GENERATION_SYSTEM_INFOREPARTO = """Eres el editor de inforeparto.com, blog para repartidores y riders en España.

Tu misión es escribir un artículo SEO completo, útil y completamente original sobre el tema indicado.

TONO Y VOZ:
- Directo, práctico, tutéa siempre al lector
- Registro informal-medio, como un repartidor veterano que explica algo a un compañero
- Humor e ironía cuando el tema lo permite. Nunca forzado.
- Jerga del sector cuando encaje: curro, pedido, ruta, zona caliente, desconexión, doble app, batear, pico

ESTRUCTURA DEL POST:
- H1: título optimizado (no más de 65 chars), con keyword principal, orientado a resolver un problema
- Intro: 2-3 frases de gancho. PROHIBIDO empezar con definición, "En este artículo..." o generalización
  Usa: escena concreta / dato sorprendente / pregunta provocadora / afirmación contraintuitiva
- H2/H3: naturales, como lo explicaría un colega (no roboticos)
- Longitud: 900-1300 palabras. Posts concisos y útiles > posts relleno.
- 1-2 listas con viñetas máximo por post; el resto narrativa
- Cierre con CTA concreto (no "esperamos que te haya ayudado")

CONTENIDO:
- Usa los datos y fuentes del brief (cítalos de forma natural, sin notas al pie)
- Integra 1-2 experiencias reales del brief donde encajen
- Añade los productos afiliados en el PRIMER TERCIO del post
- Enlaza internamente los posts del brief donde sea natural
- NO inventar datos, cifras o normativas que no estén en el brief

RESTRICCIÓN LEGAL ABSOLUTA:
- NUNCA mencionar "autónomo", "autónomos", "RETA", "cuota de autónomo" en relación a riders de plataforma.
  Motivo: la Ley Rider (RDL 9/2021) los clasifica como trabajadores asalariados.
  Excepción única: Amazon Flex / Amazon Logistics.

FORMATO DE SALIDA:
- HTML completo (h1, h2, h3, p, ul/li, strong, a)
- Sin explicaciones previas, sin markdown, sin bloques de código
- NO incluir <h1> — el título ya lo gestiona WordPress. Empieza directamente con el primer párrafo o <h2>"""

# Active generation system — overridden per site in apply_site_config()
_GENERATION_SYSTEM = _GENERATION_SYSTEM_INFOREPARTO


def _build_generation_system(site_cfg: dict) -> str:
    """Build the generation system prompt from site voice config or use the default."""
    voice_path = NATURALIZER_DIR / "contextos" / site_cfg["site_id"] / "voz.md"
    guardrails_text = ""
    for guardrail in site_cfg.get("content_guardrails", []):
        terms = ", ".join(f'"{t}"' for t in guardrail["prohibited_terms"])
        exc = guardrail.get("exceptions", [])
        exc_text = f" Excepción: {', '.join(exc)}." if exc else ""
        guardrails_text += f"\n- PROHIBIDO usar: {terms}.{exc_text} Motivo: {guardrail['reason']}"

    domain = site_cfg.get("domain", "")
    description = site_cfg.get("description", "")

    base = f"""Eres el editor de {domain}, {description}.

Tu misión es escribir un artículo SEO completo, útil y completamente original sobre el tema indicado.
"""
    if voice_path.exists():
        base += f"\nVOZ EDITORIAL:\n{voice_path.read_text()}\n"

    base += """
ESTRUCTURA DEL POST:
- H1: título optimizado (no más de 65 chars), con keyword principal
- Intro: 2-3 frases de gancho. PROHIBIDO empezar con definición o "En este artículo..."
- H2/H3: naturales y conversacionales
- Longitud: 900-1300 palabras
- Cierre con CTA concreto

CONTENIDO:
- Usa los datos y fuentes del brief
- NO inventar datos, cifras o normativas que no estén en el brief
"""
    if guardrails_text:
        base += f"\nRESTRICCIONES OBLIGATORIAS:{guardrails_text}\n"

    base += """
FORMATO DE SALIDA:
- HTML completo (h1, h2, h3, p, ul/li, strong, a)
- Sin explicaciones previas, sin markdown, sin bloques de código
- NO incluir <h1> — el título ya lo gestiona WordPress. Empieza con el primer párrafo o <h2>"""

    return base


def generate_post(keyword: str, brief: str, settings: dict, api_key: str) -> str:
    """Generate post HTML from keyword + brief using Claude Sonnet."""
    client = anthropic.Anthropic(api_key=api_key)
    model = settings.get("models", {}).get("naturalizacion", "claude-sonnet-4-6")

    user_content = f"Escribe un artículo completo sobre: {keyword}\n\n{brief}"

    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=_GENERATION_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    return _strip_code_fences(resp.content[0].text)


# ── Extract title from generated HTML ─────────────────────────────────────────

def extract_title(html: str, fallback: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return fallback


# ── WP publish ────────────────────────────────────────────────────────────────

def publish_to_wp(title: str, content: str, publish_dt: datetime, dry_run: bool) -> int | None:
    """
    Creates post in WP as 'future' (scheduled). Returns post ID or None.
    Uses WP CLI.
    """
    if dry_run:
        log.info(f"  [dry-run] Publicaría '{title[:50]}' el {publish_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        return 99999

    date_str = publish_dt.strftime("%Y-%m-%dT%H:%M:%S")
    result = subprocess.run(
        [
            "wp", "post", "create",
            f"--post_title={title}",
            f"--post_content={content}",
            f"--post_date={date_str}",
            "--post_status=future",
            "--post_type=post",
            "--porcelain",
            f"--path={WP_PATH}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip().isdigit():
        post_id = int(result.stdout.strip())
        # Mark as autopublisher post so the calendar only tracks its own series
        subprocess.run(
            ["wp", "post", "meta", "add", str(post_id), META_AUTOPUBLISHED, "1",
             f"--path={WP_PATH}"],
            capture_output=True,
        )
        return post_id
    log.error(f"  WP CLI error: {result.stderr[:200]}")
    return None


def save_as_draft(title: str, content: str, dry_run: bool) -> int | None:
    """Save failed post as draft for manual review."""
    if dry_run:
        return None
    result = subprocess.run(
        [
            "wp", "post", "create",
            f"--post_title={title}",
            f"--post_content={content}",
            "--post_status=draft",
            "--post_type=post",
            "--porcelain",
            f"--path={WP_PATH}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


# ── Schema markup ────────────────────────────────────────────────────────────

_H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
_P_AFTER_H_RE = re.compile(r"</h[23][^>]*>\s*<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_OL_RE = re.compile(r"<ol[^>]*>(.*?)</ol>", re.IGNORECASE | re.DOTALL)
_LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _STRIP_TAGS_RE.sub("", s).strip()


def detect_schema_type(html: str, title: str) -> str:
    """Detect the most appropriate Schema.org type for the given post HTML."""
    title_lower = title.lower()
    headings = [_strip_tags(h) for h in _H2_RE.findall(html) + _H3_RE.findall(html)]

    # FAQPage: headings ending in "?"
    faq_headings = [h for h in headings if h.strip().endswith("?")]
    if len(faq_headings) >= 2:
        return "FAQPage"

    # HowTo: ordered list or sequential H2/H3 steps
    if _OL_RE.search(html):
        return "HowTo"

    # ItemList: comparative / best-of titles or headings
    comparative_signals = ["mejor", "mejores", "top ", "ranking", "comparativa", "vs"]
    if any(sig in title_lower for sig in comparative_signals):
        return "ItemList"

    return "Article"


def build_schema_jsonld(schema_type: str, html: str, title: str, url: str) -> str:
    """Generate a JSON-LD <script> block for the given schema type."""
    if schema_type == "FAQPage":
        headings = list(_H2_RE.finditer(html)) + list(_H3_RE.finditer(html))
        qa_pairs = []
        for m in headings:
            question = _strip_tags(m.group(1)).strip()
            if not question.endswith("?"):
                continue
            # First paragraph after this heading
            after = html[m.end():]
            p_match = re.search(r"<p[^>]*>(.*?)</p>", after, re.IGNORECASE | re.DOTALL)
            answer = _strip_tags(p_match.group(1))[:300] if p_match else ""
            if answer:
                qa_pairs.append({"question": question, "answer": answer})
            if len(qa_pairs) >= 5:
                break
        if not qa_pairs:
            return ""
        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": qa["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": qa["answer"]},
                }
                for qa in qa_pairs
            ],
        }

    elif schema_type == "HowTo":
        steps = []
        ol_match = _OL_RE.search(html)
        if ol_match:
            for i, li in enumerate(_LI_RE.finditer(ol_match.group(1)), 1):
                text = _strip_tags(li.group(1))[:200]
                if text:
                    steps.append({
                        "@type": "HowToStep",
                        "position": i,
                        "name": text[:60],
                        "text": text,
                    })
        schema = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": title,
            "step": steps,
        }

    elif schema_type == "ItemList":
        headings = [_strip_tags(h) for h in _H2_RE.findall(html)]
        items = [
            {"@type": "ListItem", "position": i, "name": h}
            for i, h in enumerate(headings[:10], 1)
            if h
        ]
        schema = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": title,
            "itemListElement": items,
        }

    else:  # Article (default)
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "url": url,
            "publisher": {
                "@type": "Organization",
                "name": WP_URL.replace("https://", "").replace("http://", ""),
                "url": WP_URL,
            },
        }

    return f'\n<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n</script>'


# ── Affiliate link tracking rewriter ─────────────────────────────────────────

_AMAZON_LINK_RE = re.compile(
    r'href="https://www\.amazon\.es/dp/([A-Z0-9]{10})[^"]*"',
    re.IGNORECASE,
)


def rewrite_affiliate_links(html: str, wp_post_id: int) -> str:
    """Replace Amazon affiliate links with click-tracking URLs that redirect to Amazon.

    Position is assigned by relative order: first third → top, middle → middle, last → bottom.
    """
    links = _AMAZON_LINK_RE.findall(html)
    if not links:
        return html

    total = len(links)
    counter = [0]  # mutable for use in sub()

    def replacer(m: re.Match) -> str:
        asin = m.group(1).upper()
        idx = counter[0]
        counter[0] += 1
        if total == 1:
            position = "middle"
        elif idx < total / 3:
            position = "top"
        elif idx < 2 * total / 3:
            position = "middle"
        else:
            position = "bottom"
        tracking_url = f"/tracking/click.php?asin={asin}&post_id={wp_post_id}&position={position}"
        return f'href="{tracking_url}"'

    return _AMAZON_LINK_RE.sub(replacer, html)


def update_post_content(wp_post_id: int, content: str) -> bool:
    """Update the content of an existing WP post via WP CLI."""
    result = subprocess.run(
        [
            "wp", "post", "update", str(wp_post_id),
            f"--post_content={content}",
            f"--path={WP_PATH}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return True
    log.error(f"  WP update error: {result.stderr[:200]}")
    return False


# ── Naturalization ────────────────────────────────────────────────────────────

def naturalize_content(content: str, title: str, research: dict) -> tuple[str, dict, bool, list]:
    """
    Apply naturalization capas 1+2+3+3b to generated content.
    Returns (naturalized_content, score, integrity_ok, issues).
    """
    settings, patterns, expresiones = load_config()
    voice = load_voice(SITE)
    threshold = settings.get("natural_score", {}).get("thresholds", {}).get("ok", SCORE_THRESHOLD)
    max_retries = settings.get("natural_score", {}).get("max_retries", 2)
    bad_openers = patterns.get("malas_aperturas", [])

    # Build system prompt (1+2+3+3b + experiences + competitor report from research)
    system_prompt = build_system_prompt(
        patterns, expresiones, voice,
        experiences=research.get("experiences") or None,
        competitor_report=research.get("competitor_report"),
    )

    clean_content, placeholders = extract_protected(content)

    best_result = None
    best_score = None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    for attempt in range(max_retries + 1):
        raw = _naturalize_api_call(clean_content, title, system_prompt, settings)
        raw = _strip_code_fences(raw)
        sc = NaturalScorer.score(raw, patterns, bad_openers)
        if best_score is None or sc["overall"] > best_score["overall"]:
            best_result = raw
            best_score = sc
        if sc["overall"] >= threshold:
            break

    naturalized = restore_protected(best_result, placeholders)

    # Capa 5b: inject sources (now that content exists)
    serper_key = os.environ.get("SERPER_API_KEY", "")
    sources_added = []
    if serper_key:
        try:
            from sources import SourceInjector
            injector = SourceInjector(SITE)
            naturalized, sources_added = injector.inject(naturalized, title)
        except Exception as e:
            log.warning(f"  Capa 5b inject error: {e}")

    # Recalculate score with source_density
    if sources_added:
        density = min(1.0, len(sources_added) / 3)
        best_score = NaturalScorer.score(best_result, patterns, bad_openers, source_density=density)

    # Capa 6b: author byline + schema
    try:
        naturalized, _ = inject_author_signals(
            naturalized, site=SITE, post_title=title, post_url="", post_date="",
        )
    except Exception as e:
        log.warning(f"  Capa 6b error: {e}")

    # Capa 8: integrity
    integrity_ok, issues = check_integrity(content, naturalized, title, settings)

    return naturalized, best_score, integrity_ok, issues


# ── Naturalization log ────────────────────────────────────────────────────────

def log_to_db(title: str, wp_post_id: int, score: dict, research: dict, schema_type: str = "Article"):
    try:
        conn = db_connect()
        cur = conn.cursor()
        experiences_used = [e["content"][:60] for e in research.get("experiences", [])]
        sources_added = [s.get("url", "") for s in research.get("sources", [])]
        cur.execute(
            f"""INSERT INTO {NATURALIZATION_LOG_TABLE}
               (site, topic, wp_post_id, score_after, experiences_used, sources_added, schema_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                SITE, title, wp_post_id, score["overall"],
                json.dumps(experiences_used, ensure_ascii=False),
                json.dumps(sources_added, ensure_ascii=False),
                schema_type,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning(f"  Log DB error: {e}")


def log_post_performance(
    wp_post_id: int,
    keyword: str,
    search_intent: str,
    schema_type: str,
    html: str,
    score: float,
    research: dict,
    has_disclaimer: bool,
    published_at,
):
    """Insert initial row in post_performance for a newly published post."""
    try:
        import re as _re
        word_count = len(_re.sub(r"<[^>]+>", "", html).split())
        num_affiliates = len(research.get("affiliate_products", []))
        num_internal = len(research.get("internal_links", []))
        num_images = html.count("<img ")
        conn = db_connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO post_performance
               (post_id, site, keyword, search_intent, schema_type, word_count,
                natural_score, num_affiliates, num_internal_links, num_images,
                has_disclaimer, published_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               natural_score=VALUES(natural_score), schema_type=VALUES(schema_type)""",
            (
                wp_post_id, SITE, keyword, search_intent, schema_type, word_count,
                score, num_affiliates, num_internal, num_images,
                int(has_disclaimer), published_at,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning(f"  post_performance insert error: {e}")


def ping_sitemap():
    """Ping Google with the sitemap URL to trigger re-crawling."""
    try:
        sitemap_url = f"{WP_URL}/sitemap_index.xml"
        resp = requests.get(
            "https://www.google.com/ping",
            params={"sitemap": sitemap_url},
            timeout=10,
        )
        log.info(f"  Sitemap ping: {resp.status_code}")
    except Exception as e:
        log.warning(f"  Sitemap ping error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Generate even if already ran today")
    parser.add_argument("--topic", type=str, default=None, help="Override topic selection")
    parser.add_argument("--site", type=str, default="inforeparto", help="Site ID (default: inforeparto)")
    args = parser.parse_args()

    # Load and apply site-specific configuration
    from site_config import load_site_config
    try:
        site_cfg = load_site_config(args.site)
        apply_site_config(site_cfg)
        log.info(f"Site config cargado: {args.site} ({site_cfg.get('domain', '')})")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.error("ANTHROPIC_API_KEY no encontrada")
        sys.exit(1)

    if not NATURALIZER_AVAILABLE:
        log.error(f"Naturalizer no disponible: {_nat_err_msg}")
        sys.exit(1)

    log.info(f"{'[DRY-RUN] ' if args.dry_run else ''}Autopublisher — {date.today().isoformat()}")

    # ── Load editorial rules ──────────────────────────────────────────────────
    rules = load_editorial_rules()

    conn = db_connect()

    # ── Topic selection ───────────────────────────────────────────────────────
    if args.topic:
        keyword = args.topic.strip()
        topic_id = None
        log.info(f"Tema manual: {keyword}")
    else:
        topic = get_next_topic(conn)
        if not topic:
            log.info("No hay temas pendientes en ir_topic_queue. Añade temas o espera al lunes.")
            telegram_send("⚠️ <b>Autopublisher</b>: no hay temas en cola. Ejecuta gsc-topic-discovery o añade manualmente.")
            conn.close()
            return
        keyword = topic["keyword"]
        topic_id = topic["id"]
        log.info(f"Tema seleccionado: [{topic_id}] {keyword} (p={topic['priority']:.2f})")
        if not args.dry_run:
            mark_topic_in_progress(conn, topic_id)

    # ── Prohibited topic check ────────────────────────────────────────────────
    is_prohibited, reason = check_prohibited_topic(keyword, rules)
    if is_prohibited:
        log.warning(f"Tema prohibido: {keyword} — {reason}")
        if topic_id:
            conn2 = db_connect()
            cur = conn2.cursor()
            cur.execute("UPDATE ir_topic_queue SET status='skipped', notes=%s WHERE id=%s",
                        (f"Prohibido: {reason}"[:500], topic_id))
            conn2.commit()
            cur.close()
            conn2.close()
        telegram_send(f"🚫 <b>Autopublisher — Tema prohibido</b>\n<i>{keyword}</i>\n{reason}")
        conn.close()
        return

    # ── Compute publish date ──────────────────────────────────────────────────
    last_date = get_last_scheduled_date(conn)
    publish_dt = compute_next_publish_datetime(last_date)
    log.info(f"Fecha de publicación: {publish_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    conn.close()

    # ── Research phase ────────────────────────────────────────────────────────
    log.info("Research phase...")
    research = research_phase(keyword, api_key)

    has_affiliates = bool(research["affiliate_products"])
    if not has_affiliates:
        telegram_send(
            f"💡 <b>Sin afiliados para:</b> <i>{keyword}</i>\n"
            f"Considera añadir productos relevantes al catálogo."
        )

    # ── Build brief ───────────────────────────────────────────────────────────
    brief = build_brief(keyword, research)
    log.info(f"Brief construido ({len(brief)} chars)")

    # ── Generate post (with content_guardrails retry) ────────────────────────
    log.info("Generando post (Sonnet)...")
    settings, _, _ = load_config()
    raw_html = None
    guardrails = site_cfg.get("content_guardrails", [])

    for attempt in range(2):
        try:
            _brief = brief
            if attempt == 1 and guardrails:
                reinforcement = "⚠️ RESTRICCIONES CRÍTICAS que debes cumplir estrictamente:\n"
                for g in guardrails:
                    terms_str = ", ".join(f'"{t}"' for t in g["prohibited_terms"])
                    reinforcement += f"- PROHIBIDO usar: {terms_str}. {g['reason']}\n"
                log.warning("  Retry: añadiendo refuerzo de guardrails al brief")
                _brief = reinforcement + "\n" + brief
            raw_html = generate_post(keyword, _brief, settings, api_key)
        except Exception as e:
            log.error(f"Error en generación (intento {attempt+1}): {e}")
            if topic_id:
                conn = db_connect()
                mark_topic_pending(conn, topic_id, f"generation error: {e}")
                conn.close()
            telegram_send(f"❌ <b>Autopublisher error</b>\nTema: {keyword}\nFallo: generación\n{e}")
            sys.exit(1)

        # Check all guardrails
        content_lower = raw_html.lower()
        violations = []
        for guardrail in guardrails:
            hits = [t for t in guardrail["prohibited_terms"] if t.lower() in content_lower]
            if hits:
                exceptions = guardrail.get("exceptions", [])
                if not any(exc.lower() in content_lower for exc in exceptions):
                    violations.append((hits, guardrail["reason"], guardrail.get("retry_with_reinforced_brief", True)))

        if not violations:
            break  # Clean — proceed
        if attempt == 0:
            log.warning(f"  Intento 1: guardrail violation {[v[0] for v in violations]}, reintentando...")
        else:
            reason = f"Guardrail violation tras 2 intentos: {[v[0] for v in violations]}"
            log.error(f"BLOQUEADO: {reason}")
            if topic_id:
                conn = db_connect()
                mark_topic_pending(conn, topic_id, reason)
                conn.close()
            telegram_send(f"🚫 <b>Autopublisher — Contenido bloqueado</b>\nTema: {keyword}\n{reason}")
            sys.exit(1)

    title = extract_title(raw_html, keyword)
    # Capitalize first letter — generation model often returns lowercase titles
    if title:
        title = title[0].upper() + title[1:]
    log.info(f"Título generado: {title}")

    # Strip H1 from content — WP manages the title as H1
    raw_html = strip_h1(raw_html)
    log.info(f"HTML generado: {len(raw_html)} chars (H1 eliminado)")

    # ── Red flag check (pre-naturalization) ───────────────────────────────────
    red_flags = check_red_flags(raw_html, rules)
    if red_flags:
        log.warning(f"Red flags detectadas: {red_flags}")
        # Non-blocking: log but continue (naturalizer may fix wording)

    # ── Naturalize ────────────────────────────────────────────────────────────
    log.info("Naturalizando (capas 1+2+3+3b+5b+6b+7+8)...")
    try:
        naturalized, score, integrity_ok, issues = naturalize_content(raw_html, title, research)
    except Exception as e:
        log.error(f"Error en naturalización: {e}")
        if topic_id:
            conn = db_connect()
            mark_topic_pending(conn, topic_id, f"naturalize error: {e}")
            conn.close()
        telegram_send(f"❌ <b>Autopublisher error</b>\nTema: {keyword}\nFallo: naturalización\n{e}")
        sys.exit(1)

    # ── Inject disclaimers ────────────────────────────────────────────────────
    naturalized = inject_disclaimers(naturalized, rules)

    # ── Schema markup ─────────────────────────────────────────────────────────
    post_url = f"{WP_URL}/{keyword.replace(' ', '-').lower()}/"
    schema_type = detect_schema_type(naturalized, title)
    schema_jsonld = build_schema_jsonld(schema_type, naturalized, title, post_url)
    if schema_jsonld:
        naturalized = naturalized + schema_jsonld
        log.info(f"  Schema inyectado: {schema_type}")

    score_val = score["overall"]
    score_emoji = "✅" if score_val >= 70 else ("⚠️" if score_val >= 50 else "❌")
    log.info(f"NaturalScore: {score_val}/100 {score_emoji}")
    if not integrity_ok:
        log.warning(f"Integridad (Capa 8): {issues}")

    # ── Publish or draft ──────────────────────────────────────────────────────
    conn = db_connect()

    if score_val >= SCORE_THRESHOLD:
        # Inject inline images before publishing (modifies content)
        if not args.dry_run:
            naturalized = inject_inline_images(naturalized, title, rules)

        wp_post_id = publish_to_wp(title, naturalized, publish_dt, args.dry_run)
        if wp_post_id:
            # Rewrite affiliate links to tracking URLs now that we have the post ID
            if not args.dry_run:
                tracked_html = rewrite_affiliate_links(naturalized, wp_post_id)
                if tracked_html != naturalized:
                    update_post_content(wp_post_id, tracked_html)
                    log.info("  Affiliate links reescritos a tracking URLs")

            # Featured image (no credits, Spanish context)
            img_set = fetch_featured_image(wp_post_id, title, naturalized, rules, args.dry_run)

            if topic_id and not args.dry_run:
                mark_topic_done(conn, topic_id, wp_post_id)
            if not args.dry_run:
                log_to_db(title, wp_post_id, score, research, schema_type)
                ping_sitemap()
                # Record initial performance row
                topic_row = research.get("_topic_row", {})
                log_post_performance(
                    wp_post_id=wp_post_id,
                    keyword=keyword,
                    search_intent=topic_row.get("search_intent", "informational"),
                    schema_type=schema_type,
                    html=naturalized,
                    score=score_val,
                    research=research,
                    has_disclaimer="disclaimer" in naturalized.lower(),
                    published_at=publish_dt,
                )

            preview_url = f"{WP_URL}/?p={wp_post_id}"
            lines = [
                f"✅ <b>Post generado y programado</b>",
                f"📌 {title}",
                f"📅 Publicación: {publish_dt.strftime('%A %d %B · %H:%M')}h",
                f"🔗 <a href='{preview_url}'>Preview WP</a>",
                f"📊 NaturalScore: {score_val}/100",
                f"🖼️ Imagen: {'✅' if img_set else '—'}",
                f"🔗 Fuentes: {len(research['sources'])} | Experiencias: {len(research['experiences'])} | Afiliados: {len(research['affiliate_products'])}",
            ]
            if not integrity_ok:
                lines.append(f"⚠️ Integridad: {'; '.join(issues[:2])}")
            if red_flags:
                lines.append(f"⚠️ Red flags revisadas: {len(red_flags)}")
            telegram_send("\n".join(lines))
            log.info(f"Post {wp_post_id} programado para {publish_dt}")
        else:
            log.error("WP publish falló")
            if topic_id:
                mark_topic_pending(conn, topic_id, "wp publish failed")
            telegram_send(f"❌ <b>Autopublisher</b>: WP publish falló\nTema: {keyword}")
    else:
        # Score too low → save as draft
        draft_id = save_as_draft(title, naturalized, args.dry_run)
        if topic_id and not args.dry_run:
            mark_topic_pending(conn, topic_id, f"score too low: {score_val}")
        log.warning(f"Score {score_val} < {SCORE_THRESHOLD} — guardado como draft {draft_id}")
        telegram_send(
            f"⚠️ <b>Post no publicado (score bajo)</b>\n"
            f"📌 {title}\n"
            f"📊 NaturalScore: {score_val}/100\n"
            f"📝 Guardado como borrador ID {draft_id}\n"
            f"Motivo: {'; '.join(issues[:2]) if issues else 'apertura genérica o patrones IA'}"
        )

    conn.close()
    log.info("Autopublisher completado.")


if __name__ == "__main__":
    main()
