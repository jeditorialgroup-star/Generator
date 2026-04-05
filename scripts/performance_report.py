#!/usr/bin/env python3
"""
performance_report.py — Informe semanal de rendimiento del pipeline.

Cron: Domingos 20:00
  cd /home/devops/projects/inforeparto/scripts && python3 performance_report.py

Uso:
  python3 performance_report.py
  python3 performance_report.py --site inforeparto
  python3 performance_report.py --days 14   # ventana de análisis (default 30)
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

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
        logging.FileHandler(LOGS_DIR / f"performance-report-{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))

# Defaults — overridden by site_config
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


def telegram_send(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram error: {e}")


def get_post_title(conn, post_id: int) -> str:
    cur = conn.cursor()
    cur.execute("SELECT post_title FROM wp_posts WHERE ID = %s", (post_id,))
    row = cur.fetchone()
    cur.close()
    return row[0][:55] if row else f"Post {post_id}"


def get_post_slug(conn, post_id: int) -> str:
    cur = conn.cursor()
    cur.execute("SELECT post_name FROM wp_posts WHERE ID = %s", (post_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else ""


def build_report(conn) -> list[str]:
    """Build the weekly performance report. Returns a list of Telegram message strings."""
    messages = []
    today = date.today().isoformat()

    # ── Header ──────────────────────────────────────────────────────────────────
    header = f"📊 <b>Performance Report — {today}</b>\nSite: {SITE}\n"

    # ── 1. Top 10 posts por affiliate clicks ───────────────────────────────────
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT post_id, affiliate_clicks_30d, clicks_30d, impressions_30d, avg_position_30d
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s AND affiliate_clicks_30d > 0
            ORDER BY affiliate_clicks_30d DESC
            LIMIT 10""",
        (SITE,),
    )
    top_affiliate = cur.fetchall()
    cur.close()

    block_aff = ["<b>💰 Top 10 por clicks de afiliado (30d)</b>"]
    if top_affiliate:
        for i, row in enumerate(top_affiliate, 1):
            title = get_post_title(conn, row["post_id"])
            slug = get_post_slug(conn, row["post_id"])
            url = f"{WP_URL}/{slug}/" if slug else ""
            link = f'<a href="{url}">{title}</a>' if url else title
            block_aff.append(f"{i}. {link} — {row['affiliate_clicks_30d']} clicks")
    else:
        block_aff.append("Sin datos de clicks de afiliado aún.")

    # ── 2. Top 10 posts por CTR ─────────────────────────────────────────────────
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT post_id, ctr_30d, clicks_30d, impressions_30d, avg_position_30d
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s AND impressions_30d >= 50
            ORDER BY ctr_30d DESC
            LIMIT 10""",
        (SITE,),
    )
    top_ctr = cur.fetchall()
    cur.close()

    block_ctr = ["<b>🎯 Top 10 por CTR (30d, ≥50 impresiones)</b>"]
    if top_ctr:
        for i, row in enumerate(top_ctr, 1):
            title = get_post_title(conn, row["post_id"])
            slug = get_post_slug(conn, row["post_id"])
            url = f"{WP_URL}/{slug}/" if slug else ""
            link = f'<a href="{url}">{title}</a>' if url else title
            block_ctr.append(
                f"{i}. {link} — {row['ctr_30d']:.1f}% CTR "
                f"({row['clicks_30d']}c / {row['impressions_30d']}imp)"
            )
    else:
        block_ctr.append("Sin datos de CTR aún.")

    # ── 3. Oportunidades: >500 imp, <2% CTR ────────────────────────────────────
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT post_id, impressions_30d, clicks_30d, ctr_30d, avg_position_30d
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s AND impressions_30d >= 500 AND ctr_30d < 2.0
            ORDER BY impressions_30d DESC
            LIMIT 10""",
        (SITE,),
    )
    opportunities = cur.fetchall()
    cur.close()

    block_opp = ["<b>🔧 Oportunidades: >500 imp, CTR &lt;2% (mejorar título/meta)</b>"]
    if opportunities:
        for row in opportunities:
            title = get_post_title(conn, row["post_id"])
            slug = get_post_slug(conn, row["post_id"])
            url = f"{WP_URL}/{slug}/" if slug else ""
            link = f'<a href="{url}">{title}</a>' if url else title
            block_opp.append(
                f"• {link}\n"
                f"  {row['impressions_30d']} imp / {row['ctr_30d']:.1f}% CTR / pos {row['avg_position_30d']:.0f}"
            )
    else:
        block_opp.append("Sin oportunidades identificadas (buen trabajo 👌)")

    # ── 4. FAQ schema vs Article: diferencia de CTR ─────────────────────────────
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT schema_type,
               COUNT(*) as posts,
               AVG(ctr_30d) as avg_ctr,
               AVG(avg_position_30d) as avg_pos,
               SUM(impressions_30d) as total_imp
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s AND schema_type IS NOT NULL AND impressions_30d >= 30
            GROUP BY schema_type
            ORDER BY avg_ctr DESC""",
        (SITE,),
    )
    schema_stats = cur.fetchall()
    cur.close()

    block_schema = ["<b>📋 CTR por tipo de schema (posts con ≥30 imp)</b>"]
    if schema_stats:
        for row in schema_stats:
            block_schema.append(
                f"• <b>{row['schema_type']}</b>: {row['avg_ctr']:.1f}% CTR avg "
                f"({row['posts']} posts, pos {row['avg_pos']:.0f})"
            )
    else:
        block_schema.append("Sin datos de schema aún.")

    # ── 5. Natural score evolution ──────────────────────────────────────────────
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT post_id, natural_score_before, natural_score_after
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s AND natural_score_before IS NOT NULL AND natural_score_after IS NOT NULL
            ORDER BY (natural_score_after - natural_score_before) DESC
            LIMIT 5""",
        (SITE,),
    )
    score_evol = cur.fetchall()
    cur.close()

    block_scores = ["<b>📈 Top 5 mejoras de naturalización (score)</b>"]
    if score_evol:
        for row in score_evol:
            title = get_post_title(conn, row["post_id"])
            delta = row["natural_score_after"] - row["natural_score_before"]
            sign = "+" if delta >= 0 else ""
            block_scores.append(
                f"• {title[:45]}: {row['natural_score_before']:.0f} → {row['natural_score_after']:.0f} ({sign}{delta:.0f})"
            )
    else:
        block_scores.append("Sin datos de evolución aún (se acumularán con los refreshes).")

    # ── Assemble messages (split to avoid 4096 char Telegram limit) ─────────────
    messages.append(header + "\n".join(block_aff))
    messages.append("\n".join(block_ctr))
    messages.append("\n".join(block_opp))
    messages.append("\n".join(block_schema) + "\n\n" + "\n".join(block_scores))

    return messages


def main():
    parser = argparse.ArgumentParser(description="Weekly performance report")
    parser.add_argument("--site", type=str, default="inforeparto")
    parser.add_argument("--days", type=int, default=30, help="Ventana de análisis en días (informativo)")
    args = parser.parse_args()

    global SITE, WP_URL, DB, POST_PERFORMANCE_TABLE, TELEGRAM_CHAT_ID
    try:
        cfg = load_site_config(args.site)
        SITE = cfg["site_id"]
        WP_URL = cfg["wp_url"]
        DB = cfg["db"]
        POST_PERFORMANCE_TABLE = cfg.get("post_performance_table", POST_PERFORMANCE_TABLE)
        TELEGRAM_CHAT_ID = cfg.get("telegram_chat_id", TELEGRAM_CHAT_ID)
        log.info(f"Site: {SITE} ({cfg.get('domain', '')})")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    log.info(f"Generando informe de rendimiento — {date.today().isoformat()}")

    conn = db_connect()
    try:
        messages = build_report(conn)
    finally:
        conn.close()

    for msg in messages:
        telegram_send(msg)
        log.info(f"Mensaje enviado ({len(msg)} chars)")

    log.info("Informe enviado.")


if __name__ == "__main__":
    main()
