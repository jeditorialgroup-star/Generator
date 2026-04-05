"""
experience_db.py — Capa 4: ExperienceDB
Almacena y recupera fragmentos de experiencia real para inyectar en el contenido.

Uso:
  from experience_db import ExperienceDB
  db = ExperienceDB("inforeparto")
  experiences = db.get_for_topic("cuota autónomos RETA", limit=3)
"""

import json
import re
from typing import Optional
import mysql.connector

from naturalizer import _get_db_config


class ExperienceDB:
    TABLE = "ir_experience_bank"

    def __init__(self, site: str = "inforeparto"):
        self.site = site
        self._db_config = _get_db_config(site)

    def _connect(self):
        return mysql.connector.connect(**self._db_config)

    def get_for_topic(self, topic: str, limit: int = 3) -> list[dict]:
        """
        Retrieve relevant experiences for a topic using keyword matching on tags + topic field.
        Returns experiences sorted by success_score DESC.
        """
        keywords = self._extract_keywords(topic)
        if not keywords:
            return []

        conn = self._connect()
        cur = conn.cursor(dictionary=True)

        # Build keyword conditions for tag and topic matching
        conditions = []
        params = [self.site]
        for kw in keywords[:6]:
            conditions.append("(topic LIKE %s OR JSON_SEARCH(tags, 'one', %s) IS NOT NULL)")
            params.extend([f"%{kw}%", kw])

        if not conditions:
            cur.close()
            conn.close()
            return []

        sql = f"""
            SELECT id, type, content, tags, success_score, times_used
            FROM {self.TABLE}
            WHERE site = %s AND ({' OR '.join(conditions)})
            ORDER BY success_score DESC, times_used ASC
            LIMIT %s
        """
        params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()

        cur.close()
        conn.close()

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "type": row["type"],
                "content": row["content"],
                "tags": json.loads(row["tags"]) if isinstance(row["tags"], str) else (row["tags"] or []),
                "success_score": row["success_score"],
            })
        return result

    def mark_used(self, exp_ids: list[int]):
        """Update last_used and times_used for used experiences."""
        if not exp_ids:
            return
        conn = self._connect()
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(exp_ids))
        cur.execute(
            f"UPDATE {self.TABLE} SET times_used = times_used + 1, last_used = NOW() WHERE id IN ({placeholders})",
            exp_ids,
        )
        conn.commit()
        cur.close()
        conn.close()

    def update_success(self, exp_id: int, delta: float):
        """Adjust success_score by delta (positive = worked well, negative = didn't help)."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE {self.TABLE} SET success_score = GREATEST(0, LEAST(1, success_score + %s)) WHERE id = %s",
            (delta, exp_id),
        )
        conn.commit()
        cur.close()
        conn.close()

    def add(self, topic: str, exp_type: str, content: str, tags: list[str]) -> int:
        """Insert a new experience. Returns its ID."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {self.TABLE} (site, topic, type, content, tags) VALUES (%s, %s, %s, %s, %s)",
            (self.site, topic, exp_type, content, json.dumps(tags, ensure_ascii=False)),
        )
        exp_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        return exp_id

    def count(self) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {self.TABLE} WHERE site = %s", (self.site,))
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        return n

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from a topic string."""
        stopwords = {
            "para", "con", "por", "del", "los", "las", "una", "unos", "unas",
            "que", "como", "más", "muy", "sin", "sobre", "desde", "hasta",
            "cómo", "qué", "cuál", "cuáles", "guía", "completa", "todo",
        }
        words = re.findall(r"\b[a-záéíóúüñ]{4,}\b", text.lower())
        return [w for w in words if w not in stopwords]


def format_for_prompt(experiences: list[dict]) -> str:
    """Format experience list for inclusion in system prompt."""
    if not experiences:
        return ""
    lines = ["EXPERIENCIAS REALES DISPONIBLES (usar 1-2, de forma integrada y natural):"]
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
        lines.append(f'  [{type_label}] "{exp["content"]}"')
    return "\n".join(lines)
