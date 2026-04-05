#!/usr/bin/env python3
"""
Naturalizer v4 — Sistema de Naturalización por Capas (Mash) + E-E-A-T
Fase 1: Capas 1+2+3+3b (forma) + Capas 7 (NaturalScore) + 8 (integridad)

Uso CLI:
  python naturalizer.py --post-id 123 456
  python naturalizer.py --post-id 123 --site inforeparto --dry-run --verbose
  python naturalizer.py --modified-today
  python naturalizer.py --post-id 123 --backup

Uso como módulo (pipeline):
  from naturalizer import naturalize
  result = naturalize(content, title, site="inforeparto")
  # result: {'content': str, 'score': dict, 'integrity_ok': bool, 'needs_review': bool, 'issues': list}
"""

import argparse
import json
import math
import os
import re
import sys
import subprocess
import datetime
import difflib
import uuid
from pathlib import Path
from typing import Optional

import yaml
import mysql.connector
import anthropic

# ── Paths ──────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
CONTEXTOS_DIR = BASE_DIR / "contextos"

PATTERNS_FILE = CONFIG_DIR / "patterns_es.yaml"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
EXPRESIONES_FILE = CONFIG_DIR / "expresiones_es.yaml"

# ── DB config ──────────────────────────────────────────────────────────────────

DB_CONFIGS = {
    "inforeparto": dict(
        host=os.environ.get("WP_DB_HOST", "localhost"),
        user=os.environ.get("WP_DB_USER", "wp_user"),
        password=os.environ.get("WP_DB_PASSWORD", ""),
        database=os.environ.get("WP_DB_NAME", "wordpress_db"),
    ),
}


def _get_db_config(site: str) -> dict:
    if site in DB_CONFIGS:
        return DB_CONFIGS[site]
    # Try to read from wp-config.php
    wp_config = Path(f"/var/www/{site}/wp-config.php")
    if wp_config.exists():
        text = wp_config.read_text()
        user = re.search(r"DB_USER['\"], ['\"]([^'\"]+)", text)
        pw = re.search(r"DB_PASSWORD['\"], ['\"]([^'\"]+)", text)
        db = re.search(r"DB_NAME['\"], ['\"]([^'\"]+)", text)
        if user and pw and db:
            return dict(host="localhost", user=user.group(1), password=pw.group(1), database=db.group(1))
    raise ValueError(f"No DB config found for site '{site}'")


# ── Config loading ─────────────────────────────────────────────────────────────

def load_config() -> tuple[dict, dict, dict]:
    """Load settings, patterns, expresiones. Returns (settings, patterns, expresiones)."""
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    with open(PATTERNS_FILE, encoding="utf-8") as f:
        patterns = yaml.safe_load(f)
    try:
        with open(EXPRESIONES_FILE, encoding="utf-8") as f:
            expresiones = yaml.safe_load(f)
    except FileNotFoundError:
        expresiones = {}
    return settings, patterns, expresiones


