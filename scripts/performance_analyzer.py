#!/usr/bin/env python3
"""
performance_analyzer.py — Descubre qué características del post se correlacionan con
mejor rendimiento SEO (clicks, CTR, posición).

Cron: Domingos 19:00 (antes del performance_report)
  cd /home/devops/projects/inforeparto/scripts && python3 performance_analyzer.py

Genera: scripts/generation_insights.json
Envía: resumen por Telegram con los 5 mejores insights (solo si >20% diferencia)

Requiere mínimo 15 posts con >30 días de datos GSC.
No usa estadística sofisticada: medias simples y diferencias porcentuales.
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
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
        logging.FileHandler(LOGS_DIR / f"performance-analyzer-{date.today().isoformat()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("ADMIN_CHAT_ID", ""))

SITE = "inforeparto"
DB = dict(
    host=os.environ.get("WP_DB_HOST", "localhost"),
    user=os.environ.get("WP_DB_USER", "wp_user"),
    password=os.environ.get("WP_DB_PASSWORD", ""),
    database=os.environ.get("WP_DB_NAME", "wordpress_db"),
)
POST_PERFORMANCE_TABLE = "post_performance"
INSIGHTS_FILE = Path(__file__).parent / "generation_insights.json"

MIN_SAMPLE = 15   # minimum posts to start analyzing
MIN_GSC_DAYS = 30  # posts must have ≥30 days of GSC data


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


def load_posts_with_metrics(conn) -> list[dict]:
    """
    Load posts that have both structural characteristics and GSC performance data
    and were published at least MIN_GSC_DAYS ago.
    """
    cutoff = (date.today() - timedelta(days=MIN_GSC_DAYS)).isoformat()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""SELECT
              post_id, keyword, search_intent, schema_type, word_count,
              paragraph_count, avg_paragraph_length, h2_count, h3_count,
              list_count, opening_type, affiliate_count, internal_link_count,
              external_source_count, has_disclaimer, experience_count,
              reading_time_minutes, is_experimental,
              clicks_30d, impressions_30d, avg_position_30d, ctr_30d,
              published_at
            FROM {POST_PERFORMANCE_TABLE}
            WHERE site = %s
              AND opening_type IS NOT NULL
              AND impressions_30d > 0
              AND published_at IS NOT NULL
              AND published_at <= %s
            ORDER BY published_at ASC""",
        (SITE, cutoff),
    )
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def group_by_characteristic(posts: list[dict], characteristic: str) -> dict[str, list[dict]]:
    """Group posts by a characteristic value."""
    groups = defaultdict(list)
    for post in posts:
        val = post.get(characteristic)
        if val is None:
            continue
        groups[str(val)].append(post)
    return dict(groups)


def group_numeric_by_ranges(posts: list[dict], characteristic: str, ranges: list[tuple]) -> dict[str, list[dict]]:
    """
    Group posts by numeric range buckets.
    ranges: list of (label, min, max) tuples, where max is exclusive for all but the last.
    """
    groups = defaultdict(list)
    for post in posts:
        val = post.get(characteristic)
        if val is None:
            continue
        for label, lo, hi in ranges:
            if lo <= val < hi:
                groups[label].append(post)
                break
        else:
            # last bucket catches overflow
            label, lo, hi = ranges[-1]
            if val >= lo:
                groups[label].append(post)
    return dict(groups)


def group_means(group: list[dict]) -> dict:
    """Calculate mean performance metrics for a group of posts."""
    if not group:
        return {}
    clicks = [p.get("clicks_30d") or 0 for p in group]
    ctr = [p.get("ctr_30d") or 0 for p in group]
    pos = [p.get("avg_position_30d") or 50 for p in group]
    return {
        "n": len(group),
        "avg_clicks": round(sum(clicks) / len(clicks), 1),
        "avg_ctr": round(sum(ctr) / len(ctr), 2),
        "avg_position": round(sum(pos) / len(pos), 1),
    }


def confidence_label(n: int) -> str:
    if n >= 20:
        return "high"
    elif n >= 10:
        return "medium"
    return "low"


