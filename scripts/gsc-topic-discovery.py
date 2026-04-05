#!/usr/bin/env python3
"""
gsc-topic-discovery.py — Alimenta ir_topic_queue con gaps de GSC + gaps semánticos.

Cron: 04:00 Lunes
  cd /home/devops/projects/inforeparto/scripts && source /home/devops/.env.projects && python3 gsc-topic-discovery.py

Uso manual:
  python3 gsc-topic-discovery.py
  python3 gsc-topic-discovery.py --dry-run
  python3 gsc-topic-discovery.py --days 90   # rango GSC (default 90)
  python3 gsc-topic-discovery.py --min-impressions 30
"""

import argparse
import json
import logging
import os
import sys
import re
from datetime import date, timedelta, datetime
from pathlib import Path

import mysql.connector
import requests
import google.auth.transport.requests
import google.oauth2.service_account
from dotenv import load_dotenv

# Cargar .env.projects antes de leer cualquier variable de entorno
load_dotenv(Path.home() / ".env.projects", override=False)

# ── Config ────────────────────────────────────────────────────────────────────

CREDENTIALS_PATH = os.environ.get("GSC_CREDENTIALS", "/home/devops/.credentials/gsc-serviceaccount.json")
GSC_SITE = "https://inforeparto.com/"
WP_URL = "https://inforeparto.com"
SITE = "inforeparto"

DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Thresholds
MIN_IMPRESSIONS = 30          # queries con menos impresiones → ignorar
MAX_POSITION_GAP = 40         # posición peor que esto → oportunidad
SIMILARITY_THRESHOLD = 0.82   # similitud embeddings → ya tenemos post similar
MAX_NEW_TOPICS = 20           # máximo topics a añadir por run
EMBEDDINGS_CACHE_FILE = Path(__file__).parent / "post_embeddings.json"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / f"gsc-topic-discovery-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ── Telegram ──────────────────────────────────────────────────────────────────

def telegram_send(text: str):
    """Send an HTML-formatted message to the configured Telegram chat."""
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
    """Return a new MariaDB connection using DB config from environment."""
    return mysql.connector.connect(**DB)


def get_existing_keywords(conn) -> set:
    """Keywords ya en la cola (cualquier estado)."""
    cur = conn.cursor()
    cur.execute("SELECT keyword FROM ir_topic_queue WHERE site = %s", (SITE,))
    keywords = {row[0].lower() for row in cur.fetchall()}
    cur.close()
    return keywords