def load_voice(site: str) -> dict:
    """Load voice profile from contextos/{site}/voz.md. Returns frontmatter dict + _body."""
    voz_file = CONTEXTOS_DIR / site / "voz.md"
    if not voz_file.exists():
        raise FileNotFoundError(f"Voice profile not found: {voz_file}")
    content = voz_file.read_text(encoding="utf-8")
    meta = {}
    match = re.match(r"^---\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        meta = yaml.safe_load(match.group(1)) or {}
    meta["_body"] = content
    return meta


# ── System prompt builder ──────────────────────────────────────────────────────

def _extract_patterns_flat(patterns: dict) -> dict:
    """Flatten patterns dict into lists per category."""
    result = {}

    def _collect(obj):
        if isinstance(obj, list):
            return [i for i in obj if isinstance(i, str)]
        elif isinstance(obj, dict):
            items = []
            for v in obj.values():
                items.extend(_collect(v))
            return items
        return []

    for key, val in patterns.items():
        result[key] = _collect(val)

    return result


def _extract_expresiones_priority(expresiones: dict) -> list[str]:
    """Extract top expressions from expresiones_es.yaml for prompt."""
    lines = []
    # Priority 1: marcadores_discursivos
    md = expresiones.get("marcadores_discursivos", {})
    if isinstance(md, dict):
        for item in md.get("expresiones", [])[:7]:
            if isinstance(item, dict):
                expr = item.get("expr", "")
                func = item.get("funcion", "")
                if expr:
                    lines.append(f'"{expr}" ({func})')
    # Priority 2: conexion_lector
    cl = expresiones.get("conexion_lector", {})
    if isinstance(cl, dict):
        for item in cl.get("expresiones", [])[:5]:
            if isinstance(item, dict):
                expr = item.get("expr", "")
                uso = item.get("uso_ideal", "")
                if expr:
                    lines.append(f'"{expr}" ({uso})')
    return lines


def _extract_jerga_from_body(body: str) -> list[str]:
    """Extract jerga table rows from voz.md body."""
    lines = []
    in_table = False
    for line in body.split("\n"):
        if "| Expresión |" in line or "| expresión |" in line.lower():
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 2:
                lines.append(f"{cols[0]} → {cols[1]}")
        elif in_table and not line.startswith("|"):
            in_table = False
        if len(lines) >= 15:
            break
    return lines


def _extract_marcadores_from_body(body: str) -> list[str]:
    """Extract marcadores de experiencia from voz.md body."""
    section = re.search(r"## Marcadores de experiencia\n\n(.*?)\n\n##", body, re.DOTALL)
    if not section:
        return []
    lines = []
    for line in section.group(1).split("\n"):
        line = line.strip()
        if line.startswith("-"):
            clean = line.lstrip("- \"").rstrip("\"")
            if clean:
                lines.append(clean)
    return lines[:5]


def build_system_prompt(patterns: dict, expresiones: dict, voice: dict, experiences: list = None, competitor_report: str = None) -> str:
    """Build combined Capa 1+2+3+3b (+Capa 4 experiences +Capa 6 competitive) system prompt for Claude."""
    flat = _extract_patterns_flat(patterns)

    muletillas = flat.get("muletillas", [])[:30]
    intensificadores = flat.get("intensificadores_vacios", [])[:12]

    trans_all = []
    for key in ["secuencias_numeradas", "conectores_formales", "referencias_anteriores"]:
        trans_all.extend(flat.get(f"transiciones_roboticas_{key}", []))
    if not trans_all:
        trans_all = flat.get("transiciones_roboticas", [])[:15]

    arranques = flat.get("arranques_vacios", [])[:10]
    expresiones_list = _extract_expresiones_priority(expresiones)

    body = voice.get("_body", "")
    site_name = str(voice.get("site", "inforeparto")).capitalize()
    site_url = voice.get("url", "")
    tono = voice.get("tono", "directo-práctico")
    registro = voice.get("registro", "informal-medio")
    tuteo = voice.get("tuteo", True)
    humor = voice.get("humor_ironia", False)

    jerga_lines = _extract_jerga_from_body(body)
    marcadores = _extract_marcadores_from_body(body)

    def bullets(items, prefix="  •"):
        return "\n".join(f"{prefix} {i}" for i in items) if items else "  (ver patterns_es.yaml)"

    humor_line = (
        "HUMOR E IRONÍA: Permitido y bienvenido. Ironía sobre costes/plataformas, complicidad con el lector, realismo con humor. Nunca forzado ni gratuito."
        if humor
        else "HUMOR E IRONÍA: No usar."
    )

    # Capa 4: experience block
    experiences_block = ""
    if experiences:
        exp_lines = []
        for exp in experiences:
            type_label = {
                "metric": "Dato propio",
                "anecdote": "Anécdota/escena",
                "regulatory": "Contexto normativo",
                "comparison": "Comparativa propia",
                "user_feedback": "Feedback usuarios",
                "process_insight": "Proceso de investigación",
                "seasonal": "Contexto estacional",
            }.get(exp["type"], exp["type"])
            exp_lines.append(f'  [{type_label}] "{exp["content"]}"')
        experiences_block = (
            "\n\n═══════════════════════════════════════════════════════════════\n"
            "CAPA 4 — EXPERIENCIAS REALES DISPONIBLES\n"
            "═══════════════════════════════════════════════════════════════\n\n"
            "Tienes estas experiencias reales. Intégra 1-2 de forma completamente natural:\n"
            "  • En las primeras 3 frases (refuerza el gancho de Capa 3b)\n"
            "  • Justo después de una afirmación importante\n"
            "  • En el cierre si refuerza el mensaje\n"
            "NUNCA fabricar datos ni fuentes. Solo usar las que aparecen aquí:\n\n"
        ) + "\n".join(exp_lines)

    # Capa 6: competitive differentiation block
    competitor_block = ""
    if competitor_report:
        competitor_block = (
            "\n\n═══════════════════════════════════════════════════════════════\n"
            "CAPA 6 — DIFERENCIACIÓN COMPETITIVA\n"
            "═══════════════════════════════════════════════════════════════\n\n"
            "Análisis del top 3 de Google para este topic:\n\n"
            + competitor_report
            + "\n\nAl reescribir, asegúrate de destacar los ÁNGULOS QUE ELLOS IGNORAN."
        )

    num_extra = sum([bool(experiences), bool(competitor_report)])
    num_ops = str(4 + num_extra)
    return f"""Eres el editor de {site_name} ({site_url}). Tu trabajo es transformar el borrador HTML que recibes en texto que un profesional con experiencia real habría escrito.

Ejecutas {num_ops} operaciones en UN SOLO PASO, en este orden:

═══════════════════════════════════════════════════════════════
CAPA 1 — ELIMINA PATRONES IA
═══════════════════════════════════════════════════════════════

MULETILLAS — eliminar o reformular de forma completamente natural (no sustituir por sinónimo, reformular la idea):
{bullets(muletillas)}

INTENSIFICADORES VACÍOS — eliminar sin sustituir:
{bullets(intensificadores)}

TRANSICIONES ROBÓTICAS — sustituir por conectores coloquiales naturales o suprimir:
{bullets(trans_all[:12])}

ARRANQUES VACÍOS — eliminar el arranque y arrancar directo con la idea:
{bullets(arranques)}

ESTRUCTURAS A ROMPER:
  • Triadas perfectas (A, B y C con estructura idéntica) → variar: 2, 4, o 1 desarrollado
  • Párrafos de longitud uniforme → romper la simetría de forma deliberada
  • Listas donde cabe prosa → narrativizar al menos 1 de cada 3 listas
  • Em dashes (—) en exceso (>2 por 500 palabras) → coma o reformulación
  • Intros que anuncian el contenido ("En este artículo...") → suprimir, ir directo
  • Conclusiones que repiten la intro → perspectiva nueva o llamada a la acción concreta

═══════════════════════════════════════════════════════════════
CAPA 2 — INYECTA VOZ DE {site_name.upper()}
═══════════════════════════════════════════════════════════════

Tono: {tono} | Registro: {registro} | {"Tutéa siempre al lector. Nunca 'usted'." if tuteo else "Tratamiento de usted."}

VOCABULARIO DEL SECTOR (usar cuando encaje de forma natural, no forzar):
{bullets(jerga_lines) if jerga_lines else "  (ver contextos/" + voice.get("site", "inforeparto") + "/voz.md)"}

EXPRESIONES INFORMALES (usar 4-6 en total, distribuidas, nunca acumuladas):
{bullets(expresiones_list) if expresiones_list else "  (ver config/expresiones_es.yaml)"}

{"MARCADORES DE EXPERIENCIA (usar 1-2 para añadir E-E-A-T):" if marcadores else ""}
{chr(10).join(f'  • "{m}"' for m in marcadores) if marcadores else ""}

{humor_line}

═══════════════════════════════════════════════════════════════
CAPA 3 — VARIABILIDAD SINTÁCTICA
═══════════════════════════════════════════════════════════════

  • Mezcla frases cortas (5-10 palabras) con largas (25-35 palabras). El ritmo debe sonar irregular al leerlo en voz alta.
  • Varía el arranque de cada párrafo: no repitas la misma estructura en dos párrafos consecutivos.
  • Incluye 2-3 preguntas retóricas en artículos largos (>1000 palabras). No más.
  • Permite 1-2 digresiones breves ("esto me recuerda a...", "de hecho...", "curioso, porque...").
  • Si hay 3+ párrafos largos seguidos: rompe con una frase corta de impacto (una sola oración).
  • H3 técnicos: reformular como lo explicaría un colega. "Lo del IRPF, que siempre lía" > "Retención de IRPF".

═══════════════════════════════════════════════════════════════
CAPA 3b — GANCHO DE APERTURA ⚡ (PRIORIDAD MÁXIMA)
═══════════════════════════════════════════════════════════════

Las primeras 3-4 frases son el punto más analizado por detectores y donde el lector decide si sigue.

PROHIBIDO empezar con:
  • Definición: "X es un proceso/concepto/sistema que..."
  • Generalización: "En la actualidad...", "Hoy en día...", "En el mundo moderno..."
  • Anuncio de contenido: "En este artículo veremos...", "Vamos a hablar de..."
  • Cualquier muletilla de Capa 1

OBLIGATORIO: usar uno de estos 5 patrones (rotar entre artículos del mismo sitio):
  1. Escena concreta: situación real del sector narrada en 2-3 frases vívidas
  2. Dato sorprendente: estadística o hecho verificable y poco conocido
  3. Pregunta provocadora: que el lector no sepa responder aún
  4. Afirmación contra-intuitiva: que contradiga la expectativa obvia
  5. Humor/ironía: solo si el tema lo permite de forma natural

Test obligatorio: ¿Podrían estas 3 primeras frases haberlas generado cualquier chatbot genérico? Si la respuesta es sí → reescribir.

═══════════════════════════════════════════════════════════════
RESTRICCIONES ABSOLUTAS (NO MODIFICAR NUNCA)
═══════════════════════════════════════════════════════════════

  • Bloques HTML con clase: aviso-afiliados, aviso-actualizacion, disclaimer-legal, disclaimer-fiscal, disclaimer-ganancias, disclaimer-convenio
  • Etiquetas <script type="application/ld+json">
  • URLs amazon.es/dp/ y cualquier enlace href existente
  • Shortcodes WordPress entre corchetes [...]
  • Cifras concretas, porcentajes, fechas específicas, nombres de leyes y normativas
  • Modelos fiscales (Modelo 303, 130, 036, 347, etc.)
  • HTML estructural: etiquetas, atributos, clases CSS
  • Bloques <table> completos con sus datos

Devuelve SOLO el HTML reescrito. Sin explicaciones, sin comentarios, sin bloques markdown.
{experiences_block}{competitor_block}"""


# ── NaturalScore — Capa 7 ──────────────────────────────────────────────────────

class NaturalScorer:
    """Métricas de naturalidad del texto. Puntuación 0-100."""

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"<[^>]+>", " ", text)

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip().split()) > 2]

    @classmethod
    def burstiness(cls, text: str) -> float:
        """CV de longitud de frases. Más variación = más humano. Target: CV > 0.5."""
        sents = cls._sentences(cls._clean(text))
        if len(sents) < 4:
            return 0.5
        lengths = [len(s.split()) for s in sents]
        mean = sum(lengths) / len(lengths)
        if mean == 0:
            return 0.0
        std = math.sqrt(sum((l - mean) ** 2 for l in lengths) / len(lengths))
        cv = std / mean
        return min(1.0, cv / 0.65)

    @classmethod
    def lexical_diversity(cls, text: str) -> float:
        """MATTR con ventana de 100 palabras. Target: MATTR > 0.72."""
        words = re.findall(r"\b[a-záéíóúüñ]+\b", cls._clean(text).lower())
        if len(words) < 30:
            return 0.5
        window = min(100, len(words))
        if len(words) <= window:
            return len(set(words)) / len(words)
        ttrs = []
        for i in range(len(words) - window + 1):
            w = words[i : i + window]
            ttrs.append(len(set(w)) / window)
        return sum(ttrs) / len(ttrs)

    @classmethod
    def pattern_penalty(cls, text: str, patterns: dict) -> float:
        """Fracción de patrones IA encontrados. Menor = mejor."""
        clean = cls._clean(text).lower()
        found = 0
        total = 0

        def _scan(obj):
            nonlocal found, total
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str) and len(item) > 5:
                        total += 1
                        if item.lower() in clean:
                            found += 1
            elif isinstance(obj, dict):
                for v in obj.values():
                    _scan(v)

        _scan(patterns)
        return found / max(total, 1)

    @classmethod
    def paragraph_variance(cls, text: str) -> float:
        """Varianza de longitud de párrafos. Mayor varianza = menos robótico."""
        clean = cls._clean(text)
        paragraphs = [p.strip() for p in re.split(r"\n\n+", clean) if len(p.strip().split()) > 5]
        if len(paragraphs) < 3:
            return 0.5
        lengths = [len(p.split()) for p in paragraphs]
        mean = sum(lengths) / len(lengths)
        if mean == 0:
            return 0.0
        variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
        return min(1.0, variance / 400)

    @classmethod
    def opening_score(cls, text: str, bad_openers: list) -> float:
        """Comprueba si las primeras frases son genéricas. 1.0 = buen gancho."""
        clean = cls._clean(text).strip()
        first = clean[:500].lower()
        for opener in bad_openers:
            if isinstance(opener, str) and opener.lower() in first[:200]:
                return 0.1
        generic_patterns = [
            r"^(en la actualidad|hoy en día|actualmente|en el mundo|en la sociedad)",
            r"^(en este artículo|en este post|a lo largo de este)",
            r"^\w+ (es un|es una|es el|es la) (proceso|concepto|sistema|herramienta|método|elemento)",
        ]
        for pat in generic_patterns:
            if re.match(pat, first):
                return 0.2
        return 1.0

    @classmethod
    def score(cls, text: str, patterns: dict = None, bad_openers: list = None, source_density: float = 0.5) -> dict:
        burst = cls.burstiness(text)
        lexical = cls.lexical_diversity(text)
        penalty = cls.pattern_penalty(text, patterns or {})
        para_var = cls.paragraph_variance(text)
        opening = cls.opening_score(text, bad_openers or [])

        raw = (
            burst * 0.20
            + lexical * 0.20
            + (1 - penalty) * 0.25
            + para_var * 0.10
            + opening * 0.15
            + source_density * 0.10
        )
        overall = round(raw * 100)
        return {
            "overall": overall,
            "burstiness": round(burst * 100),
            "lexical_diversity": round(lexical * 100),
            "pattern_penalty": round(penalty * 100),
            "paragraph_variance": round(para_var * 100),
            "opening": round(opening * 100),
            "source_density": round(source_density * 100),
        }


