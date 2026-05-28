"""Configuration management for ComfyUI Discord Rich Presence extension."""

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger("discord_rpc")

_EXTENSION_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_EXTENSION_DIR, "config.json")
_DEFAULT_CONFIG_PATH = os.path.join(_EXTENSION_DIR, "config_default.json")

_config = None
_rpc_manager = None  # Set by __init__.py after manager is created


def _load_defaults():
    """Load default configuration from config_default.json."""
    try:
        with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "enabled": True,
            "client_id": "1470194985893888167",
            "show_model_name": True,
            "show_queue_info": True,
            "show_node_name": False,
            "show_step_progress": True,
            "show_elapsed_time": True,
            "show_current_run_time": True,
            "custom_idle_text": "",
            "privacy_mode": False,
            "idle_update_interval": 15,
            "generating_update_interval": 5,
            "reconnect_interval": 15,
        }


def load_config():
    """Load configuration, merging user config over defaults."""
    global _config
    defaults = _load_defaults()

    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            defaults.update(user_config)
        except Exception as e:
            logger.warning(f"[Discord RPC] Failed to load config.json: {e}")

    _config = defaults
    return _config


def save_config(config_data):
    """Save configuration to config.json."""
    global _config
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        _config = config_data
    except Exception as e:
        logger.error(f"[Discord RPC] Failed to save config.json: {e}")
        raise


def get_config():
    """Get current configuration."""
    global _config
    if _config is None:
        load_config()
    return _config


def set_rpc_manager(manager):
    """Store reference to the RPC manager for status queries."""
    global _rpc_manager
    _rpc_manager = manager


def register_routes(app):
    """Register API routes for configuration and status."""

    async def handle_get_config(request):
        return web.json_response(get_config())

    async def handle_set_config(request):
        try:
            data = await request.json()
            current = get_config()
            current.update(data)
            save_config(current)

            # Apply runtime changes to the RPC manager
            if _rpc_manager is not None:
                _rpc_manager.apply_config(current)

            return web.json_response({"status": "ok"})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def handle_get_status(request):
        status = {
            "connected": False,
            "enabled": get_config().get("enabled", True),
        }
        if _rpc_manager is not None:
            status["connected"] = _rpc_manager.connected
        return web.json_response(status)

    app.router.add_get("/discord-rpc/config", handle_get_config)
    app.router.add_post("/discord-rpc/config", handle_set_config)
    app.router.add_get("/discord-rpc/status", handle_get_status)
