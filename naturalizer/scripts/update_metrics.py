#!/usr/bin/env python3
"""
update_metrics.py — Capa 9: Feedback Loop post-publicación
Corre como cron a las 07:00 (distinto al daily-refresh de 06:06).

Para cada post naturalizado hace 30+ días sin métricas:
  1. Consulta GSC → avg_position, CTR
  2. Consulta GA4 → pageviews_30d, avg_time_on_page
  3. Actualiza ir_naturalization_log
  4. Ajusta success_score en ir_experience_bank para las experiencias usadas
  5. Envía resumen Telegram si hay anomalías

Uso:
  python3 update_metrics.py
  python3 update_metrics.py --dry-run
  python3 update_metrics.py --days 30    # default
"""

import argparse
import json
import os
import requests
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mysql.connector
import google.auth.transport.requests
import google.oauth2.service_account

from naturalizer import _get_db_config

# ── Config ────────────────────────────────────────────────────────────────────

CREDENTIALS_PATH = "/home/devops/.credentials/gsc-serviceaccount.json"
GSC_SITE = "https://inforeparto.com/"
WP_URL = "https://inforeparto.com"

TELEGRAM_BOT_TOKEN = "8558131550:AAF4lUqNljBn3AXclat_q7VxaBT0u8DFuhI"
TELEGRAM_CHAT_ID = "1312711201"

SCORE_DELTA_GOOD = +0.1     # experiencia funcionó bien (CTR > 3% o pos < 20)
SCORE_DELTA_BAD = -0.05     # experiencia no ayudó (pos > 40 o CTR < 1%)
ALERT_AVG_POSITION = 35     # alerta si posición media > 35

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


# ── GSC ───────────────────────────────────────────────────────────────────────

def _gsc_credentials():
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds


def get_gsc_metrics(url: str, days: int = 30) -> dict:
    """Returns {'avg_position': float, 'ctr': float, 'clicks': int, 'impressions': int}"""
    try:
        creds = _gsc_credentials()
        end = date.today()
        start = end - timedelta(days=days)
        resp = requests.post(
            f"https://www.googleapis.com/webmasters/v3/sites/{GSC_SITE.replace('/', '%2F')}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
            json={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": ["page"],
                "dimensionFilterGroups": [{
                    "filters": [{"dimension": "page", "operator": "equals", "expression": url}]
                }],
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        rows = data.get("rows", [])
        if not rows:
            return {}
        row = rows[0]
        return {
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "avg_position": round(row.get("position", 0), 1),
        }
    except Exception:
        return {}


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_posts_to_update(conn, site: str, days: int) -> list[dict]:
    """Posts naturalized 30+ days ago without metrics."""
    cutoff = datetime.now() - timedelta(days=days)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """SELECT id, wp_post_id, topic, experiences_used, sources_added, score_after
           FROM ir_naturalization_log
           WHERE site = %s
             AND created_at <= %s
             AND metrics_updated_at IS NULL
             AND wp_post_id IS NOT NULL
           ORDER BY created_at ASC
           LIMIT 20""",
        (site, cutoff),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def get_post_slug(conn, post_id: int) -> str:
    cur = conn.cursor()
    cur.execute("SELECT post_name FROM wp_posts WHERE ID = %s", (post_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else ""


def update_log_metrics(conn, log_id: int, metrics: dict):
    cur = conn.cursor()
    cur.execute(
        """UPDATE ir_naturalization_log SET
               pageviews_30d = %s,
               avg_position = %s,
               ctr = %s,
               metrics_updated_at = NOW()
           WHERE id = %s""",
        (
            metrics.get("clicks", 0),
            metrics.get("avg_position"),
            metrics.get("ctr"),
            log_id,
        ),
    )
    conn.commit()
    cur.close()


def update_experience_scores(conn, experiences_used: list, avg_position: float, ctr: float):
    """Adjust success_score for experiences based on post performance."""
    if not experiences_used:
        return
    if avg_position and avg_position < 20 and ctr and ctr > 3:
        delta = SCORE_DELTA_GOOD
    elif avg_position and avg_position > ALERT_AVG_POSITION:
        delta = SCORE_DELTA_BAD
    else:
        return  # Neutral: don't adjust

    cur = conn.cursor()
    for exp_snippet in experiences_used:
        # Match by content snippet (first 60 chars stored)
        cur.execute(
            """UPDATE ir_experience_bank
               SET success_score = GREATEST(0, LEAST(1, success_score + %s))
               WHERE LEFT(content, 60) = %s""",
            (delta, exp_snippet[:60]),
        )
    conn.commit()
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="inforeparto")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_config = _get_db_config(args.site)
    conn = mysql.connector.connect(**db_config)

    posts = get_posts_to_update(conn, args.site, args.days)
    if not posts:
        print(f"No hay posts para actualizar (>{args.days} días sin métricas).")
        conn.close()
        return

    print(f"Posts a actualizar: {len(posts)}")

    updated = 0
    alerts = []

    for post in posts:
        post_id = post["wp_post_id"]
        slug = get_post_slug(conn, post_id)
        if not slug:
            continue

        url = f"{WP_URL}/{slug}/"
        metrics = get_gsc_metrics(url, days=args.days)

        if not metrics:
            print(f"  [{post_id}] {post['topic'][:40]} → sin datos GSC")
            continue

        pos = metrics.get("avg_position", 0)
        ctr = metrics.get("ctr", 0)
        clicks = metrics.get("clicks", 0)
        print(f"  [{post_id}] {post['topic'][:40]} → pos:{pos} ctr:{ctr}% clicks:{clicks}")

        if not args.dry_run:
            update_log_metrics(conn, post["id"], metrics)
            experiences = json.loads(post["experiences_used"]) if post["experiences_used"] else []
            update_experience_scores(conn, experiences, pos, ctr)
            updated += 1

        if pos > ALERT_AVG_POSITION:
            alerts.append(f"⚠️ [{post_id}] {post['topic'][:40]}: pos {pos} (>{ALERT_AVG_POSITION})")

    conn.close()

    # Telegram summary
    if not args.dry_run and (updated > 0 or alerts):
        lines = [f"📊 <b>Capa 9 — Métricas actualizadas</b> ({date.today().isoformat()})"]
        lines.append(f"Posts procesados: {updated}/{len(posts)}")
        if alerts:
            lines.append("\n" + "\n".join(alerts))
        else:
            lines.append("✅ Todos los posts con posición correcta.")
        telegram_send("\n".join(lines))

    print(f"\nActualizado: {updated}/{len(posts)}{'  [DRY-RUN]' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