# ── Capa 8: Integridad semántica ───────────────────────────────────────────────

_INTEGRITY_SYSTEM = """Eres un auditor de contenido. Compara el original y el texto naturalizado y verifica que no se ha perdido información esencial.

Responde ÚNICAMENTE con JSON, sin texto adicional:
{"ok": true, "issues": []}

Comprueba:
1. Los puntos clave del original están presentes (aunque reformulados)
2. No hay afirmaciones falsas introducidas
3. Las keywords SEO principales se conservan
4. Las cifras, fechas y datos numéricos son idénticos
5. Los nombres de leyes, modelos fiscales y normativas son idénticos

Si todo OK: {"ok": true, "issues": []}
Si hay problemas: {"ok": false, "issues": ["descripción del problema"]}"""


def check_integrity(original: str, naturalized: str, title: str, settings: dict) -> tuple[bool, list[str]]:
    """Capa 8: verificación semántica via Claude Haiku."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return True, ["ANTHROPIC_API_KEY no disponible — integridad omitida"]

    model = settings.get("models", {}).get("integridad", "claude-haiku-4-5-20251001")
    trim = settings.get("pipeline", {}).get("integrity_check_chars", 3000)

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=_INTEGRITY_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Título: {title}\n\n"
                        f"ORIGINAL:\n{original[:trim]}\n\n"
                        f"NATURALIZADO:\n{naturalized[:trim]}"
                    ),
                }
            ],
        )
        raw = resp.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return True, []
        result = json.loads(match.group(0))
        return result.get("ok", True), result.get("issues", [])
    except Exception as e:
        return True, [f"Capa 8 error (no bloqueante): {e}"]


# ── Protected blocks ───────────────────────────────────────────────────────────

_PROTECTED_PATTERNS = [
    re.compile(
        r'<(?:p|div)[^>]*class="(?:aviso-afiliados|aviso-actualizacion|disclaimer-legal|'
        r'disclaimer-fiscal|disclaimer-ganancias|disclaimer-convenio)[^"]*"[^>]*>.*?</(?:p|div)>',
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>', re.DOTALL | re.IGNORECASE),
    re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE),
    re.compile(r"\[[^\]]+\]", re.DOTALL),
]


def extract_protected(content: str) -> tuple[str, dict]:
    placeholders: dict = {}
    for pattern in _PROTECTED_PATTERNS:
        def replacer(m, _ph=placeholders):
            key = f"__PROTECTED_{uuid.uuid4().hex}__"
            _ph[key] = m.group(0)
            return key
        content = pattern.sub(replacer, content)
    return content, placeholders


def restore_protected(content: str, placeholders: dict) -> str:
    for key, original in placeholders.items():
        content = content.replace(key, original)
    return content


def verify_structural_integrity(original: str, result: str) -> list[str]:
    """Verify Amazon links and disclaimer blocks are intact."""
    errors = []
    amazon_orig = set(re.findall(r"https://www\.amazon\.es/dp/[^\"'\s>]+", original))
    amazon_result = set(re.findall(r"https://www\.amazon\.es/dp/[^\"'\s>]+", result))
    missing = amazon_orig - amazon_result
    if missing:
        errors.append(f"Amazon links perdidos: {missing}")
    for cls in ("aviso-afiliados", "aviso-actualizacion", "disclaimer-legal", "disclaimer-fiscal", "disclaimer-ganancias", "disclaimer-convenio"):
        if cls in original and cls not in result:
            errors.append(f"Bloque {cls} desaparecido")
    return errors


# ── Core naturalization ────────────────────────────────────────────────────────

def _naturalize_api_call(content: str, title: str, system_prompt: str, settings: dict) -> str:
    """Single Claude API call for capas 1+2+3+3b."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no definida")

    model = settings.get("models", {}).get("naturalizacion", "claude-sonnet-4-6")
    max_chars = settings.get("pipeline", {}).get("max_content_chars", 80_000)
    chunk_size = settings.get("pipeline", {}).get("chunk_size", 75_000)
    client = anthropic.Anthropic(api_key=api_key)

    if len(content) <= max_chars:
        resp = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Título del post: {title}\n\n{content}"}],
        )
        return resp.content[0].text

    # Chunk for very long posts
    chunks = []
    current = ""
    for para in re.split(r"(?<=</p>)", content):
        if len(current) + len(para) > chunk_size:
            if current:
                chunks.append(current)
            current = para
        else:
            current += para
    if current:
        chunks.append(current)

    parts = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  Fragmento {i}/{len(chunks)}...")
        resp = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Título: {title} (fragmento {i}/{len(chunks)})\n\n{chunk}"}],
        )
        parts.append(resp.content[0].text)
    return "".join(parts)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1:]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return text.strip()


