#!/usr/bin/env python3
"""
post_analyzer.py — Extrae características estructurales de posts generados.

Usado por autopublisher.py después de cada generación y por backfill_post_characteristics.py
para calcular métricas retroactivas sobre posts ya publicados.

Función principal: analyze_post_characteristics(html_content, brief=None) -> dict
"""

import json
import re
from typing import Any


# ── Opening type classification ────────────────────────────────────────────────

_ANECDOTE_PATTERNS = [
    r"^imagina\b",
    r"^el otro d[ií]a\b",
    r"^era\s+\w+\s+(de\s+)?(un|una|el|la)\b",
    r"^recuerdo cuando\b",
    r"^cuando\s+(trabajaba|empec[eé]|llev[aá]ba|era)\b",
    r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\s+(llevaba|trabajaba|ganaba|salía|llegó|tenía)\b",
    r"^ayer\b",
    r"^la semana pasada\b",
    r"^hace\s+(un\s+a[ñn]o|unos meses|dos años)\b",
]

_QUESTION_PATTERNS = [
    r"^¿",
    r"\?\s*$",
]

_STATISTIC_PATTERNS = [
    r"^\d+[\.,]?\d*\s*(%|€|euros|km|horas|minutos)\b",
    r"^(el|un)\s+\d+[\.,]?\d*\s*%",
    r"^(según|de acuerdo con|los datos (muestran|indican|revelan))\b",
    r"^\d{2,}\s+\w",  # starts with number ≥10
]

_HOOK_PATTERNS = [
    r"^si (eres|tienes|quieres|buscas)\b",
    r"^lo que nadie\b",
    r"^la verdad (es|sobre)\b",
    r"^nadie te (dice|cuenta|explica)\b",
    r"^todo el mundo (sabe|cree|piensa)\b",
    r"^(cuidado|atenci[oó]n|ojo)\b",
    r"^(el secreto|el truco|el error)\b",
]


def classify_opening_type(html: str) -> str:
    """
    Classify the opening paragraph of a post.
    Returns one of: 'anecdote', 'question', 'statistic', 'hook', 'statement'
    """
    # Extract first non-empty paragraph
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
    first_text = ""
    for p in paragraphs:
        clean = re.sub(r"<[^>]+>", " ", p).strip()
        if len(clean) > 30:
            first_text = clean
            break

    if not first_text:
        return "statement"

    t = first_text.lower().strip()

    for pat in _QUESTION_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return "question"

    for pat in _ANECDOTE_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return "anecdote"

    for pat in _STATISTIC_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return "statistic"

    for pat in _HOOK_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return "hook"

    return "statement"


# ── Affiliate link positions ───────────────────────────────────────────────────

def get_affiliate_positions(html: str) -> list[float]:
    """
    Return relative positions (0.0–1.0) of Amazon affiliate links in the document.
    Position = character offset of link / total document length.
    """
    total = len(html)
    if total == 0:
        return []
    positions = []
    for m in re.finditer(r'href="https://www\.amazon\.es/dp/', html, re.IGNORECASE):
        positions.append(round(m.start() / total, 3))
    return positions


# ── Experience count ────────────────────────────────────────────────────────────

_EXPERIENCE_PATTERNS = [
    r"\bme\s+(pas[oó]|ocurri[oó]|dijeron|contaron|llam[oó])\b",
    r"\b(un|una)\s+(repartidor|rider|compañero|mensajero|chico|chica)\s+(me\s+)?(cont[oó]|dijo|comentó|explicó)\b",
    r"\bcuando\s+(trabajaba|empec[eé]|hice|estaba haciendo)\b",
    r'\b(recuerdo|me acuerdo)\b',
    r"<blockquote",
    r'class="(experiencia|anecdote|testimony|testimonio)"',
    r"\b(yo\s+mismo|en mi caso|a m[ií]|me\s+ha\s+pasado)\b",
]


def count_experiences(html: str) -> int:
    """Count first-person experience signals in HTML content."""
    text = html.lower()
    count = 0
    for pat in _EXPERIENCE_PATTERNS:
        matches = re.findall(pat, text, re.IGNORECASE)
        count += len(matches)
    # Cap to avoid noise — each real experience likely triggers 1-3 patterns
    return min(count, 10)


# ── External sources ────────────────────────────────────────────────────────────

def count_external_sources(html: str, wp_url: str = "https://inforeparto.com") -> int:
    """Count distinct external (non-Amazon, non-internal) href links."""
    links = re.findall(r'href="(https?://[^"]+)"', html, re.IGNORECASE)
    seen = set()
    count = 0
    for link in links:
        domain = re.match(r"https?://([^/]+)", link)
        if not domain:
            continue
        d = domain.group(1).lower()
        if d in seen:
            continue
        seen.add(d)
        # Skip internal and Amazon
        if wp_url.lower().rstrip("/") in link.lower():
            continue
        if "amazon." in d:
            continue
        count += 1
    return count