def pct_diff(a: float, b: float) -> float:
    """Percentage difference of a relative to b. Positive = a is better."""
    if b == 0:
        return 0.0
    return round((a - b) / b, 3)


def analyze_categorical(posts: list[dict], characteristic: str, metric: str = "avg_clicks") -> list[dict]:
    """
    Analyze a categorical characteristic. Returns insights sorted by performance.
    """
    groups = group_by_characteristic(posts, characteristic)
    if len(groups) < 2:
        return []

    stats = {val: group_means(group) for val, group in groups.items()}
    overall_vals = [s[metric] for s in stats.values() if s]
    overall_avg = sum(overall_vals) / len(overall_vals) if overall_vals else 0

    insights = []
    for val, s in stats.items():
        if not s or s["n"] < 2:
            continue
        diff = pct_diff(s[metric], overall_avg)
        insights.append({
            "value": val,
            "n": s["n"],
            "avg_clicks": s["avg_clicks"],
            "avg_ctr": s["avg_ctr"],
            "avg_position": s["avg_position"],
            "improvement_vs_average": diff,
            "confidence": confidence_label(s["n"]),
        })

    insights.sort(key=lambda x: x["improvement_vs_average"], reverse=True)
    return insights


def analyze_numeric(posts: list[dict], characteristic: str, ranges: list[tuple], metric: str = "avg_clicks") -> list[dict]:
    """Analyze a numeric characteristic using predefined ranges."""
    groups = group_numeric_by_ranges(posts, characteristic, ranges)
    if len(groups) < 2:
        return []

    stats = {label: group_means(group) for label, group in groups.items()}
    overall_vals = [s[metric] for s in stats.values() if s]
    overall_avg = sum(overall_vals) / len(overall_vals) if overall_vals else 0

    insights = []
    for label, s in stats.items():
        if not s or s["n"] < 2:
            continue
        diff = pct_diff(s[metric], overall_avg)
        insights.append({
            "value": label,
            "n": s["n"],
            "avg_clicks": s["avg_clicks"],
            "avg_ctr": s["avg_ctr"],
            "avg_position": s["avg_position"],
            "improvement_vs_average": diff,
            "confidence": confidence_label(s["n"]),
        })

    insights.sort(key=lambda x: x["improvement_vs_average"], reverse=True)
    return insights