# ── Public API ─────────────────────────────────────────────────────────────────

def naturalize(
    content: str,
    title: str,
    site: str = "inforeparto",
    post_id: int = None,
    post_url: str = "",
    post_date: str = "",
) -> dict:
    """
    Public pipeline API. Runs Fase 1+2+3 (Capas 1+2+3+3b+4+5b+6+6b+7+8).

    Returns:
        {
            'content': str,
            'score': dict,
            'integrity_ok': bool,
            'needs_review': bool,
            'issues': list[str],
            'experiences_used': list,
            'sources_added': list,
            'competitor_report': str | None,
        }
    """
    settings, patterns, expresiones = load_config()
    voice = load_voice(site)
    threshold = settings.get("natural_score", {}).get("thresholds", {}).get("ok", 70)
    max_retries = settings.get("natural_score", {}).get("max_retries", 2)
    bad_openers = patterns.get("malas_aperturas", [])

    fase2_active = bool(settings.get("capas_activas", {}).get("fase2"))
    fase3_active = bool(settings.get("capas_activas", {}).get("fase3"))
    serper_ok = bool(os.environ.get("SERPER_API_KEY"))

    # Capa 4: fetch experiences
    experiences = []
    exp_db = None
    if fase2_active:
        try:
            from experience_db import ExperienceDB
            exp_db = ExperienceDB(site)
            experiences = exp_db.get_for_topic(title, limit=2)
        except Exception:
            pass

    # Capa 6: competitive analysis (before main prompt)
    competitor_report = None
    if fase3_active and serper_ok:
        try:
            from competitor import CompetitorAnalyzer
            analyzer = CompetitorAnalyzer(site)
            competitor_report = analyzer.analyze(title, content[:1500])
        except Exception:
            pass

    system_prompt = build_system_prompt(
        patterns, expresiones, voice,
        experiences=experiences or None,
        competitor_report=competitor_report,
    )

    # Extract protected blocks
    clean_content, placeholders = extract_protected(content)

    # Capas 1+2+3+3b+4+6: main Sonnet call with retry
    best_result = None
    best_score = None
    for attempt in range(max_retries + 1):
        raw = _naturalize_api_call(clean_content, title, system_prompt, settings)
        raw = _strip_code_fences(raw)
        sc = NaturalScorer.score(raw, patterns, bad_openers)
        if best_score is None or sc["overall"] > best_score["overall"]:
            best_result = raw
            best_score = sc
        if sc["overall"] >= threshold:
            break

    naturalized = restore_protected(best_result, placeholders)

    # Capa 5b: source injection
    sources_added = []
    if fase2_active and serper_ok:
        try:
            from sources import SourceInjector
            injector = SourceInjector(site)
            naturalized, sources_added = injector.inject(naturalized, title)
        except Exception:
            pass

    # Capa 6b: author byline + Organization schema
    if fase3_active:
        try:
            from author_schema import inject_author_signals
            naturalized, _ = inject_author_signals(
                naturalized, site=site, post_title=title,
                post_url=post_url, post_date=post_date,
            )
        except Exception:
            pass

    # Recalculate NaturalScore with real source_density now that Capa 5b ran
    if sources_added:
        density = min(1.0, len(sources_added) / 3)
        best_score = NaturalScorer.score(best_result, patterns, bad_openers, source_density=density)

    # Capa 8: integrity
    integrity_ok, issues = check_integrity(content, naturalized, title, settings)

    # Capa 9: log to ir_naturalization_log
    experiences_used = [e["content"][:60] for e in experiences]
    sources_list = [s.get("url", "") for s in sources_added]
    if post_id:
        try:
            db_config = _get_db_config(site)
            import mysql.connector as _mc
            conn = _mc.connect(**db_config)
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ir_naturalization_log
                   (site, topic, wp_post_id, score_after, experiences_used, sources_added)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    site, title, post_id, best_score["overall"],
                    json.dumps(experiences_used, ensure_ascii=False),
                    json.dumps(sources_list, ensure_ascii=False),
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

    # Mark experiences as used only after full pipeline completes successfully
    if experiences and exp_db:
        try:
            exp_db.mark_used([e["id"] for e in experiences])
        except Exception:
            pass

    return {
        "content": naturalized,
        "score": best_score,
        "integrity_ok": integrity_ok,
        "needs_review": best_score["overall"] < threshold,
        "issues": issues,
        "experiences_used": experiences_used,
        "sources_added": sources_list,
        "competitor_report": competitor_report,
    }


