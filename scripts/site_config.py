"""
site_config.py — Cargador de configuración multi-site.

Carga naturalizer/contextos/{site}/site_config.yaml y
expone un dict tipado con todos los parámetros del sitio.
"""

import os
from pathlib import Path

import yaml

NATURALIZER_DIR = Path(__file__).parent.parent / "naturalizer"
CONTEXTS_DIR = NATURALIZER_DIR / "contextos"


def load_site_config(site: str) -> dict:
    """Load and return the site_config.yaml for the given site ID.

    Raises FileNotFoundError if the site directory or config file doesn't exist.
    """
    config_path = CONTEXTS_DIR / site / "site_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"site_config.yaml no encontrado para '{site}': {config_path}\n"
            f"Sitios disponibles: {[d.name for d in CONTEXTS_DIR.iterdir() if d.is_dir() and not d.name.startswith('_')]}"
        )
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve DB credentials from environment using the db_env_prefix
    prefix = config.get("db_env_prefix", "WP")
    config["db"] = dict(
        host=os.environ.get(f"{prefix}_DB_HOST", os.environ.get("WP_DB_HOST", "localhost")),
        user=os.environ.get(f"{prefix}_DB_USER", os.environ.get("WP_DB_USER", "wp_user")),
        password=os.environ.get(f"{prefix}_DB_PASSWORD", os.environ.get("WP_DB_PASSWORD", "")),
        database=os.environ.get(f"{prefix}_DB_NAME", os.environ.get("WP_DB_NAME", "wordpress_db")),
    )

    # Resolve Telegram chat ID from env
    chat_id_env = config.get("telegram_chat_id_env", "TELEGRAM_CHAT_ID")
    config["telegram_chat_id"] = os.environ.get(chat_id_env, os.environ.get("TELEGRAM_CHAT_ID", ""))

    # Resolve affiliate catalog path (relative to project root)
    if config.get("affiliate_catalog"):
        config["affiliate_catalog_path"] = Path(__file__).parent.parent / config["affiliate_catalog"]
    else:
        config["affiliate_catalog_path"] = None

    return config


def list_sites() -> list[str]:
    """Return all configured site IDs."""
    return [
        d.name for d in CONTEXTS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "site_config.yaml").exists()
    ]
