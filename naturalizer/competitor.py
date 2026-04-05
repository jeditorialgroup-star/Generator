"""
competitor.py — Capa 6: Análisis Competitivo
Analiza el top 3 SERP para el topic del post y genera una recomendación
de diferenciación que se inyecta en el prompt principal.

Usa caché en MariaDB (TTL 7 días) para no repetir búsquedas costosas.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

import requests
import mysql.connector
import anthropic

from naturalizer import _get_db_config

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
SERPER_URL = "https://google.serper.dev/search"
JINA_BASE = "https://r.jina.ai/"

CACHE_TTL_DAYS = 7
JINA_EXTRACT_CHARS = 2000   # chars por competidor
MAX_COMPETITORS = 3

_ANALYSIS_SYSTEM = """Eres un analista SEO especializado en contenido para repartidores y riders en España.

Analiza los 3 primeros resultados de Google para un topic y compáralos con el post propio.
Genera una recomendación de diferenciación BREVE (máx 150 palabras) con este formato:

ÁNGULOS CUBIERTOS POR COMPETIDORES: [lista de 2-3 temas que tratan todos]
ÁNGULOS QUE ELLOS IGNORAN: [lista de 2-3 temas que podemos explotar]
RECOMENDACIÓN: [1-2 frases concretas sobre cómo diferenciarse]

Sé específico y práctico. No generalices."""


class CompetitorAnalyzer:
    def __init__(self, site: str = "inforeparto"):
        self.site = site
        self._db_config = _get_db_config(site)
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    def analyze(self, topic: str, own_content: str = "") -> Optional[str]:
        """
        Analyze top SERP competitors for topic.
        Returns a brief differentiation recommendation string, or None if unavailable.
        """
        if not SERPER_API_KEY:
            return None

        cache_key = "comp:" + hashlib.md5(f"{self.site}:{topic}".encode()).hexdigest()
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached.get("report")

        # Step 1: Serper top 3
        urls = self._serper_top3(topic)
        if not urls:
            return None

        # Step 2: Jina extract each
        competitor_texts = []
        for url in urls[:MAX_COMPETITORS]:
            text = self._jina_extract(url)
            if text:
                competitor_texts.append(f"URL: {url}\n{text}")

        if not competitor_texts:
            return None

        # Step 3: Haiku analysis
        report = self._haiku_analysis(topic, competitor_texts, own_content)
        if report:
            self._set_cache(cache_key, topic, {"report": report})
        return report

    def _serper_top3(self, topic: str) -> list[str]:
        try:
            resp = requests.post(
                SERPER_URL,
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": topic, "gl": "es", "hl": "es", "num": 5},
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            urls = []
            for item in data.get("organic", []):
                url = item.get("link", "")
                # Skip PDFs, aggregators, social
                if not url or url.lower().endswith(".pdf"):
                    continue
                if any(s in url for s in ["youtube.com", "twitter.com", "facebook.com", "amazon.es"]):
                    continue
                urls.append(url)
                if len(urls) >= MAX_COMPETITORS:
                    break
            return urls
        except Exception:
            return []

    def _jina_extract(self, url: str) -> Optional[str]:
        try:
            headers = {"Accept": "text/plain"}
            if JINA_API_KEY:
                headers["Authorization"] = f"Bearer {JINA_API_KEY}"
            resp = requests.get(
                f"{JINA_BASE}{url}",
                headers=headers,
                timeout=8,
            )
            if resp.status_code != 200 or len(resp.text) < 200:
                return None
            # Clean and trim
            text = re.sub(r"\s+", " ", resp.text)
            return text[:JINA_EXTRACT_CHARS]
        except Exception:
            return None

    def _haiku_analysis(self, topic: str, competitors: list[str], own: str) -> Optional[str]:
        try:
            comp_block = "\n\n---\n\n".join(competitors)
            own_excerpt = own[:1500] if own else "(no disponible)"
            resp = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=_ANALYSIS_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": (
                        f"TOPIC: {topic}\n\n"
                        f"COMPETIDORES:\n{comp_block}\n\n"
                        f"NUESTRO POST (extracto):\n{own_excerpt}"
                    ),
                }],
            )
            return resp.content[0].text.strip()
        except Exception:
            return None

    def _get_cache(self, cache_key: str) -> Optional[dict]:
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

    def _set_cache(self, cache_key: str, query: str, data: dict):
        try:
            expires = datetime.now() + timedelta(days=CACHE_TTL_DAYS)
            conn = mysql.connector.connect(**self._db_config)
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO ir_source_cache (query_hash, query, site, results, expires_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE results = VALUES(results), expires_at = VALUES(expires_at)""",
                (cache_key, query, self.site, json.dumps(data, ensure_ascii=False), expires),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
