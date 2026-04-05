#!/usr/bin/env python3
"""
experience_enricher.py — Scraping de experiencias reales de repartidores para la base de datos.

Busca testimonios y experiencias en foros, Reddit, Forocoches, etc. usando Serper + Jina,
extrae frases clave con Haiku y deduplica con embeddings Ollama.

Cron: 1 y 15 de cada mes, 03:00
  cd /home/devops/projects/inforeparto/scripts && python3 experience_enricher.py

Uso:
  python3 experience_enricher.py
  python3 experience_enricher.py --dry-run
  python3 experience_enricher.py --max 20
"""

import argparse
import json
import logging
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
import mysql.connector
import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env.projects", override=False)

sys.path.insert(0, str(Path(__file__).parent))
from site_config import load_site_config

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / f"experience-enricher-{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

SITE = "inforeparto"
DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)
EXPERIENCE_TABLE = "ir_experience_bank"

MAX_NEW_EXPERIENCES = 30
DEDUP_THRESHOLD = 0.85  # cosine similarity above this → duplicate

# Search queries targeting forums, Reddit, and discussion threads
SEARCH_QUERIES = [
    "repartidor glovo experiencia foro site:reddit.com OR site:forocoches.com",
    "rider uber eats opinión Spain forum experiencia real",
    "autónomo repartidor Spain testimonio problemas ingresos",
    "deliveroo repartidor España experiencia personal",
    "amazon flex repartidor comentario experiencia",
    "stuart mensajero ciudad experiencia real",
    "repartidor bicicleta ingresos hora experiencia",
    "trabajar glovo experiencia negativa positiva España",
    "rider ingresos reales mes España foro",
    "repartidor en moto España testimonios accidentes seguros",
]


def db_connect():
    return mysql.connector.connect(**DB)


def telegram_send(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram error: {e}")


# ── Embeddings ─────────────────────────────────────────────────────────────────

def get_embedding(text: str):
    """Request a nomic-embed-text embedding from the local Ollama instance. Returns list or None."""
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


def ollama_available() -> bool:
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        return any("nomic-embed-text" in m for m in models)
    except Exception:
        return False


# ── Serper search ──────────────────────────────────────────────────────────────

def serper_search(query: str, num_results: int = 5) -> list[dict]:
    """Search with Serper and return organic results."""
    if not SERPER_API_KEY:
        log.warning("SERPER_API_KEY no configurada")
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num_results, "hl": "es", "gl": "es"},
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning(f"Serper {resp.status_code}: {query[:50]}")
            return []
        return resp.json().get("organic", [])
    except Exception as e:
        log.warning(f"Serper error: {e}")
        return []


# ── Jina scraping ──────────────────────────────────────────────────────────────

def jina_scrape(url: str) -> str:
    """Scrape a URL using Jina Reader. Returns text content (max 8000 chars)."""
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/plain"},
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.text[:8000]
        return ""
    except Exception as e:
        log.warning(f"Jina error ({url[:60]}): {e}")
        return ""


# ── Haiku extraction ───────────────────────────────────────────────────────────

def extract_experiences_with_haiku(text: str, source_url: str) -> list[dict]:
    """
    Use Claude Haiku to extract 1-5 first-person rider experiences from raw text.
    Returns list of {quote, topic, platform}.
    """
    if not text.strip():
        return []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "Extrae 1-5 experiencias o testimonios reales de repartidores de este texto. "
                    "Solo frases que sean testimonios genuinos en primera persona o descripciones "
                    "directas de experiencias reales (ingresos, condiciones, plataformas, accidentes, etc.).\n\n"
                    f"Texto:\n{text[:4000]}\n\n"
                    "Responde SOLO con un JSON array. Cada elemento: "
                    '{"quote": "frase exacta o parafraseada", "topic": "ingresos|condiciones|plataforma|accidente|equipo|otro", "platform": "glovo|ubereats|deliveroo|amazon_flex|stuart|general"}\n'
                    "Si no hay testimonios relevantes, responde: []"
                ),
            }],
        )
        raw = msg.content[0].text.strip()
        # Extract JSON from response
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not json_match:
            return []
        items = json.loads(json_match.group())
        results = []
        for item in items:
            if isinstance(item, dict) and item.get("quote") and len(item["quote"]) > 30:
                results.append({
                    "quote": item["quote"].strip(),
                    "topic": item.get("topic", "otro"),
                    "platform": item.get("platform", "general"),
                    "source_url": source_url,
                })
        return results
    except Exception as e:
        log.warning(f"Haiku extraction error: {e}")
        return []


# ── Database ───────────────────────────────────────────────────────────────────

def get_existing_embeddings(conn) -> list[dict]:
    """Load all existing experience embeddings for deduplication."""
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT id, quote, embedding_json FROM {EXPERIENCE_TABLE} WHERE embedding_json IS NOT NULL")
    rows = cur.fetchall()
    cur.close()
    result = []
    for row in rows:
        try:
            emb = json.loads(row["embedding_json"])
            result.append({"id": row["id"], "quote": row["quote"], "embedding": emb})
        except Exception:
            pass
    return result


