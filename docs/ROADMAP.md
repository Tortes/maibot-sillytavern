# Scope and compatibility roadmap

## v0.1 — initial overlay scaffold
- Basic ST Chat Completion JSON loading.
- Exact session binding.
- Safe text overlay and offline preview.

## v0.2 — structured preset engine (current branch)
- Role-aware System/User/Assistant Context Item insertion.
- chatHistory before/after boundary.
- injection_position, injection_depth, injection_order.
- Basic macro expansion and character_id selection.
- Tool-call logical-turn closure for depth insertion.
- Assistant prefill behind an explicit per-binding opt-in.
- Compatibility matrix and expanded offline tests.

## v0.3 — bounded World Info / Lorebook import (current)
- Standalone SillyTavern World Info JSON import.
- Embedded V2 character_book import.
- Primary/secondary keyword activation, constant/disabled entries, scan depth, matching options, probability.
- Bounded recursive activation and before/after/depth placement.
- CLI preview and offline fixtures.

## v0.4 — compatibility and runtime validation
- Differential Golden Test corpus against DSH Preset Enhance and SillyTavern.
- Validate MaiBot SDK manifest compatibility against pinned MaiBot releases.
- Live MaiBot/provider tests and provider-specific role behavior.
- Character PNG metadata extraction.
- Consider timed effects, inclusion-group scoring, and additional ST insertion positions.
- Per-session worldbook state and explicit security limits.

## v0.5 — multi-chat operations
- Map platform group identity to MaiBot session_id using supported host APIs.
- Per-chat character / preset binding UI.
- Prompt inspection and structured diagnostics in WebUI.
- Safe import/export and configuration migration.

## Deferred
- Arbitrary Tavern JavaScript, EJS, and script execution (not planned).
- Full sampler UI (MaiBot model provider owns generation parameters).
- Complete regex compatibility (only after a safe, bounded design and fixtures exist).
- DSH tool controls and DSML (not applicable to MaiBot's tool runtime).
