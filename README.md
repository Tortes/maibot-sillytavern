# MaiBot × SillyTavern (experimental MVP)

A safety-first bridge for **SillyTavern Chat Completion preset JSON** in MaiBot's replyer. Target: group-chat roleplay without replacing MaiBot Planner, memory, or tool pipeline.

**Status:** experimental alpha, not a full SillyTavern implementation. Offline tests pass; **live MaiBot integration remains unverified**.

## MVP supports

- Load ST Chat Completion JSON with `prompts` and `prompt_order`.
- Read V2 / flat exported character-card JSON.
- Respect order and enabled flags; expand a fixed subset of safe macros (char, user, description, personality, scenario, mesExamples).
- Inject an overlay through `maisaka.replyer.before_model_request` by appending to an **existing system Context Item**, preserving metadata, conversation history, images, and tool-related items.
- Bind one preset to an exact MaiBot **session_id**, disabled by default.
- Offline CLI preview, explicit compatibility warnings, and unit tests.

## Important limitations

This MVP **does not** preserve exact ST role boundaries or depth injection. User prompts are flattened into a system overlay. It does not implement worldbooks, regex execution, script processing, setvar/getvar, assistant prefill, sampler settings, PNG metadata extraction, or automatic group ID mapping. Unsupported macros skip the affected prompt with a warning.

## Preview locally

Run from repository root (Python 3.12+):

~~~bash
python -m st_bridge.cli preview resources/example-st-preset.json --character resources/example-character.json
python -m unittest discover -s tests -v
~~~

## Experimental MaiBot installation

Clone into your MaiBot `plugins/maibot-sillytavern` directory and load it using MaiBot WebUI. Enable `plugin.enabled` explicitly, then add a `bindings` entry for the **exact internal session_id**. Use `preset_file=example-st-preset.json` and `character_file=example-character.json` as a smoke test. Preset JSON and exported character JSON are read only from the plugin's `resources/` directory.

Before opening the bot to actual groups, inspect the outgoing prompt and verify injection once without changing the Planner. Use only trusted card files; the imported prompts must never be allowed to authorize tool execution.

## Development roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). Priorities: Golden tests vs. SillyTavern / DSH Preset Enhance, structured role/depth injection, lorebook matching, chat-group binding and debug UI.

## References

- [MaiBot](https://github.com/Mai-with-u/MaiBot) (host)
- [DSH Preset Enhance](https://github.com/bychv/dsh-preset-enhance) (inspiration)
- [MaiBot GroupPersona](https://github.com/beichen24a1/MaiBot-GroupPersona) (group binding inspiration)

All code in this repository is independently written. See LICENSE (MIT).