def build_insights(posts: list[dict]) -> dict:
    """
    Run all analyses and build the generation_insights.json structure.
    """
    insights = []
    warnings = []

    # ── Categorical characteristics ─────────────────────────────────────────────

    CATEGORICAL = {
        "opening_type": {
            "metric": "avg_clicks",
            "label_fn": lambda v, s: f"Aperturas con '{v}' rinden {abs(s['improvement_vs_average'])*100:.0f}% {'más' if s['improvement_vs_average']>0 else 'menos'} clicks que la media",
            "rec_fn": lambda best: (
                f"Priorizar apertura tipo '{best['value']}' — mayor rendimiento en clicks/CTR"
                if best["improvement_vs_average"] > 0.2 else None
            ),
        },
        "schema_type": {
            "metric": "avg_ctr",
            "label_fn": lambda v, s: f"Schema '{v}' — CTR medio {s['avg_ctr']:.1f}% (n={s['n']})",
            "rec_fn": lambda best: (
                f"Preferir schema '{best['value']}' — mejor CTR ({best['avg_ctr']:.1f}%)"
                if best["improvement_vs_average"] > 0.2 else None
            ),
        },
        "has_disclaimer": {
            "metric": "avg_clicks",
            "label_fn": lambda v, s: f"Disclaimer={'Sí' if v=='1' else 'No'}: {s['avg_clicks']:.0f} clicks/30d medio",
            "rec_fn": lambda best: None,  # disclaimer is compliance, not optimization
        },
        "search_intent": {
            "metric": "avg_clicks",
            "label_fn": lambda v, s: f"Intención '{v}': {s['avg_clicks']:.0f} clicks/30d, CTR {s['avg_ctr']:.1f}%",
            "rec_fn": lambda best: None,  # intent is determined by topic, not choice
        },
    }

    for char, config in CATEGORICAL.items():
        groups = group_by_characteristic(posts, char)
        if len(groups) < 2:
            if len(groups) == 1:
                val, group = list(groups.items())[0]
                if len(group) < 5:
                    warnings.append(f"Solo hay posts con {char}='{val}' — sin varianza para comparar")
            continue

        group_stats = analyze_categorical(posts, char, config["metric"])
        if not group_stats:
            continue

        best = group_stats[0]
        worst = group_stats[-1]

        diff = abs(pct_diff(best["avg_clicks"], worst["avg_clicks"]) if worst["avg_clicks"] else 0)
        if diff > 0.2:
            rec = config["rec_fn"](best)
            insight = {
                "characteristic": char,
                "best_value": best["value"],
                "improvement_vs_average": best["improvement_vs_average"],
                "confidence": best["confidence"],
                "recommendation": rec or config["label_fn"](best["value"], best),
                "detail": {v: {"avg_clicks": s["avg_clicks"], "avg_ctr": s["avg_ctr"], "n": s["n"]} for v, s in {g["value"]: g for g in group_stats}.items()},
            }
            insights.append(insight)

        if best["n"] < 5:
            warnings.append(f"Posts con {char}='{best['value']}' tienen mejor rendimiento pero muestra pequeña (n={best['n']})")

    # ── Numeric characteristics ─────────────────────────────────────────────────

    NUMERIC = {
        "word_count": {
            "ranges": [("<700", 0, 700), ("700-900", 700, 900), ("900-1100", 900, 1100), ("1100-1300", 1100, 1300), (">1300", 1300, 99999)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: f"Apuntar a {best['value']} palabras — mejor rendimiento en clicks",
        },
        "h2_count": {
            "ranges": [("1-3", 1, 4), ("4-6", 4, 7), ("7+", 7, 99)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: f"Usar {best['value']} H2 — mejor estructura para CTR",
        },
        "experience_count": {
            "ranges": [("0", 0, 1), ("1-2", 1, 3), ("3-4", 3, 5), ("5+", 5, 99)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: f"Integrar {best['value']} experiencias reales en el texto",
        },
        "affiliate_count": {
            "ranges": [("0", 0, 1), ("1-2", 1, 3), ("3-5", 3, 6), ("6+", 6, 99)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: None,  # affiliate count is content-dependent
        },
        "list_count": {
            "ranges": [("0", 0, 1), ("1-2", 1, 3), ("3+", 3, 99)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: None,
        },
        "internal_link_count": {
            "ranges": [("0-1", 0, 2), ("2-3", 2, 4), ("4+", 4, 99)],
            "metric": "avg_clicks",
            "rec_fn": lambda best: f"Incluir {best['value']} enlaces internos — mejor distribución de autoridad",
        },
    }

    for char, config in NUMERIC.items():
        group_stats = analyze_numeric(posts, char, config["ranges"], config["metric"])
        if not group_stats or len(group_stats) < 2:
            continue

        best = group_stats[0]
        worst = group_stats[-1]
        diff = abs(pct_diff(best["avg_clicks"], worst["avg_clicks"]) if worst["avg_clicks"] else 0)

        if diff > 0.2:
            rec = config["rec_fn"](best)
            if char == "word_count" and best["improvement_vs_average"] > 0:
                # Extract optimal range
                lo_label, lo_val, hi_val = next(
                    (r for r in config["ranges"] if r[0] == best["value"]), (None, None, None)
                )
                if lo_val is not None:
                    insight = {
                        "characteristic": char,
                        "optimal_range": [lo_val, min(hi_val, 9999)],
                        "best_value": best["value"],
                        "improvement_vs_average": best["improvement_vs_average"],
                        "confidence": best["confidence"],
                        "recommendation": rec or f"Apuntar a {best['value']} palabras",
                        "detail": {g["value"]: {"avg_clicks": g["avg_clicks"], "n": g["n"]} for g in group_stats},
                    }
                    insights.append(insight)
                    continue

            insight = {
                "characteristic": char,
                "best_value": best["value"],
                "improvement_vs_average": best["improvement_vs_average"],
                "confidence": best["confidence"],
                "recommendation": rec or f"{char}='{best['value']}' rinde mejor",
                "detail": {g["value"]: {"avg_clicks": g["avg_clicks"], "n": g["n"]} for g in group_stats},
            }
            insights.append(insight)

    # Sort by impact (abs improvement × confidence weight)
    conf_weight = {"high": 1.0, "medium": 0.7, "low": 0.4}
    insights.sort(
        key=lambda x: abs(x["improvement_vs_average"]) * conf_weight.get(x["confidence"], 0.5),
        reverse=True,
    )

    return {
        "updated_at": date.today().isoformat(),
        "sample_size": len(posts),
        "insights": insights,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze post performance patterns")
    parser.add_argument("--site", type=str, default="inforeparto")
    parser.add_argument("--dry-run", action="store_true", help="Analyze but don't write insights file")
    args = parser.parse_args()

    global SITE, DB, POST_PERFORMANCE_TABLE, TELEGRAM_CHAT_ID
    try:
        cfg = load_site_config(args.site)
        SITE = cfg["site_id"]
        DB = cfg["db"]
        POST_PERFORMANCE_TABLE = cfg.get("post_performance_table", POST_PERFORMANCE_TABLE)
        TELEGRAM_CHAT_ID = cfg.get("telegram_chat_id", TELEGRAM_CHAT_ID)
        log.info(f"Site: {SITE} ({cfg.get('domain', '')})")
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    log.info(f"Performance analyzer — {date.today().isoformat()}")

    conn = db_connect()
    posts = load_posts_with_metrics(conn)
    conn.close()

    log.info(f"Posts con datos completos (>{MIN_GSC_DAYS}d GSC + características): {len(posts)}")

    if len(posts) < MIN_SAMPLE:
        log.info(f"Datos insuficientes ({len(posts)}/{MIN_SAMPLE}). Se necesitan más posts con datos GSC completos.")
        telegram_send(
            f"📊 Performance Analyzer — {date.today().isoformat()}\n"
            f"Datos insuficientes: {len(posts)}/{MIN_SAMPLE} posts con métricas completas.\n"
            f"El análisis empezará cuando haya más datos históricos."
        )
        return

    result = build_insights(posts)
    insights = result["insights"]

    log.info(f"Insights encontrados: {len(insights)}")
    for ins in insights:
        log.info(f"  [{ins['confidence']}] {ins['characteristic']}={ins['best_value']}: {ins['improvement_vs_average']:+.0%} vs media")
        log.info(f"    → {ins['recommendation']}")

    if not args.dry_run:
        with open(INSIGHTS_FILE, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log.info(f"Insights guardados en {INSIGHTS_FILE}")

    # ── Telegram: top 5 insights with >20% difference ──────────────────────────
    significant = [i for i in insights if abs(i["improvement_vs_average"]) > 0.20][:5]
    if significant:
        lines = [f"🔬 <b>Performance Insights — {date.today().isoformat()}</b>"]
        lines.append(f"Muestra: {result['sample_size']} posts | {len(insights)} patrones encontrados\n")
        for ins in significant:
            sign = "+" if ins["improvement_vs_average"] > 0 else ""
            conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(ins["confidence"], "⚪")
            lines.append(
                f"{conf_emoji} <b>{ins['characteristic']}</b>={ins['best_value']}: "
                f"{sign}{ins['improvement_vs_average']*100:.0f}% vs media"
            )
            lines.append(f"   → {ins['recommendation']}")
        if result["warnings"]:
            lines.append(f"\n⚠️ {result['warnings'][0]}")
        telegram_send("\n".join(lines))
    else:
        log.info("Sin insights significativos (>20% diferencia) todavía.")

    log.info("Análisis completado.")


if __name__ == "__main__":
    main()