# ── CLI helpers ────────────────────────────────────────────────────────────────

def _show_diff(original: str, result: str, post_id: int):
    orig_lines = original.splitlines(keepends=True)
    result_lines = result.splitlines(keepends=True)
    diff = list(difflib.unified_diff(orig_lines, result_lines, fromfile=f"post_{post_id}_original", tofile=f"post_{post_id}_naturalizado", n=2))
    if diff:
        for line in diff[:300]:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"\033[32m{line}\033[0m", end="")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"\033[31m{line}\033[0m", end="")
            else:
                print(line, end="")
    else:
        print("  (sin cambios detectados)")


def _process_post(post_id: int, site: str, dry_run: bool, verbose: bool, conn) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT post_title, post_content FROM wp_posts WHERE ID = %s AND post_status IN ('publish','draft','future')",
        (post_id,),
    )
    row = cur.fetchone()
    if not row:
        print(f"  ⚠️  Post {post_id} no encontrado o no publicado.")
        cur.close()
        return False

    title, content = row
    print(f"\n── Post [{post_id}] {title[:60]} ──")
    print(f"  Tamaño original: {len(content)} chars")

    try:
        result = naturalize(content, title, site=site)
    except Exception as e:
        print(f"  ❌ Error en naturalización: {e}")
        cur.close()
        return False

    naturalized = result["content"]
    sc = result["score"]
    integrity_ok = result["integrity_ok"]
    issues = result["issues"]

    # Structural check (Amazon links, disclaimers)
    struct_errors = verify_structural_integrity(content, naturalized)
    if struct_errors:
        print(f"  ❌ VERIFICACIÓN ESTRUCTURAL FALLIDA — abortando:")
        for err in struct_errors:
            print(f"     • {err}")
        cur.close()
        return False

    # Score report
    score_emoji = "✅" if sc["overall"] >= 70 else ("⚠️" if sc["overall"] >= 50 else "❌")
    print(f"  NaturalScore: {sc['overall']}/100 {score_emoji}")
    if verbose:
        print(f"    Burstiness: {sc['burstiness']} | Lexical: {sc['lexical_diversity']} | Patterns: {sc['pattern_penalty']}% | ParaVar: {sc['paragraph_variance']} | Opening: {sc['opening']}")
    if result.get("experiences_used"):
        print(f"  Capa 4: {len(result['experiences_used'])} experiencia(s) inyectada(s)")
    if result.get("sources_added"):
        print(f"  Capa 5b: {len(result['sources_added'])} fuente(s) añadida(s)")
    if result.get("competitor_report"):
        print(f"  Capa 6: análisis competitivo aplicado")

    if not integrity_ok:
        print(f"  ⚠️  Integridad (Capa 8): {issues}")

    if result["needs_review"]:
        print(f"  ⚠️  NaturalScore bajo — marcar para revisión humana.")

    if verbose:
        print("\n  ── DIFF ──")
        _show_diff(content, naturalized, post_id)
        print()

    if dry_run:
        print(f"  [DRY-RUN] No guardado.")
    else:
        cur.execute(
            "UPDATE wp_posts SET post_content = %s, post_modified = NOW(), post_modified_gmt = UTC_TIMESTAMP() WHERE ID = %s",
            (naturalized, post_id),
        )
        conn.commit()
        print(f"  💾 Guardado en DB.")

    cur.close()
    return True


