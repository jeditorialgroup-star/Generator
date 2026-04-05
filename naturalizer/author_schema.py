"""
author_schema.py — Capa 6b: Schema de Autor y Señales E-E-A-T
Inyecta byline y JSON-LD Organization schema en el post HTML.

Solo actúa si el post no tiene ya estos elementos.
Los bloques <script type="application/ld+json"> están protegidos del naturalizer
(no se tocan durante las capas 1-5b), pero este módulo los añade ANTES de
que el contenido sea publicado.
"""

import json
import re

# ── Author configs by site ─────────────────────────────────────────────────────

AUTHOR_CONFIG = {
    "inforeparto": {
        "name": "Equipo de Inforeparto",
        "url": "https://inforeparto.com/sobre-nosotros/",
        "org_name": "Inforeparto",
        "org_url": "https://inforeparto.com",
        "knows_about": [
            "legislación laboral riders España",
            "RETA cotización autónomos",
            "plataformas delivery Glovo Uber Eats Just Eat",
            "Ley Rider Real Decreto-ley 9/2021",
            "fiscalidad autónomos España",
            "equipamiento seguridad ciclistas motoristas",
        ],
        "byline_class": "firma-inforeparto",
        "byline_template": '<p class="firma-inforeparto" style="font-size:0.85em;color:#666;margin-top:2em;border-top:1px solid #eee;padding-top:0.8em">Elaborado por el <strong>Equipo de Inforeparto</strong> · Actualizado el {date}</p>',
    },
    "psicoprotego": {
        "name": "Equipo de Psicoprotego",
        "url": "https://psicoprotego.es/sobre-nosotros/",
        "org_name": "Psicoprotego",
        "org_url": "https://psicoprotego.es",
        "knows_about": [
            "psicología clínica",
            "terapia EMDR",
            "salud mental adolescentes",
            "psicología Pozuelo de Alarcón Madrid",
        ],
        "byline_class": "firma-psicoprotego",
        "byline_template": '<p class="firma-psicoprotego" style="font-size:0.85em;color:#555;margin-top:2em;border-top:1px solid #eee;padding-top:0.8em">Elaborado por el <strong>Equipo de Psicoprotego</strong> · Actualizado el {date}</p>',
    },
}

# ── Schema builder ─────────────────────────────────────────────────────────────

def _build_org_schema(cfg: dict, post_title: str, post_url: str = "") -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": cfg["org_name"],
        "url": cfg["org_url"],
        "knowsAbout": cfg["knows_about"],
    }
    return (
        '<script type="application/ld+json" class="schema-author-inforeparto">\n'
        + json.dumps(schema, ensure_ascii=False, indent=2)
        + "\n</script>"
    )


def _has_byline(content: str, byline_class: str) -> bool:
    return f'class="{byline_class}"' in content or f"class='{byline_class}'" in content


def _has_author_schema(content: str, org_name: str) -> bool:
    return f'"name": "{org_name}"' in content or f'"name":"{org_name}"' in content


# ── Public API ─────────────────────────────────────────────────────────────────

def inject_author_signals(
    content: str,
    site: str = "inforeparto",
    post_title: str = "",
    post_url: str = "",
    post_date: str = "",
) -> tuple[str, bool]:
    """
    Inject byline and Organization schema if not already present.
    Returns (modified_content, was_modified).
    """
    cfg = AUTHOR_CONFIG.get(site)
    if not cfg:
        return content, False

    from datetime import date
    date_str = post_date or date.today().strftime("%d/%m/%Y")

    modified = False

    # 1. Byline: add before the last </p> or at end
    if not _has_byline(content, cfg["byline_class"]):
        byline = cfg["byline_template"].format(date=date_str)
        # Insert before closing </div> or at end of content
        if "</article>" in content.lower():
            content = re.sub(r"</article>", byline + "</article>", content, count=1, flags=re.IGNORECASE)
        elif content.rstrip().endswith("</p>"):
            content = content.rstrip() + "\n" + byline
        else:
            content = content + "\n" + byline
        modified = True

    # 2. Organization schema: append if not present
    if not _has_author_schema(content, cfg["org_name"]):
        schema_block = _build_org_schema(cfg, post_title, post_url)
        content = content + "\n" + schema_block
        modified = True

    return content, modified