def is_duplicate(new_embedding, existing_embeddings: list, threshold: float) -> bool:
    """Return True if any existing experience has cosine similarity >= threshold."""
    for item in existing_embeddings:
        if cosine_similarity(new_embedding, item["embedding"]) >= threshold:
            return True
    return False


def insert_experience(conn, exp: dict, embedding: list, dry_run: bool) -> bool:
    """Insert a new experience into ir_experience_bank. Returns True if inserted."""
    if dry_run:
        return True
    try:
        cur = conn.cursor()
        cur.execute(
            f"""INSERT INTO {EXPERIENCE_TABLE}
                (site, quote, topic, platform, source_url, embedding_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
            (
                SITE,
                exp["quote"],
                exp["topic"],
                exp["platform"],
                exp["source_url"],
                json.dumps(embedding),
            ),
        )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        log.warning(f"Insert experience error: {e}")
        return False


def ensure_experience_table(conn):
    """Create ir_experience_bank if it doesn't exist."""
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {EXPERIENCE_TABLE} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            site VARCHAR(50) NOT NULL,
            quote TEXT NOT NULL,
            topic VARCHAR(50) DEFAULT 'otro',
            platform VARCHAR(50) DEFAULT 'general',
            source_url VARCHAR(500),
            embedding_json MEDIUMTEXT,
            used_count INT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_site (site),
            INDEX idx_topic (topic),
            INDEX idx_platform (platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cur.close()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Enrich experience bank with real rider testimonials")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max", type=int, default=MAX_NEW_EXPERIENCES, help="Max new experiences to insert")
    parser.add_argument("--site", type=str, default="inforeparto")
    args = parser.parse_args()

    global SITE, DB, TELEGRAM_CHAT_ID

    try:
        cfg = load_site_config(args.site)
        SITE = cfg["site_id"]
        DB = cfg["db"]
        TELEGRAM_CHAT_ID = cfg.get("telegram_chat_id", TELEGRAM_CHAT_ID)
        log.info(f"Site: {SITE} ({cfg.get('domain', '')})")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    if not SERPER_API_KEY:
        log.error("SERPER_API_KEY no configurada — abortando")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY no configurada — abortando")
        sys.exit(1)

    use_dedup = ollama_available()
    if not use_dedup:
        log.warning("Ollama/nomic-embed-text no disponible — deduplicación desactivada")

    prefix = "[DRY-RUN] " if args.dry_run else ""
    log.info(f"{prefix}Experience enricher — {date.today().isoformat()}")

    conn = db_connect()
    ensure_experience_table(conn)

    existing_embeddings = get_existing_embeddings(conn) if use_dedup else []
    log.info(f"Experiencias existentes en DB: {len(existing_embeddings)}")

    # Collect all candidate experiences
    all_candidates = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        log.info(f"Buscando: {query[:70]}")
        results = serper_search(query, num_results=5)
        for result in results:
            url = result.get("link", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            log.info(f"  Scrapeando: {url[:70]}")
            text = jina_scrape(url)
            if not text:
                continue

            experiences = extract_experiences_with_haiku(text, url)
            if experiences:
                log.info(f"  Extraídas: {len(experiences)} experiencias")
                all_candidates.extend(experiences)

    log.info(f"Total candidatos extraídos: {len(all_candidates)}")

    # Deduplicate and insert
    inserted = 0
    skipped_dup = 0

    for exp in all_candidates:
        if inserted >= args.max:
            break

        quote = exp["quote"]

        if use_dedup:
            embedding = get_embedding(quote)
            if not embedding:
                continue
            if is_duplicate(embedding, existing_embeddings, DEDUP_THRESHOLD):
                skipped_dup += 1
                continue
        else:
            embedding = []

        log.info(f"  {'[DRY] ' if args.dry_run else ''}Insertando: {quote[:80]}")
        if insert_experience(conn, exp, embedding, args.dry_run):
            inserted += 1
            if use_dedup and embedding:
                # Add to in-memory cache to avoid intra-run duplicates
                existing_embeddings.append({"id": -1, "quote": quote, "embedding": embedding})

    conn.close()

    log.info(f"Completado: {inserted} nuevas experiencias, {skipped_dup} duplicados omitidos")

    if not args.dry_run:
        telegram_send(
            f"🗣️ <b>Experience Enricher — {date.today().isoformat()}</b>\n"
            f"Site: {SITE}\n"
            f"Candidatos extraídos: {len(all_candidates)}\n"
            f"Nuevas experiencias: {inserted}\n"
            f"Duplicados omitidos: {skipped_dup}\n"
            f"Total en DB: {len(existing_embeddings)}"
        )
    else:
        log.info(f"[DRY-RUN] Hubiera insertado: {inserted} experiencias")


if __name__ == "__main__":
    main()
