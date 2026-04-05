#!/usr/bin/env python3
"""
Model Router — inforeparto.com
Selecciona proveedor y modelo según la tarea. Lee config desde models.json.
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "models.json"


def get_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_model(task: str) -> dict:
    """
    Devuelve config completa para una tarea:
    {provider, model, max_tokens, api_key, base_url}
    """
    config = get_config()
    task_config = config["models"].get(task, config["fallback"])
    provider_name = task_config["provider"]
    provider = config["providers"][provider_name]

    api_key = os.environ.get(provider["env_key"], "")
    if not api_key:
        # Fallback a Anthropic si no hay key del proveedor
        fallback = config["fallback"]
        provider_name = fallback["provider"]
        provider = config["providers"][provider_name]
        api_key = os.environ.get(provider["env_key"], "")
        return {
            "provider": provider_name,
            "model": fallback["model"],
            "max_tokens": fallback["max_tokens"],
            "api_key": api_key,
            "base_url": provider["base_url"],
        }

    return {
        "provider": provider_name,
        "model": task_config["model"],
        "max_tokens": task_config["max_tokens"],
        "api_key": api_key,
        "base_url": provider["base_url"],
    }


def call_model(task: str, system: str, user: str) -> str:
    """
    Llama al modelo asignado para la tarea y devuelve el texto de respuesta.
    Soporta: anthropic, deepseek (compatible OpenAI), gemini.
    """
    cfg = get_model(task)
    provider = cfg["provider"]

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=cfg["api_key"])
        response = client.messages.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    elif provider == "deepseek":
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        response = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content

    elif provider == "gemini":
        from google import genai
        client = genai.Client(api_key=cfg["api_key"])
        response = client.models.generate_content(
            model=cfg["model"],
            contents=f"{system}\n\n{user}",
        )
        return response.text

    elif provider == "cohere":
        import cohere
        client = cohere.ClientV2(api_key=cfg["api_key"])
        response = client.chat(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.message.content[0].text

    elif provider in ("deepseek", "grok", "together"):
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        response = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=cfg["max_tokens"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content

    else:
        raise ValueError(f"Proveedor desconocido: {provider}")


if __name__ == "__main__":
    # Test rápido
    for task in ["naturalizacion", "formateo", "seo_check"]:
        cfg = get_model(task)
        print(f"{task:20} → {cfg['provider']:12} / {cfg['model']} (key: {'✅' if cfg['api_key'] else '❌ MISSING'})")
