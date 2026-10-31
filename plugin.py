"""MaiBot adapter for role-aware SillyTavern preset injection.

The plugin changes only the Replyer request Context Items. Planner, memories,
tool definitions, and MaiBot's own system identity remain host-owned.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import Field
from maibot_sdk import HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import HookMode, HookOrder

try:
    from .st_bridge.context import apply_compiled_preset, extract_history_macro_values
    from .st_bridge.preset import compile_preset, load_character, load_preset, safe_resource_path
except ImportError:
    from st_bridge.context import apply_compiled_preset, extract_history_macro_values
    from st_bridge.preset import compile_preset, load_character, load_preset, safe_resource_path

log = logging.getLogger("maibot.plugin.sillytavern")
RESOURCES = Path(__file__).resolve().parent / "resources"


class PluginSwitch(PluginConfigBase):
    enabled: bool = Field(default=False, description="显式启用实验性预设注入")
    config_version: str = Field(default="0.2.0")


class PresetBinding(PluginConfigBase):
    session_id: str = Field(default="", description="MaiBot 的精确 session_id，不是 QQ 群号")
    preset_file: str = Field(default="example-st-preset.json", description="resources/ 下 JSON 文件名")
    character_file: str = Field(default="example-character.json", description="resources/ 下角色 JSON 文件名；留空表示不用")
    user_name: str = Field(default="群友")
    char_name: str = Field(default="", description="可选：覆盖角色昵称")
    character_id: str = Field(default="", description="可选：选择 ST prompt_order 中的 character_id；留空时自动选择默认组")
    trigger: str = Field(default="normal", description="ST injection_trigger，本版本默认 normal")
    allow_assistant_prefill: bool = Field(default=False, description="仅在已验证模型支持 assistant 前缀续写后启用")
    enabled: bool = Field(default=True)


class PresetBridgeConfig(PluginConfigBase):
    plugin: PluginSwitch = Field(default_factory=PluginSwitch)
    bindings: list[PresetBinding] = Field(default_factory=list, description="按精确 session_id 绑定预设")
    max_chars: int = Field(default=16000, ge=500, le=20000)


PresetBridgeConfig.model_rebuild()


class SillyTavernBridgePlugin(MaiBotPlugin):
    config_model = PresetBridgeConfig

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="sillytavern_preset_bridge",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        timeout_ms=3000,
    )
    async def on_replyer_before_model_request(self, **kwargs: Any) -> dict[str, Any] | None:
        try:
            cfg = self.config
        except RuntimeError:
            log.debug("Plugin config is not injected yet; skipping preset hook")
            return None
        if not bool(getattr(getattr(cfg, "plugin", None), "enabled", False)):
            return None

        session_id = str(kwargs.get("session_id") or "")
        bindings = [
            binding for binding in getattr(cfg, "bindings", [])
            if binding.enabled and str(binding.session_id) == session_id
        ]
        if not session_id or not bindings:
            return None

        binding = bindings[0]
        raw_items = kwargs.get("items")
        if not isinstance(raw_items, list):
            return None

        try:
            preset_path = safe_resource_path(RESOURCES, binding.preset_file)
            preset = load_preset(preset_path)
            character = None
            if binding.character_file:
                character_path = safe_resource_path(RESOURCES, binding.character_file)
                character = load_character(character_path)

            compiled = compile_preset(
                preset,
                character=character,
                user_name=binding.user_name,
                char_name=binding.char_name,
                character_id=binding.character_id or None,
                trigger=binding.trigger,
                macro_values=extract_history_macro_values(raw_items),
                max_chars=cfg.max_chars,
            )
            reply_tool_args = kwargs.get("reply_tool_args")
            reply_tool_args = reply_tool_args if isinstance(reply_tool_args, dict) else {}
            applied = apply_compiled_preset(
                raw_items,
                compiled,
                allow_assistant_prefill=binding.allow_assistant_prefill,
                reply_reason=str(kwargs.get("reply_reason") or ""),
                reply_reference=str(reply_tool_args.get("reply_reference") or ""),
            )
            for warning in applied.warnings:
                log.warning("session=%s preset warning: %s", session_id, warning)
            if not applied.inserted:
                return None

            modified_kwargs = dict(kwargs)
            modified_kwargs["items"] = applied.items
            # item_schema_version is intentionally preserved from the host payload.
            return {"action": "continue", "modified_kwargs": modified_kwargs}
        except Exception:
            log.exception("SillyTavern preset compilation failed for session=%s; using host prompt", session_id)
            return None


def create_plugin() -> MaiBotPlugin:
    return SillyTavernBridgePlugin()