# ── Main analyzer ──────────────────────────────────────────────────────────────

def analyze_post_characteristics(html_content: str, brief: dict | None = None, wp_url: str = "https://inforeparto.com") -> dict:
    """
    Extract structural characteristics from a generated post HTML.

    Args:
        html_content: Raw HTML of the post body.
        brief: Optional research dict from research_phase() for additional counts.
        wp_url: Base URL of the site for internal link detection.

    Returns:
        dict with all measurable characteristics.
    """
    html = html_content or ""

    # Strip script/style content to avoid counting them
    clean_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    plain_text = re.sub(r"<[^>]+>", " ", clean_html)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    words = plain_text.split()
    word_count = len(words)

    # Structural counts
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
    non_empty_paragraphs = [p for p in paragraphs if re.sub(r"<[^>]+>", "", p).strip()]
    paragraph_count = len(non_empty_paragraphs)

    if paragraph_count > 0:
        total_p_words = sum(
            len(re.sub(r"<[^>]+>", " ", p).split()) for p in non_empty_paragraphs
        )
        avg_paragraph_length = round(total_p_words / paragraph_count, 1)
    else:
        avg_paragraph_length = 0.0

    h2_count = len(re.findall(r"<h2[\s>]", html, re.IGNORECASE))
    h3_count = len(re.findall(r"<h3[\s>]", html, re.IGNORECASE))
    list_count = len(re.findall(r"<(ul|ol)[\s>]", html, re.IGNORECASE))
    has_table = bool(re.search(r"<table[\s>]", html, re.IGNORECASE))

    # Opening classification
    opening_type = classify_opening_type(html)

    # Affiliate links
    affiliate_links = re.findall(r'href="https://www\.amazon\.es/dp/', html, re.IGNORECASE)
    affiliate_count = len(affiliate_links)
    affiliate_positions = get_affiliate_positions(html)

    # Internal links (links to wp_url)
    internal_links = re.findall(rf'href="{re.escape(wp_url)}[^"]*"', html, re.IGNORECASE)
    internal_link_count = len(internal_links)

    # External sources
    external_source_count = count_external_sources(html, wp_url)

    # Disclaimer
    has_disclaimer = bool(
        re.search(r'class="(aviso-afiliados|disclaimer|aviso-legal|aviso-ymyl)"', html, re.IGNORECASE)
        or re.search(r"(este artículo contiene enlaces de afiliado|este contenido es solo informativo)", html, re.IGNORECASE)
    )

    # Experience count
    experience_count = count_experiences(html)
    # If brief is provided, use its experience list as ground truth
    if brief and isinstance(brief.get("experiences"), list):
        experience_count = max(experience_count, len(brief["experiences"]))

    # Schema type from HTML
    schema_type = _detect_schema_type(html)

    # Reading time
    reading_time_minutes = round(word_count / 200, 1)

    return {
        "word_count": word_count,
        "paragraph_count": paragraph_count,
        "avg_paragraph_length": avg_paragraph_length,
        "h2_count": h2_count,
        "h3_count": h3_count,
        "list_count": list_count,
        "has_table": has_table,
        "opening_type": opening_type,
        "affiliate_count": affiliate_count,
        "affiliate_positions": affiliate_positions,
        "internal_link_count": internal_link_count,
        "external_source_count": external_source_count,
        "has_disclaimer": has_disclaimer,
        "experience_count": experience_count,
        "schema_type": schema_type,
        "reading_time_minutes": reading_time_minutes,
    }


def _detect_schema_type(html: str) -> str:
    """Detect FAQ, HowTo, ItemList, or Article schema type from HTML structure."""
    faq_count = len(re.findall(r'<div[^>]+class="[^"]*faq[^"]*"', html, re.IGNORECASE))
    has_faq_section = bool(re.search(r"<h[23][^>]*>.*?(preguntas|faq|dudas|frecuentes).*?</h[23]>", html, re.IGNORECASE | re.DOTALL))
    qa_pattern = len(re.findall(r"<h[23][^>]*>.*?\?.*?</h[23]>", html, re.IGNORECASE))

    if faq_count >= 2 or has_faq_section or qa_pattern >= 3:
        return "FAQPage"

    howto_signals = len(re.findall(r"<h[23][^>]*>\s*(paso\s+\d|step\s+\d|cómo\s+\w|c[oó]mo\s+hacer)", html, re.IGNORECASE))
    ol_steps = len(re.findall(r"<ol[^>]*>", html, re.IGNORECASE))
    if howto_signals >= 2 or (ol_steps >= 1 and re.search(r"(cómo|guía|pasos?)", html, re.IGNORECASE)):
        return "HowTo"

    list_items = len(re.findall(r"<li[^>]*>", html, re.IGNORECASE))
    h2_with_products = len(re.findall(r"<h[23][^>]*>.*?(mejor|top|recomend|product)", html, re.IGNORECASE))
    if list_items >= 5 and h2_with_products >= 2:
        return "ItemList"

    return "Article"
