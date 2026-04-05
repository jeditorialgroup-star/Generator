#!/usr/bin/env python3
"""
GSC Indexing API — inforeparto.com
Sends URL_UPDATED notifications for recent or specified posts.

Usage:
  python3 index_urls.py                  # Index last 10 published posts
  python3 index_urls.py --post-id 590    # Index specific post
  python3 index_urls.py --all-recent 20  # Index last N posts
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import google.auth.transport.requests
import google.oauth2.service_account
import requests
from dotenv import load_dotenv

# Cargar .env.projects antes de leer cualquier variable de entorno
load_dotenv(Path.home() / ".env.projects", override=False)

import os

CREDENTIALS_PATH = os.environ.get("GSC_CREDENTIALS", "/home/devops/.credentials/gsc-serviceaccount.json")
SCOPES = ["https://www.googleapis.com/auth/indexing"]
INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"
WP_PATH = "/var/www/inforeparto"
WP_URL = "https://inforeparto.com"

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_DIR = Path(os.environ.get("LOG_DIR", "/var/log/projects"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"gsc-indexing-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def get_access_token() -> str:
    """Obtain a valid OAuth2 access token for the Google Indexing API."""
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def get_post_urls(post_ids: list | None = None, limit: int = 10) -> list[str]:
    """Retrieve permalink URLs for published WP posts."""
    if post_ids:
        id_list = ",".join(str(i) for i in post_ids)
        query = (
            f"SELECT ID, post_name FROM wp_posts "
            f"WHERE ID IN ({id_list}) AND post_status IN ('publish','future') AND post_type='post'"
        )
    else:
        query = (
            f"SELECT ID, post_name FROM wp_posts "
            f"WHERE post_status='publish' AND post_type='post' "
            f"ORDER BY post_date DESC LIMIT {limit}"
        )

    result = subprocess.run(
        ["wp", "db", "query", query, f"--path={WP_PATH}", "--allow-root"],
        capture_output=True, text=True
    )
    urls = []
    for line in result.stdout.strip().split("\n")[1:]:  # skip header
        parts = line.strip().split("\t")
        if len(parts) == 2:
            _, slug = parts
            urls.append(f"{WP_URL}/{slug}/")
    return urls


def notify_url(token: str, url: str) -> tuple[int, dict]:
    """Send a URL_UPDATED notification to the Google Indexing API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"url": url, "type": "URL_UPDATED"}
    resp = requests.post(INDEXING_API, headers=headers, json=payload, timeout=15)
    return resp.status_code, resp.json()


def main():
    """Main entry point: parse args and send indexing notifications."""
    parser = argparse.ArgumentParser(description="Notify Google Indexing API for WP posts")
    parser.add_argument("--post-id", type=int, help="Index a single post by WP ID")
    parser.add_argument("--all-recent", type=int, default=10, help="Number of recent posts to index")
    args = parser.parse_args()

    post_ids = [args.post_id] if args.post_id else None
    limit = args.all_recent

    log.info("GSC Indexing — obteniendo token...")
    try:
        token = get_access_token()
    except Exception as e:
        log.error(f"Error de autenticación: {e}")
        sys.exit(1)

    log.info("Obteniendo URLs de WordPress...")
    urls = get_post_urls(post_ids=post_ids, limit=limit)

    if not urls:
        log.warning("No se encontraron URLs.")
        sys.exit(0)

    log.info(f"Enviando {len(urls)} URL(s) a Google Indexing API...")
    ok = 0
    for url in urls:
        status, body = notify_url(token, url)
        if status == 200:
            log.info(f"  OK: {url}")
            ok += 1
        else:
            err = body.get("error", {}).get("message", str(body))
            log.warning(f"  ERROR {status}: {url} — {err}")
        time.sleep(0.3)  # avoid rate limiting

    log.info(f"Completado: {ok}/{len(urls)} URLs enviadas correctamente.")


if __name__ == "__main__":
    main()
