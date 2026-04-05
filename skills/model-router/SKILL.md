---
name: model-router
description: Configuración de modelos de IA por tarea. Usar para optimizar coste y calidad asignando el modelo adecuado a cada paso del workflow.
---

# Model Router - inforeparto.com

## Concepto

No todas las tareas necesitan el mismo modelo. Investigar datos
requiere precisión (modelo potente). Formatear HTML es mecánico
(modelo barato). Esta skill define qué modelo usar en cada paso.

## Modelos disponibles

| Modelo | Coste | Uso ideal |
|---|---|---|
| claude-opus-4-20250514 | $$$$$ | Análisis legal, verificación de datos, decisiones complejas |
| claude-sonnet-4-20250514 | $$$ | Redacción, naturalización, SEO, investigación |
| claude-haiku-4-5-20251001 | $ | Formateo HTML, extracción de datos, tareas mecánicas |

## Asignación por tarea

### Workflow de creación de post (blog-post)

| Paso | Tarea | Modelo | Justificación |
|---|---|---|---|
| 1 | Investigación web | Claude Code (sesión) | Usa el modelo de la sesión activa |
| 2 | Redacción del post | sonnet | Buen balance creatividad/coste |
| 3 | Checklist SEO | haiku | Mecánico: contar keywords, verificar estructura |
| 4 | Buscar/subir imágenes | haiku | Solo queries a APIs y comandos bash |
| 5 | Enlaces de afiliado | haiku | Buscar ASINs y formatear URLs |
| 6 | Revisión legal | opus | Requiere razonamiento profundo sobre riesgos |
| 7 | Naturalización | sonnet | Creatividad para reescribir, no mecánico |
| 8 | Publicar en WP | haiku | Solo comandos wp-cli |

### Tareas sueltas

| Tarea | Modelo |
|---|---|
| Actualizar post existente (contenido) | sonnet |
| Corregir enlaces de afiliado (formato) | haiku |
| Auditar todos los posts (bulk) | haiku para scan, sonnet para análisis |
| Responder preguntas del usuario | Claude Code (sesión) |

## Implementación

Claude Code ejecuta la sesión con su modelo fijo. Para tareas
que se delegan a la API (naturalizer, legal review, etc.),
los scripts Python leen este config:

### Archivo de configuración

```json
// ~/projects/inforeparto/config/models.json
{
  "models": {
    "redaccion": "claude-sonnet-4-20250514",
    "legal_review": "claude-opus-4-20250514",
    "naturalizacion": "claude-sonnet-4-20250514",
    "seo_check": "claude-haiku-4-5-20251001",
    "formateo": "claude-haiku-4-5-20251001",
    "extraccion": "claude-haiku-4-5-20251001"
  },
  "fallback": "claude-sonnet-4-20250514",
  "max_tokens": {
    "redaccion": 4096,
    "legal_review": 2048,
    "naturalizacion": 4096,
    "seo_check": 1024,
    "formateo": 2048,
    "extraccion": 1024
  }
}
```

### Función helper para scripts Python

```python
import json
import os

def get_model(task: str) -> tuple[str, int]:
    """Devuelve (modelo, max_tokens) para una tarea."""
    config_path = os.path.expanduser(
        "~/projects/inforeparto/config/models.json"
    )
    try:
        with open(config_path) as f:
            config = json.load(f)
        model = config["models"].get(task, config["fallback"])
        tokens = config["max_tokens"].get(task, 2048)
        return model, tokens
    except FileNotFoundError:
        return "claude-sonnet-4-20250514", 2048
```

Uso en el naturalizer u otros scripts:

```python
from model_router import get_model

model, max_tokens = get_model("naturalizacion")
response = client.messages.create(
    model=model,
    max_tokens=max_tokens,
    ...
)
```

## Cuándo usar Opus

Opus es 5-10x más caro que Sonnet. Solo usarlo para:

- Revisión legal (riesgo real si falla)
- Verificación de datos numéricos críticos (salarios, leyes)
- Decisiones ambiguas que requieren matiz

NO usar Opus para:
- Redacción de posts (sonnet es suficiente)
- Naturalización (es reescritura creativa)
- Cualquier tarea mecánica

## Cuándo usar Haiku

Haiku es ~20x más barato que Sonnet. Usarlo para:

- Contar palabras, keywords, densidad
- Formatear HTML
- Extraer datos estructurados de texto
- Generar queries de búsqueda
- Verificar estructura (H2, H3, listas)
- Clasificar contenido por categoría

NO usar Haiku para:
- Redacción creativa
- Análisis legal
- Razonamiento complejo

## Estimación de coste por post

| Paso | Modelo | Tokens aprox | Coste aprox |
|---|---|---|---|
| Redacción | sonnet | ~6K output | ~$0.09 |
| Legal review | opus | ~2K output | ~$0.30 |
| Naturalización | sonnet | ~6K output | ~$0.09 |
| SEO check | haiku | ~1K output | ~$0.001 |
| Formateo | haiku | ~2K output | ~$0.002 |
| **Total por post** | | | **~$0.50** |

Sin router (todo sonnet): ~$0.30
Sin router (todo opus): ~$1.50
Con router optimizado: ~$0.50

El legal review con opus sube el coste pero reduce el riesgo.

## Reglas

- SIEMPRE consultar models.json antes de hacer llamadas API
- Si models.json no existe, usar sonnet como fallback
- El modelo de la sesión de Claude Code no se puede cambiar (es fijo)
- Solo afecta a scripts que llaman la API directamente
- Revisar costes mensualmente y ajustar si es necesario
