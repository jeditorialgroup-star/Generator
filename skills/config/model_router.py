"""
Model Router - Helper para seleccionar el modelo correcto por tarea.

Uso:
    from model_router import get_model
    model, max_tokens = get_model("naturalizacion")
"""

import json
import os

CONFIG_PATH = os.path.expanduser(
    "~/projects/inforeparto/config/models.json"
)

FALLBACK_MODEL = "claude-sonnet-4-20250514"
FALLBACK_TOKENS = 2048


def get_model(task: str) -> tuple:
    """Devuelve (modelo, max_tokens) para una tarea."""
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        model = config["models"].get(task, config.get("fallback", FALLBACK_MODEL))
        tokens = config["max_tokens"].get(task, FALLBACK_TOKENS)
        return model, tokens
    except FileNotFoundError:
        return FALLBACK_MODEL, FALLBACK_TOKENS


def list_models() -> dict:
    """Listar todos los modelos configurados."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)["models"]
    except FileNotFoundError:
        return {"default": FALLBACK_MODEL}
