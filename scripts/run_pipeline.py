#!/usr/bin/env python3
"""
run_pipeline.py — Punto de entrada único del pipeline multi-site.

Uso:
  python3 run_pipeline.py --site inforeparto --process all
  python3 run_pipeline.py --site inforeparto --process publish
  python3 run_pipeline.py --site psicoprotego --process discovery --dry-run
  python3 run_pipeline.py --list-sites

Procesos disponibles:
  discovery  → gsc-topic-discovery.py
  publish    → autopublisher.py
  refresh    → daily-refresh.py
  index      → gsc-indexing/index_urls.py
  all        → discovery + publish + refresh + index (en ese orden)
"""

import argparse
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path.home() / ".env.projects", override=False)

from site_config import load_site_config, list_sites

SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent

LOGS_DIR = SCRIPTS_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / f"pipeline-{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

PROCESS_COMMANDS = {
    "discovery": [sys.executable, str(SCRIPTS_DIR / "gsc-topic-discovery.py")],
    "publish":   [sys.executable, str(SCRIPTS_DIR / "autopublisher.py")],
    "refresh":   [sys.executable, str(SCRIPTS_DIR / "daily-refresh.py")],
    "index":     [sys.executable, str(PROJECT_DIR / "gsc-indexing" / "index_urls.py")],
}

PROCESS_ORDER = ["discovery", "publish", "refresh", "index"]


def run_process(process: str, site: str, extra_args: list[str]) -> int:
    """Run a single pipeline process for the given site. Returns exit code."""
    cmd = PROCESS_COMMANDS[process] + ["--site", site] + extra_args
    log.info(f"  Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(SCRIPTS_DIR))
    if result.returncode != 0:
        log.error(f"  {process} falló con código {result.returncode}")
    else:
        log.info(f"  {process} completado OK")
    return result.returncode


def main():
    """Entry point for the pipeline orchestrator."""
    parser = argparse.ArgumentParser(description="Pipeline orchestrator multi-site")
    parser.add_argument("--site", type=str, default="inforeparto", help="Site ID")
    parser.add_argument(
        "--process",
        type=str,
        default="publish",
        choices=list(PROCESS_COMMANDS.keys()) + ["all"],
        help="Proceso a ejecutar (default: publish)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Pasar --dry-run a todos los procesos")
    parser.add_argument("--list-sites", action="store_true", help="Listar sitios configurados y salir")
    args = parser.parse_args()

    if args.list_sites:
        sites = list_sites()
        print("Sitios configurados:")
        for s in sites:
            try:
                cfg = load_site_config(s)
                print(f"  {s} — {cfg.get('domain', '?')} — {cfg.get('description', '')}")
            except Exception:
                print(f"  {s} — (error al cargar config)")
        return

    # Validate site
    try:
        cfg = load_site_config(args.site)
        log.info(f"Pipeline: site={args.site} ({cfg.get('domain', '')}) process={args.process}")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    extra = ["--dry-run"] if args.dry_run else []

    processes = PROCESS_ORDER if args.process == "all" else [args.process]
    failed = []

    for process in processes:
        log.info(f"\n{'='*50}")
        log.info(f"PROCESO: {process.upper()} — {args.site}")
        log.info(f"{'='*50}")
        rc = run_process(process, args.site, extra)
        if rc != 0:
            failed.append(process)
            if args.process != "all":
                sys.exit(rc)
            # For 'all', continue but track failures

    if failed:
        log.error(f"Procesos fallidos: {failed}")
        sys.exit(1)
    else:
        log.info(f"\nPipeline completado: {args.site} / {args.process}")


if __name__ == "__main__":
    main()
