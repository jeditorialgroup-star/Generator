#!/usr/bin/env python3
"""
affiliate_report.py — Reporte semanal de clics en afiliados via Telegram.

Cron: domingos 08:30
  cd /home/devops/projects/inforeparto/scripts && python3 affiliate_report.py

Uso manual:
  python3 affiliate_report.py
  python3 affiliate_report.py --days 30   # último mes
"""

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import mysql.connector
import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env.projects", override=False)

# ── Config ─────────────────────────────────────────────────────────────────────

DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))
WP_URL = "https://inforeparto.com"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / f"affiliate-report-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


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


def get_top_asins(conn, days: int, limit: int = 5) -> list[dict]:
    """Return top clicked ASINs in the last N days."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT asin, COUNT(*) AS clicks
        FROM ir_affiliate_clicks
        WHERE clicked_at >= NOW() - INTERVAL %s DAY
        GROUP BY asin
        ORDER BY clicks DESC
        LIMIT %s
        """,
        (days, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def get_top_posts(conn, days: int, limit: int = 5) -> list[dict]:
    """Return top posts by affiliate clicks in the last N days."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT c.post_id, COUNT(*) AS clicks, p.post_title
        FROM ir_affiliate_clicks c
        LEFT JOIN wp_posts p ON p.ID = c.post_id
        WHERE c.clicked_at >= NOW() - INTERVAL %s DAY
          AND c.post_id IS NOT NULL
        GROUP BY c.post_id, p.post_title
        ORDER BY clicks DESC
        LIMIT %s
        """,
        (days, limit),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def get_total_clicks(conn, days: int) -> int:
    """Return total affiliate clicks in the last N days."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM ir_affiliate_clicks WHERE clicked_at >= NOW() - INTERVAL %s DAY",
        (days,),
    )
    total = cur.fetchone()[0]
    cur.close()
    return total


def get_position_breakdown(conn, days: int) -> dict:
    """Return clicks grouped by position (top/middle/bottom)."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT position, COUNT(*) AS clicks
        FROM ir_affiliate_clicks
        WHERE clicked_at >= NOW() - INTERVAL %s DAY
        GROUP BY position
        ORDER BY clicks DESC
        """,
        (days,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r["position"]: r["clicks"] for r in rows}


def main():
    """Generate and send weekly affiliate click report via Telegram."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Días a analizar (default: 7)")
    args = parser.parse_args()

    log.info(f"Affiliate Report — últimos {args.days} días")

    conn = mysql.connector.connect(**DB)

    total = get_total_clicks(conn, args.days)
    top_asins = get_top_asins(conn, args.days)
    top_posts = get_top_posts(conn, args.days)
    positions = get_position_breakdown(conn, args.days)

    conn.close()

    log.info(f"Total clics: {total}")

    period_label = f"últimos {args.days} días" if args.days != 7 else "última semana"
    lines = [
        f"📊 <b>Reporte afiliados — {period_label}</b> ({date.today().isoformat()})",
        f"Clics totales: <b>{total}</b>",
    ]

    if positions:
        pos_str = " | ".join(
            f"{p}: {c}" for p, c in sorted(positions.items(), key=lambda x: -x[1])
        )
        lines.append(f"Posición: {pos_str}")

    if top_asins:
        lines.append("\n🏆 <b>Top productos más clicados:</b>")
        for i, row in enumerate(top_asins, 1):
            amazon_url = f"https://www.amazon.es/dp/{row['asin']}/"
            lines.append(f"  {i}. <a href='{amazon_url}'>{row['asin']}</a> — {row['clicks']} clics")
    else:
        lines.append("\nSin clics registrados en este período.")

    if top_posts:
        lines.append("\n📝 <b>Top posts que generan clics:</b>")
        for i, row in enumerate(top_posts, 1):
            title = (row.get("post_title") or f"Post {row['post_id']}")[:45]
            post_url = f"{WP_URL}/?p={row['post_id']}"
            lines.append(f"  {i}. <a href='{post_url}'>{title}</a> — {row['clicks']} clics")

    if total == 0:
        lines.append("\n💡 Si no hay clics, verifica que los enlaces de tracking estén activos en los posts.")

    message = "\n".join(lines)
    log.info("Enviando reporte a Telegram...")
    telegram_send(message)
    log.info("Done.")


if __name__ == "__main__":
    main()
