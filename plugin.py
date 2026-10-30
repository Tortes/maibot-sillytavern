"""MaiBot plugin adapter: safe ST preset overlay at before_model_request.

Requires an installed MaiBot SDK at runtime; CLI/tests do not import this file.
"""
from __future__ import annotations
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import Field
from maibot_sdk import HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import HookMode, HookOrder

try:
    from .st_bridge.preset import build_overlay, load_character, load_preset, safe_resource_path
except ImportError:  # standalone preview/test import
    from st_bridge.preset import build_overlay, load_character, load_preset, safe_resource_path

log = logging.getLogger("maibot.plugin.sillytavern")
RESOURCES = Path(__file__).resolve().parent / "resources"
TAG = "【SillyTavern Preset Overlay — experimental】"

class PluginSwitch(PluginConfigBase):
    enabled: bool = Field(default=False, description="显式启用实验性预设注入")
    config_version: str = Field(default="0.1.0")

class PresetBinding(PluginConfigBase):
    session_id: str = Field(default="", description="MaiBot 的 session_id，不是 QQ 群号")
    preset_file: str = Field(default="example-st-preset.json", description="resources/ 下 JSON 文件名")
    character_file: str = Field(default="example-character.json", description="resources/ 下角色 JSON 文件名；留空表示不用")
    user_name: str = Field(default="群友")
    char_name: str = Field(default="", description="可选：覆盖角色昵称")
    enabled: bool = Field(default=True)

class PresetBridgeConfig(PluginConfigBase):
    plugin: PluginSwitch = Field(default_factory=PluginSwitch)
    bindings: list[PresetBinding] = Field(default_factory=list, description="按精确 session_id 绑定预设")
    max_chars: int = Field(default=16000, ge=500, le=20000)

PresetBridgeConfig.model_rebuild()


def append_system_overlay(items: list[dict[str, Any]], text: str) -> list[dict[str, Any]] | None:
    """Only patch an existing system item so MaiBot's metadata/tools/history survive."""
    if not text:
        return None
    copied = deepcopy(items)
    for item in copied:
        if not isinstance(item, dict) or item.get("item_type") != "SystemMessageItem":
            continue
        parts = item.get("parts")
        if not isinstance(parts, list):
            continue
        if any(isinstance(part, dict) and TAG in str(part.get("text", "")) for part in parts):
            return None  # avoid duplicate on one request
        parts.append({"type": "text", "text": "\n\n" + TAG + "\n" + text})
        return copied
    return None


class SillyTavernBridgePlugin(MaiBotPlugin):
    config_model = PresetBridgeConfig

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="sillytavern_preset_overlay",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        timeout_ms=3000,
    )
    async def on_replyer_before_model_request(self, **kwargs: Any) -> dict[str, Any] | None:
        cfg = getattr(self, "config", None)
        if cfg is None or not bool(getattr(getattr(cfg, "plugin", None), "enabled", False)):
            return None
        sid = str(kwargs.get("session_id") or "")
        bindings = [b for b in getattr(cfg, "bindings", []) if b.enabled and str(b.session_id) == sid]
        if not sid or not bindings:
            return None
        binding = bindings[0]
        items = kwargs.get("items")
        if not isinstance(items, list):
            return None
        try:
            preset = load_preset(safe_resource_path(RESOURCES, binding.preset_file))
            character = load_character(safe_resource_path(RESOURCES, binding.character_file)) if binding.character_file else None
            preview = build_overlay(
                preset, character=character, user_name=binding.user_name,
                char_name=binding.char_name, max_chars=cfg.max_chars,
            )
            for warning in preview.warnings:
                log.warning("preset session=%s: %s", sid, warning)
            patched = append_system_overlay(items, preview.text)
            if patched is None:
                return None
            modified = dict(kwargs)
            modified["items"] = patched
            return {"action": "continue", "modified_kwargs": modified}
        except Exception as exc:
            log.warning("SillyTavern preset skipped for session=%s: %s", sid, exc)
            return None


def create_plugin() -> MaiBotPlugin:
    return SillyTavernBridgePlugin()
