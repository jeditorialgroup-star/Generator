#!/usr/bin/env python3
"""
migrate_db.py — Crea las tablas de Naturalizer v4 en MariaDB.
Idempotente: seguro de ejecutar múltiples veces.

Uso:
  python3 migrate_db.py
  python3 migrate_db.py --site psicoprotego
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mysql.connector
from naturalizer import _get_db_config

TABLES = {
    "experience_bank": """
        CREATE TABLE IF NOT EXISTS ir_experience_bank (
            id INT AUTO_INCREMENT PRIMARY KEY,
            site VARCHAR(50) NOT NULL,
            topic VARCHAR(200),
            type ENUM(
                'metric','anecdote','regulatory','comparison',
                'user_feedback','process_insight','seasonal'
            ) NOT NULL,
            content TEXT NOT NULL,
            tags JSON,
            success_score FLOAT DEFAULT 0.5,
            times_used INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP NULL,
            INDEX idx_site (site),
            INDEX idx_success (success_score DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "naturalization_log": """
        CREATE TABLE IF NOT EXISTS ir_naturalization_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            site VARCHAR(50),
            topic VARCHAR(200),
            wp_post_id INT,
            score_before FLOAT,
            score_after FLOAT,
            experiences_used JSON,
            sources_added JSON,
            pageviews_30d INT DEFAULT NULL,
            avg_time_on_page FLOAT DEFAULT NULL,
            avg_position FLOAT DEFAULT NULL,
            ctr FLOAT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metrics_updated_at TIMESTAMP NULL,
            INDEX idx_site_post (site, wp_post_id),
            INDEX idx_created (created_at DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "source_cache": """
        CREATE TABLE IF NOT EXISTS ir_source_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            query_hash VARCHAR(64) NOT NULL UNIQUE,
            query TEXT NOT NULL,
            site VARCHAR(50),
            results JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            INDEX idx_hash (query_hash),
            INDEX idx_expires (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def migrate(site: str = "inforeparto"):
    db_config = _get_db_config(site)
    conn = mysql.connector.connect(**db_config)
    cur = conn.cursor()

    for name, ddl in TABLES.items():
        cur.execute(ddl)
        print(f"  ✅ Tabla {name}: OK")

    conn.commit()
    cur.close()
    conn.close()
    print(f"Migración completada para site '{site}'.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="inforeparto")
    args = parser.parse_args()
    migrate(args.site)


if __name__ == "__main__":
    main()
