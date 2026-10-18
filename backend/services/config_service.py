"""
Config service — read/write application settings from config.json.
"""
import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'config.json')

# Also check working directory
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(os.getcwd(), 'config.json')

EXAMPLE_PATH = CONFIG_PATH.replace('config.json', 'config.example.json')

DEFAULT_CONFIG = {
    "port": 3003,
    "llm": {
        "enabled": False,
        "provider": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini"
    },
    "notification": {
        "enabled": False,
        "webhook_url": "",
        "events": ["selloff_large", "new_big_holder"]
    },
    "company": {
        "name": "",
        "ir_email": "",
        "logo_url": ""
    },
    "auto_fetch": {
        "enabled": False,
        "time": "17:30",
        "days": 90
    }
}


def load_config() -> dict:
    """Load config from file, with defaults. Auto-creates config.json from example if missing."""
    if not os.path.exists(CONFIG_PATH) and os.path.exists(EXAMPLE_PATH):
        import shutil
        try:
            shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
            logger.info(f"Created config.json from example")
        except Exception:
            pass
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # Merge with defaults
            merged = {**DEFAULT_CONFIG, **cfg}
            for k in ['llm', 'notification', 'company', 'auto_fetch']:
                merged[k] = {**DEFAULT_CONFIG[k], **(cfg.get(k, {}))}
            return merged
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    return dict(DEFAULT_CONFIG)


def save_config(new_config: dict) -> dict:
    """Save config to file. Returns merged config."""
    current = load_config()
    merged = _deep_merge(current, new_config)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
