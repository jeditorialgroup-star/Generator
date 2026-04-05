#!/usr/bin/env python3
"""
seo_health_check.py — Verificación diaria de salud SEO técnica.

Comprueba: sitemap, canonicals incorrectos, 404s, meta descriptions.
Solo envía Telegram si hay problemas.

Cron: diario 11:00
  cd /home/devops/projects/inforeparto/scripts && python3 seo_health_check.py

Uso manual:
  python3 seo_health_check.py
  python3 seo_health_check.py --full   # verifica todos los posts (más lento)
"""

import argparse
import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

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
WP_PATH = "/var/www/inforeparto"
SITEMAP_INDEX = f"{WP_URL}/sitemap_index.xml"
POST_SITEMAP = f"{WP_URL}/post-sitemap.xml"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / f"seo-health-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def telegram_send(text: str):
    """Send an HTML-formatted Telegram message."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── Checks ────────────────────────────────────────────────────────────────────

def check_sitemap(recent_post_urls: list[str]) -> list[str]:
    """Verify sitemap is accessible and contains the most recent posts."""
    issues = []
    try:
        resp = requests.get(SITEMAP_INDEX, timeout=15)
        if resp.status_code != 200:
            issues.append(f"Sitemap index inaccesible: {resp.status_code}")
            return issues

        # Check post sitemap contains recent posts
        resp2 = requests.get(POST_SITEMAP, timeout=15)
        if resp2.status_code != 200:
            issues.append(f"Post sitemap inaccesible: {resp2.status_code}")
            return issues

        sitemap_xml = resp2.text
        missing = []
        for url in recent_post_urls[:5]:
            slug = urlparse(url).path.strip("/").split("/")[-1]
            if slug and slug not in sitemap_xml:
                missing.append(slug)

        if missing:
            issues.append(f"Posts ausentes del sitemap: {', '.join(missing)}")
        else:
            log.info("  Sitemap: OK")

    except Exception as e:
        issues.append(f"Sitemap error: {e}")

    return issues


def get_recent_post_slugs(conn, limit: int = 10) -> list[tuple[int, str]]:
    """Return (post_id, post_name) for the most recent published posts."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ID, post_name FROM wp_posts "
        "WHERE post_status='publish' AND post_type='post' "
        "ORDER BY post_date DESC LIMIT %s",
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def check_404s(post_slugs: list[tuple[int, str]]) -> list[str]:
    """Check for 404s among recent posts."""
    issues = []
    for post_id, slug in post_slugs:
        url = f"{WP_URL}/{slug}/"
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 404:
                issues.append(f"404: {url}")
            elif resp.status_code >= 400:
                issues.append(f"HTTP {resp.status_code}: {url}")
        except Exception as e:
            issues.append(f"Error accediendo {url}: {e}")
    return issues


def check_meta_descriptions(post_slugs: list[tuple[int, str]]) -> list[str]:
    """Check for missing RankMath meta descriptions via DB."""
    issues = []
    if not post_slugs:
        return issues
    ids = [str(p[0]) for p in post_slugs]
    try:
        conn = mysql.connector.connect(**DB)
        cur = conn.cursor()
        cur.execute(
            f"SELECT post_id FROM wp_postmeta "
            f"WHERE post_id IN ({','.join(ids)}) "
            f"AND meta_key = 'rank_math_description' AND meta_value != ''"
        )
        with_meta = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()
        missing = [slug for pid, slug in post_slugs if pid not in with_meta]
        if missing:
            issues.append(f"Sin meta description (RankMath): {', '.join(missing[:5])}")
        else:
            log.info("  Meta descriptions: OK")
    except Exception as e:
        issues.append(f"Error verificando meta descriptions: {e}")
    return issues


def check_canonical_issues(post_slugs: list[tuple[int, str]]) -> list[str]:
    """Spot-check canonical tags on recent posts (sample 3 to avoid rate limiting)."""
    issues = []
    for post_id, slug in post_slugs[:3]:
        url = f"{WP_URL}/{slug}/"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            # Simple check: canonical should point to the same URL (or www variant)
            canonical = ""
            for line in resp.text.split("\n"):
                if 'rel="canonical"' in line.lower():
                    import re
                    m = re.search(r'href=["\']([^"\']+)["\']', line)
                    if m:
                        canonical = m.group(1)
                    break
            if not canonical:
                issues.append(f"Sin canonical: {url}")
            elif urlparse(canonical).path != urlparse(url).path:
                issues.append(f"Canonical apunta a otra URL: {url} → {canonical}")
            else:
                log.info(f"  Canonical OK: {slug}")
        except Exception as e:
            log.warning(f"  Canonical check error {slug}: {e}")
    return issues


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    """Run all SEO health checks and notify via Telegram only if issues found."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Verifica todos los posts publicados")
    args = parser.parse_args()

    log.info(f"SEO Health Check — {date.today().isoformat()}")

    conn = mysql.connector.connect(**DB)
    limit = 50 if args.full else 10
    recent = get_recent_post_slugs(conn, limit)
    conn.close()

    post_urls = [f"{WP_URL}/{slug}/" for _, slug in recent]
    log.info(f"Verificando {len(recent)} posts...")

    all_issues = []

    log.info("Comprobando sitemap...")
    all_issues.extend(check_sitemap(post_urls))

    log.info("Comprobando 404s...")
    all_issues.extend(check_404s(recent))

    log.info("Comprobando meta descriptions...")
    all_issues.extend(check_meta_descriptions(recent))

    log.info("Comprobando canonicals...")
    all_issues.extend(check_canonical_issues(recent))

    if all_issues:
        log.warning(f"Problemas encontrados: {len(all_issues)}")
        lines = [
            f"⚠️ <b>SEO Health Check — {date.today().isoformat()}</b>",
            f"Posts verificados: {len(recent)}",
            f"Problemas encontrados: {len(all_issues)}",
            "",
        ]
        for issue in all_issues:
            lines.append(f"  • {issue}")
        telegram_send("\n".join(lines))
    else:
        log.info("Todo OK — sin problemas detectados")


if __name__ == "__main__":
    main()