def _get_modified_today_ids(site: str, conn) -> list[int]:
    today = datetime.date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT ID FROM wp_posts WHERE DATE(post_modified) = %s AND post_status IN ('publish','draft','future') AND post_type IN ('post','page')",
        (today,),
    )
    ids = [row[0] for row in cur.fetchall()]
    cur.close()
    return ids


def _do_backup(db_config: dict):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"/var/backups/wp_posts_naturalizer_{ts}.sql"
    cmd = ["mysqldump", "-u", db_config["user"], f"-p{db_config['password']}", db_config["database"], "wp_posts"]
    try:
        with open(path, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, check=True)
        print(f"💾 Backup guardado: {path}")
    except Exception as e:
        print(f"⚠️  Backup fallido: {e}. Continuando igualmente.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Naturalizer v4 — inforeparto.com / psicoprotego.es")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--post-id", nargs="+", type=int, metavar="ID", help="IDs de posts a naturalizar")
    group.add_argument("--modified-today", action="store_true", help="Procesar posts modificados hoy")
    parser.add_argument("--site", default="inforeparto", help="Sitio (inforeparto|psicoprotego)")
    parser.add_argument("--dry-run", action="store_true", help="Analizar sin guardar en DB")
    parser.add_argument("--backup", action="store_true", help="Backup de wp_posts antes de empezar")
    parser.add_argument("--verbose", action="store_true", help="Mostrar diff y métricas detalladas")
    parser.add_argument("--score-only", action="store_true", help="Solo calcular NaturalScore sin reescribir")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.score_only:
        print("❌ ANTHROPIC_API_KEY no definida. Ejecuta: source ~/.env.projects")
        sys.exit(1)

    try:
        db_config = _get_db_config(args.site)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if args.backup and not args.dry_run:
        _do_backup(db_config)

    conn = mysql.connector.connect(**db_config)

    if args.modified_today:
        post_ids = _get_modified_today_ids(args.site, conn)
        if not post_ids:
            print("ℹ️  No hay posts modificados hoy.")
            conn.close()
            return
        print(f"Posts modificados hoy: {post_ids}")
    else:
        post_ids = args.post_id

    if args.score_only:
        # Just compute NaturalScore for existing posts
        settings, patterns, _ = load_config()
        bad_openers = patterns.get("malas_aperturas", [])
        cur = conn.cursor()
        for pid in post_ids:
            cur.execute("SELECT post_title, post_content FROM wp_posts WHERE ID = %s", (pid,))
            row = cur.fetchone()
            if not row:
                print(f"Post {pid}: no encontrado")
                continue
            title, content = row
            sc = NaturalScorer.score(content, patterns, bad_openers)
            emoji = "✅" if sc["overall"] >= 70 else ("⚠️" if sc["overall"] >= 50 else "❌")
            print(f"[{pid}] {title[:50]} → {sc['overall']}/100 {emoji}")
            if args.verbose:
                print(f"  Burst:{sc['burstiness']} Lexical:{sc['lexical_diversity']} Patterns:{sc['pattern_penalty']}% ParaVar:{sc['paragraph_variance']} Opening:{sc['opening']}")
        cur.close()
        conn.close()
        return

    ok = 0
    fail = 0
    for pid in post_ids:
        success = _process_post(pid, site=args.site, dry_run=args.dry_run, verbose=args.verbose, conn=conn)
        if success:
            ok += 1
        else:
            fail += 1

    conn.close()
    print(f"\n{'─' * 50}")
    print(f"Completado: {ok} OK, {fail} fallidos, {len(post_ids)} total.")
    if args.dry_run:
        print("(DRY-RUN: nada fue guardado)")


if __name__ == "__main__":
    main()
