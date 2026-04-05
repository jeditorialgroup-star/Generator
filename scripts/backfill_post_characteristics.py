#!/usr/bin/env python3
"""
backfill_post_characteristics.py — Retroactively compute post characteristics
for all published posts that are missing them in post_performance.

Usage:
  python3 backfill_post_characteristics.py
  python3 backfill_post_characteristics.py --dry-run
  python3 backfill_post_characteristics.py --site inforeparto
  python3 backfill_post_characteristics.py --force  # recompute even if already set
"""

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env.projects", override=False)

sys.path.insert(0, str(Path(__file__).parent))
from site_config import load_site_config
from post_analyzer import analyze_post_characteristics

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / f"backfill-characteristics-{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

SITE = "inforeparto"
WP_URL = "https://inforeparto.com"
DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)
POST_PERFORMANCE_TABLE = "post_performance"


def db_connect():
    return mysql.connector.connect(**DB)


def get_posts_to_backfill(conn, force: bool) -> list[dict]:
    """Get published posts that need characteristic backfill."""
    cur = conn.cursor(dictionary=True)
    if force:
        condition = "p.post_status = 'publish' AND p.post_type = 'post'"
    else:
        condition = (
            "p.post_status = 'publish' AND p.post_type = 'post' "
            "AND (pp.opening_type IS NULL OR pp.paragraph_count = 0)"
        )
    cur.execute(f"""
        SELECT p.ID, p.post_title, p.post_content, p.post_name
        FROM wp_posts p
        LEFT JOIN {POST_PERFORMANCE_TABLE} pp ON pp.post_id = p.ID AND pp.site = %s
        WHERE {condition}
        ORDER BY p.post_date ASC
    """, (SITE,))
    rows = cur.fetchall()
    cur.close()
    return rows


def upsert_characteristics(conn, post_id: int, chars: dict, dry_run: bool):
    """Insert or update post characteristics in post_performance."""
    if dry_run:
        return
    cur = conn.cursor()
    cur.execute(
        f"""INSERT INTO {POST_PERFORMANCE_TABLE}
            (post_id, site, keyword, word_count, paragraph_count, avg_paragraph_length,
             h2_count, h3_count, list_count, opening_type, affiliate_count,
             affiliate_positions, internal_link_count, external_source_count,
             has_disclaimer, experience_count, reading_time_minutes)
            VALUES (%s, %s, '', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              word_count=VALUES(word_count),
              paragraph_count=VALUES(paragraph_count),
              avg_paragraph_length=VALUES(avg_paragraph_length),
              h2_count=VALUES(h2_count),
              h3_count=VALUES(h3_count),
              list_count=VALUES(list_count),
              opening_type=VALUES(opening_type),
              affiliate_count=VALUES(affiliate_count),
              affiliate_positions=VALUES(affiliate_positions),
              internal_link_count=VALUES(internal_link_count),
              external_source_count=VALUES(external_source_count),
              has_disclaimer=VALUES(has_disclaimer),
              experience_count=VALUES(experience_count),
              reading_time_minutes=VALUES(reading_time_minutes)""",
        (
            post_id, SITE,
            chars["word_count"], chars["paragraph_count"], chars["avg_paragraph_length"],
            chars["h2_count"], chars["h3_count"], chars["list_count"],
            chars["opening_type"],
            chars["affiliate_count"],
            json.dumps(chars["affiliate_positions"]) if chars["affiliate_positions"] else None,
            chars["internal_link_count"], chars["external_source_count"],
            int(chars["has_disclaimer"]), chars["experience_count"],
            chars["reading_time_minutes"],
        )
    )
    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill post characteristics into post_performance")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Recompute even for posts already analyzed")
    parser.add_argument("--site", type=str, default="inforeparto")
    args = parser.parse_args()

    global SITE, WP_URL, DB, POST_PERFORMANCE_TABLE
    try:
        cfg = load_site_config(args.site)
        SITE = cfg["site_id"]
        WP_URL = cfg["wp_url"]
        DB = cfg["db"]
        POST_PERFORMANCE_TABLE = cfg.get("post_performance_table", POST_PERFORMANCE_TABLE)
        log.info(f"Site: {SITE} ({cfg.get('domain', '')})")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    prefix = "[DRY-RUN] " if args.dry_run else ""
    log.info(f"{prefix}Backfill post characteristics — {date.today().isoformat()}")

    conn = db_connect()
    posts = get_posts_to_backfill(conn, force=args.force)
    log.info(f"Posts a procesar: {len(posts)}")

    processed = 0
    errors = 0

    for post in posts:
        post_id = post["ID"]
        title = post["post_title"][:55]
        html = post.get("post_content", "")

        if not html:
            log.warning(f"  Post {post_id} sin contenido — skip")
            continue

        try:
            chars = analyze_post_characteristics(html, wp_url=WP_URL)
            upsert_characteristics(conn, post_id, chars, args.dry_run)
            flag = "[DRY] " if args.dry_run else ""
            log.info(
                f"  {flag}Post {post_id}: {title} — "
                f"{chars['word_count']}w, {chars['opening_type']}, {chars['h2_count']}H2, "
                f"aff:{chars['affiliate_count']}, exp:{chars['experience_count']}"
            )
            processed += 1
        except Exception as e:
            log.error(f"  Error en post {post_id}: {e}")
            errors += 1

    conn.close()
    log.info(f"Completado: {processed} posts procesados, {errors} errores.")


if __name__ == "__main__":
    main()
