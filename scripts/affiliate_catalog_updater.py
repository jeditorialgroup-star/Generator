#!/usr/bin/env python3
"""
affiliate_catalog_updater.py — Amplía el catálogo de afiliados via Serper + Jina.

Busca productos de Amazon relevantes para repartidores, extrae ASINs y genera
affiliate_catalog_new.json para revisión manual antes de reemplazar el catálogo.

Cron: día 1 y 15 de cada mes, 02:00
  cd /home/devops/projects/inforeparto/scripts && python3 affiliate_catalog_updater.py

Uso manual:
  python3 affiliate_catalog_updater.py
  python3 affiliate_catalog_updater.py --dry-run   # muestra lo que encontraría sin guardar
  python3 affiliate_catalog_updater.py --category "mochilas térmicas"  # solo una categoría
"""

import argparse
import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env.projects", override=False)

# ── Config ─────────────────────────────────────────────────────────────────────

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
AFFILIATE_TAG = "inforeparto-21"

CATALOG_FILE = Path(__file__).parent / "affiliate_catalog.json"
OUTPUT_FILE = Path(__file__).parent / "affiliate_catalog_new.json"

# ── Logging ───────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / f"affiliate-catalog-updater-{date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ── Categorías y queries de búsqueda ─────────────────────────────────────────

CATEGORIES = [
    {
        "name": "mochilas_termicas",
        "queries": [
            "mejores mochilas térmicas para repartidores Amazon",
            "mochila isotérmica reparto domicilio Amazon",
            "bolsa térmica delivery repartidor Amazon",
        ],
        "keywords_base": ["mochila térmica", "mochila repartidor", "bolsa isotérmica", "mochila delivery"],
    },
    {
        "name": "accesorios_bicicleta",
        "queries": [
            "mejores accesorios bicicleta para repartidores Amazon",
            "luces bicicleta repartidor Amazon",
            "candado bicicleta antirrobo Amazon",
            "soporte móvil bicicleta manillar Amazon",
            "portamóvil bici Amazon",
        ],
        "keywords_base": ["luces bicicleta", "candado bicicleta", "soporte móvil bici", "timbre bicicleta"],
    },
    {
        "name": "accesorios_moto",
        "queries": [
            "mejores accesorios moto repartidores Amazon",
            "soporte móvil moto repartidor Amazon",
            "guantes moto repartidor Amazon",
            "intercomunicador moto casco Amazon",
        ],
        "keywords_base": ["soporte móvil moto", "guantes moto", "intercomunicador moto", "soporte manillar"],
    },
    {
        "name": "ropa_impermeable",
        "queries": [
            "mejores chubasqueros para repartidores Amazon",
            "ropa impermeable ciclismo trabajo Amazon",
            "pantalón impermeable ciclismo Amazon",
            "chaqueta impermeable moto Amazon",
        ],
        "keywords_base": ["chubasquero repartidor", "ropa impermeable", "chaqueta impermeable", "pantalón impermeable"],
    },
    {
        "name": "powerbanks_cargadores",
        "queries": [
            "mejores powerbanks para repartidores Amazon",
            "batería externa carga rápida Amazon",
            "powerbank solar resistente Amazon",
            "cargador inalámbrico moto Amazon",
        ],
        "keywords_base": ["powerbank repartidor", "batería externa", "cargador portátil", "power bank carga rápida"],
    },
    {
        "name": "soportes_movil",
        "queries": [
            "mejores soportes móvil moto bici Amazon",
            "soporte teléfono moto antigravitacional Amazon",
            "portamóvil universal moto Amazon",
        ],
        "keywords_base": ["soporte móvil moto", "portamóvil universal", "soporte teléfono bici"],
    },
    {
        "name": "bidones_botellas",
        "queries": [
            "mejores bidones ciclismo Amazon",
            "botella deportiva repartidor Amazon",
            "bidón bicicleta portabidón Amazon",
        ],
        "keywords_base": ["bidón ciclismo", "botella deportiva", "portabidón bicicleta"],
    },
    {
        "name": "herramientas_reparacion",
        "queries": [
            "kit reparación bicicleta Amazon",
            "herramientas reparación pinchazos ciclismo Amazon",
            "multitool bicicleta Amazon",
            "bomba inflador bicicleta Amazon",
        ],
        "keywords_base": ["kit reparación bici", "parches pinchazos", "multitool bicicleta", "bomba bicicleta"],
    },
]

# ── Serper ────────────────────────────────────────────────────────────────────

def serper_search(query: str) -> list[str]:
    """Search Google via Serper API and return organic result URLs."""
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "gl": "es", "hl": "es", "num": 10},
            timeout=15,
        )
        if resp.status_code != 200:
            log.warning(f"Serper {resp.status_code} para: {query}")
            return []
        results = resp.json().get("organic", [])
        return [r["link"] for r in results if "link" in r]
    except Exception as e:
        log.error(f"Serper error: {e}")
        return []


# ── Jina Reader ───────────────────────────────────────────────────────────────

