"""
sources.py — Capa 5b: Inyector de fuentes con enlaces
Busca fuentes autoritativas con Serper, las verifica con Jina Reader,
y pide a Claude Haiku que las integre de forma natural en el contenido.

Uso:
  from sources import SourceInjector
  injector = SourceInjector("inforeparto")
  content = injector.inject(content, title)
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
import mysql.connector

from naturalizer import _get_db_config
import anthropic

# ── API keys ──────────────────────────────────────────────────────────────────

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")

SERPER_URL = "https://google.serper.dev/search"
JINA_BASE = "https://r.jina.ai/"

# Cache TTL: 7 days
CACHE_TTL_DAYS = 7

# ── Priority domains by site ──────────────────────────────────────────────────

PRIORITY_DOMAINS = {
    "inforeparto": [
        "boe.es", "seg-social.es", "agenciatributaria.gob.es",
        "agenciatributaria.es", "mites.gob.es", "empleo.gob.es",
        "ine.es", "elconfidencial.com", "expansion.com",
        "xataka.com", "elpais.com", "elmundo.es",
    ],
    "psicoprotego": [
        "who.int", "cop.es", "boe.es", "comunidad.madrid",
        "mscbs.gob.es", "sanidad.gob.es", "fundacionmentalia.org",
        "elpais.com", "elmundo.es",
    ],
}

# ── Source injector system prompt ─────────────────────────────────────────────

_SOURCES_SYSTEM = """Eres el editor de {site_name}. Tu tarea es integrar 2-3 fuentes externas en el contenido HTML de forma completamente natural.

REGLAS:
1. Integra cada fuente como enlace dentro de texto ya existente — NO añadas frases nuevas vacías solo para el enlace.
2. Formato: <a href="URL" target="_blank" rel="nofollow noopener">texto ancla descriptivo</a>
3. El texto ancla debe ser descriptivo (nunca "haz clic aquí" ni "fuente").
4. Máximo 1 enlace por dominio.
5. No repitas dominios ya enlazados en el HTML.
6. Si una fuente no encaja de forma natural, omítela.
7. NO añadas párrafos nuevos, NO cambies el texto existente excepto para insertar el enlace.

Devuelve SOLO el HTML con los enlaces integrados, sin explicaciones."""


class SourceInjector:
    def __init__(self, site: str = "inforeparto"):
        self.site = site
        self._db_config = _get_db_config(site)
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._priority = PRIORITY_DOMAINS.get(site, [])

    def inject(self, content: str, title: str) -> tuple[str, list[dict]]:
        """
        Find sources and inject them into content.
        Returns (enriched_content, sources_list).
        If no sources found or API unavailable, returns original content.
        """
        if not SERPER_API_KEY:
            return content, []

        sources = self._find_sources(title)
        if not sources:
            return content, []

        enriched = self._inject_via_claude(content, title, sources)
        return enriched, sources

    def _find_sources(self, topic: str) -> list[dict]:
        """Search Serper for authoritative sources. Uses cache."""
        cache_key = hashlib.md5(f"{self.site}:{topic}".encode()).hexdigest()
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # Two searches: official sources + broader data search
        results = []
        # Classify topic: fiscal/legal → prioritize official domains; equipment/general → broaden
        fiscal_keywords = {"autónomo", "reta", "irpf", "iva", "modelo", "hacienda", "seguridad social",
                           "boe", "fiscal", "tributaria", "laboral", "ley rider", "cotización"}
        topic_lower = topic.lower()
        is_fiscal = any(kw in topic_lower for kw in fiscal_keywords)

        if is_fiscal:
            q1 = f"{topic} site:{' OR site:'.join(self._priority[:5])}"
        else:
            q1 = f"{topic} guía información España"
        queries = [
            q1,
            f"{topic} estadísticas datos informe 2025 2026 España",
        ]

        for query in queries:
            try:
                resp = requests.post(
                    SERPER_URL,
                    headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                    json={"q": query, "gl": "es", "hl": "es", "num": 5},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if not url:
                        continue
                    # Skip PDFs and non-useful formats
                    if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
                        continue
                    if not self._is_priority_domain(url) and is_fiscal:
                        continue
                    if any(r["url"] == url for r in results):
                        continue
                    results.append({
                        "url": url,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "domain": self._extract_domain(url),
                    })
                    if len(results) >= 5:
                        break
            except Exception:
                continue

        # Verify top 3 with Jina
        verified = []
        for source in results[:4]:
            if self._verify_url(source["url"]):
                verified.append(source)
            if len(verified) >= 3:
                break

        self._set_cache(cache_key, topic, verified)
        return verified

    def _verify_url(self, url: str) -> bool:
        """Quick verification via Jina Reader — just checks accessibility."""
        try:
            headers = {}
            if JINA_API_KEY:
                headers["Authorization"] = f"Bearer {JINA_API_KEY}"
            resp = requests.get(
                f"{JINA_BASE}{url}",
                headers=headers,
                timeout=8,
                allow_redirects=True,
            )
            return resp.status_code == 200 and len(resp.text) > 200
        except Exception:
            return False

    def _inject_via_claude(self, content: str, title: str, sources: list[dict]) -> str:
        """Ask Haiku to integrate sources naturally into the HTML."""
        if not sources:
            return content

        sources_text = "\n".join(
            f"- URL: {s['url']}\n  Descripción: {s['title']} — {s['snippet'][:120]}"
            for s in sources
        )

        site_name = self.site.capitalize()
        system = _SOURCES_SYSTEM.format(site_name=site_name)

        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8192,
                system=system,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Título del post: {title}\n\n"
                        f"FUENTES A INTEGRAR:\n{sources_text}\n\n"
                        f"HTML:\n{content}"
                    ),
                }],
            )
            result = resp.content[0].text.strip()
            # Strip code fences if Claude wrapped it
            if result.startswith("```"):
                nl = result.find("\n")
                if nl != -1:
                    result = result[nl + 1:]
                if result.endswith("```"):
                    result = result[:-3].rstrip()
            return result.strip()
        except Exception:
            return content

    def _is_priority_domain(self, url: str) -> bool:
        domain = self._extract_domain(url)
        return any(p in domain for p in self._priority)

    @staticmethod
    def _extract_domain(url: str) -> str:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        return match.group(1) if match else ""

    def _get_cache(self, cache_key: str) -> Optional[list]:
        try:
            conn = mysql.connector.connect(**self._db_config)
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT results FROM ir_source_cache WHERE query_hash = %s AND expires_at > NOW()",
                (cache_key,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return json.loads(row["results"])
        except Exception:
            pass
        return None

    def _set_cache(self, cache_key: str, query: str, results: list):
        try:
            expires = datetime.now() + timedelta(days=CACHE_TTL_DAYS)
            conn = mysql.connector.connect(**self._db_config)
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ir_source_cache (query_hash, query, site, results, expires_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE results = VALUES(results), expires_at = VALUES(expires_at)""",
                (cache_key, query, self.site, json.dumps(results, ensure_ascii=False), expires),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