def insert_topics(conn, topics: list[dict], dry_run: bool) -> int:
    """Insert new topics into ir_topic_queue. Returns count inserted."""
    if not topics or dry_run:
        return 0
    cur = conn.cursor()
    inserted = 0
    for t in topics:
        try:
            cur.execute(
                """INSERT IGNORE INTO ir_topic_queue
                   (site, keyword, source, priority, gsc_impressions, gsc_avg_position)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    SITE,
                    t["keyword"],
                    t["source"],
                    t["priority"],
                    t.get("impressions"),
                    t.get("avg_position"),
                ),
            )
            if cur.rowcount:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    cur.close()
    return inserted


# ── GSC ───────────────────────────────────────────────────────────────────────

def _gsc_token() -> str:
    """Obtain a valid OAuth2 access token for the GSC API using the service account."""
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def get_gsc_queries(days: int, min_impressions: int) -> list[dict]:
    """Fetch top queries from GSC with impressions >= min_impressions."""
    try:
        token = _gsc_token()
        end = date.today()
        start = end - timedelta(days=days)
        resp = requests.post(
            f"https://www.googleapis.com/webmasters/v3/sites/{GSC_SITE.replace('/', '%2F')}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": ["query"],
                "rowLimit": 500,
                "startRow": 0,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"  GSC error {resp.status_code}: {resp.text[:200]}")
            return []
        rows = resp.json().get("rows", [])
        results = []
        for row in rows:
            query = row["keys"][0]
            impressions = row.get("impressions", 0)
            position = row.get("position", 0)
            ctr = row.get("ctr", 0) * 100
            if impressions >= min_impressions and position >= 8:
                results.append({
                    "query": query,
                    "impressions": int(impressions),
                    "avg_position": round(position, 1),
                    "ctr": round(ctr, 2),
                })
        return results
    except Exception as e:
        print(f"  GSC exception: {e}")
        return []


def get_existing_post_urls(conn) -> set:
    """Get slugs of all published posts."""
    cur = conn.cursor()
    cur.execute(
        "SELECT post_name FROM wp_posts WHERE post_status IN ('publish','future') AND post_type='post'"
    )
    slugs = {row[0] for row in cur.fetchall()}
    cur.close()
    return slugs


# ── Embeddings ─────────────────────────────────────────────────────────────────

def load_embeddings_cache() -> dict:
    """Load the local post embeddings cache. Returns empty dict if not found."""
    if EMBEDDINGS_CACHE_FILE.exists():
        with open(EMBEDDINGS_CACHE_FILE) as f:
            return json.load(f)
    return {}


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
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def has_similar_post(query: str, cache: dict, threshold: float) -> bool:
    """Returns True if any existing post is semantically similar to query."""
    emb = get_embedding(query)
    if not emb:
        return False
    for data in cache.values():
        post_emb = data.get("embedding")
        if not post_emb:
            continue
        if cosine_similarity(emb, post_emb) >= threshold:
            return True
    return False


# ── Priority scoring ──────────────────────────────────────────────────────────

def compute_priority(impressions: int, avg_position: float, ctr: float) -> float:
    """
    Priority 0-1. Higher = more urgent to cover.
    Factors: high impressions + bad position + low CTR = big opportunity.
    """
    imp_score = min(1.0, impressions / 500)
    pos_score = min(1.0, max(0, (avg_position - 8) / 42))  # 8 → 0, 50 → 1
    ctr_penalty = max(0, 1 - ctr / 5)  # CTR 5%+ → penalizar (ya tenemos tráfico)
    return round(imp_score * 0.4 + pos_score * 0.4 + ctr_penalty * 0.2, 3)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    """Entry point: discover GSC gap queries and insert top candidates into ir_topic_queue."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--min-impressions", type=int, default=MIN_IMPRESSIONS)
    args = parser.parse_args()

    prefix = "[DRY-RUN] " if args.dry_run else ""
    log.info(f"{prefix}GSC Topic Discovery — {date.today().isoformat()}")

    conn = db_connect()
    existing_keywords = get_existing_keywords(conn)

    # ── Step 1: GSC gap queries ───────────────────────────────────────────────
    log.info(f"Fetching GSC queries (last {args.days} days, ≥{args.min_impressions} impressions)...")
    queries = get_gsc_queries(args.days, args.min_impressions)
    log.info(f"  {len(queries)} queries found with position ≥ 8")

    # ── Step 2: Filter already-covered queries via embeddings ─────────────────
    use_embeddings = True
    cache = load_embeddings_cache()
    if not cache:
        log.info("  No embeddings cache found — skipping semantic dedup (run daily-refresh first)")
        use_embeddings = False

    candidates = []
    skipped_existing = 0
    skipped_semantic = 0

    for q in queries:
        keyword = q["query"].strip().lower()

        # Already in queue
        if keyword in existing_keywords:
            skipped_existing += 1
            continue

        # Skip branded queries
        if "inforeparto" in keyword:
            skipped_existing += 1
            continue

        # Skip very short (likely brand or noise)
        if len(keyword.split()) < 2:
            skipped_existing += 1
            continue

        # Semantic dedup: do we already have a post covering this?
        if use_embeddings and has_similar_post(keyword, cache, SIMILARITY_THRESHOLD):
            skipped_semantic += 1
            continue

        priority = compute_priority(q["impressions"], q["avg_position"], q["ctr"])

        candidates.append({
            "keyword": keyword,
            "source": "gsc_gap",
            "priority": priority,
            "impressions": q["impressions"],
            "avg_position": q["avg_position"],
        })

    log.info(f"  Skipped (existing/branded/short): {skipped_existing}")
    log.info(f"  Skipped (semantic overlap): {skipped_semantic}")
    log.info(f"  New candidates: {len(candidates)}")

    # Sort by priority desc, take top N
    candidates.sort(key=lambda x: x["priority"], reverse=True)
    to_insert = candidates[:MAX_NEW_TOPICS]

    if to_insert:
        log.info(f"Top {len(to_insert)} topics to add:")
        for t in to_insert:
            flag = "[DRY] " if args.dry_run else ""
            log.info(f"  {flag}[p={t['priority']:.2f} pos={t['avg_position']} imp={t['impressions']}] {t['keyword']}")

    inserted = insert_topics(conn, to_insert, args.dry_run)
    conn.close()

    # ── Telegram summary ──────────────────────────────────────────────────────
    if not args.dry_run:
        lines = [f"🔍 <b>GSC Topic Discovery — {date.today().isoformat()}</b>"]
        lines.append(f"Queries analizadas: {len(queries)}")
        lines.append(f"Nuevos temas añadidos: {inserted}")
        if to_insert:
            lines.append("\nTop 5 prioridad:")
            for t in to_insert[:5]:
                lines.append(f"  • [{t['avg_position']:.0f}pos / {t['impressions']}imp] {t['keyword']}")
        telegram_send("\n".join(lines))
    else:
        log.info(f"[DRY-RUN] Hubiera insertado {len(to_insert)} topics.")

    log.info(f"Done. Insertados: {inserted}/{len(to_insert)}")


if __name__ == "__main__":
    main()