def jina_fetch(url: str) -> str:
    """Fetch page content via Jina Reader API as plain text."""
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers={
                "Authorization": f"Bearer {JINA_API_KEY}",
                "Accept": "text/plain",
                "X-Remove-Selector": "nav,footer,header,.sidebar",
                "X-Timeout": "20",
            },
            timeout=25,
        )
        if resp.status_code == 200:
            return resp.text
        log.warning(f"Jina {resp.status_code} para: {url}")
        return ""
    except Exception as e:
        log.error(f"Jina error {url}: {e}")
        return ""


# ── ASIN extraction ───────────────────────────────────────────────────────────

ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})(?:[/?]|$)")


def extract_asins_from_text(text: str) -> list[str]:
    """Extract Amazon ASINs from text content."""
    return list(dict.fromkeys(ASIN_RE.findall(text)))  # deduplicated, order preserved


def extract_title_near_asin(text: str, asin: str) -> str:
    """Try to extract a product title near the ASIN mention in text."""
    idx = text.find(asin)
    if idx == -1:
        return ""
    # Take up to 300 chars before and after ASIN
    snippet = text[max(0, idx - 300): idx + 100]
    # Grab first non-trivial line
    for line in snippet.split("\n"):
        line = line.strip()
        if len(line) > 20 and not line.startswith("http") and asin not in line:
            return line[:120]
    return ""


# ── Catalog helpers ───────────────────────────────────────────────────────────

def load_existing_catalog() -> list[dict]:
    """Load the current affiliate catalog."""
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE) as f:
            return json.load(f)
    return []


def existing_asins(catalog: list[dict]) -> set[str]:
    """Return the set of ASINs already in the catalog."""
    return {item["asin"] for item in catalog}


# ── Main ──────────────────────────────────────────────────────────────────────

def process_category(category: dict, known_asins: set[str]) -> list[dict]:
    """Run searches for a category, scrape result pages, and return new catalog entries."""
    new_entries = []
    found_asins: set[str] = set()

    for query in category["queries"]:
        log.info(f"  Buscando: {query}")
        urls = serper_search(query)
        time.sleep(1)

        # Only look at Amazon URLs directly or pages that list Amazon products
        amazon_urls = [u for u in urls if "amazon.es" in u or "amazon.com" in u]
        other_urls = [u for u in urls if u not in amazon_urls][:3]  # max 3 non-Amazon pages

        for url in amazon_urls[:5] + other_urls:
            log.info(f"    Fetching: {url[:80]}")
            content = jina_fetch(url)
            if not content:
                time.sleep(0.5)
                continue

            asins = extract_asins_from_text(content)
            log.info(f"    → {len(asins)} ASINs encontrados")

            for asin in asins:
                if asin in known_asins or asin in found_asins:
                    continue
                found_asins.add(asin)
                title = extract_title_near_asin(content, asin)
                new_entries.append({
                    "keywords": category["keywords_base"],
                    "asin": asin,
                    "name": title or f"[{category['name']}] {asin}",
                    "category": category["name"],
                    "affiliate_url": f"https://www.amazon.es/dp/{asin}/?tag={AFFILIATE_TAG}",
                })

            time.sleep(0.8)

    return new_entries


def main():
    """Discover new affiliate products via Serper+Jina and write affiliate_catalog_new.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No escribe el archivo de salida")
    parser.add_argument("--category", help="Procesar solo esta categoría (por nombre)")
    args = parser.parse_args()

    if not SERPER_API_KEY:
        log.error("SERPER_API_KEY no configurada")
        return
    if not JINA_API_KEY:
        log.error("JINA_API_KEY no configurada")
        return

    log.info(f"Affiliate Catalog Updater — {date.today().isoformat()}")

    existing = load_existing_catalog()
    known = existing_asins(existing)
    log.info(f"Catálogo actual: {len(existing)} productos, {len(known)} ASINs conocidos")

    categories = CATEGORIES
    if args.category:
        categories = [c for c in CATEGORIES if c["name"] == args.category]
        if not categories:
            log.error(f"Categoría '{args.category}' no encontrada. Disponibles: {[c['name'] for c in CATEGORIES]}")
            return

    all_new: list[dict] = []
    for cat in categories:
        log.info(f"\nCategoría: {cat['name']}")
        new = process_category(cat, known | {e["asin"] for e in all_new})
        log.info(f"  → {len(new)} nuevos productos encontrados")
        all_new.extend(new)

    log.info(f"\nTotal nuevos productos: {len(all_new)}")

    if args.dry_run:
        log.info("[DRY-RUN] No se escribe el archivo")
        for e in all_new[:10]:
            log.info(f"  {e['asin']} — {e['name'][:60]}")
        return

    # Write new catalog (existing + new entries)
    combined = existing + all_new
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    log.info(f"Escrito: {OUTPUT_FILE} ({len(combined)} productos total)")
    log.info(f"Revísalo manualmente y renómbralo a affiliate_catalog.json cuando esté listo.")


if __name__ == "__main__":
    main()
