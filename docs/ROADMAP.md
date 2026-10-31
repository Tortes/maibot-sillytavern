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

## v0.3 — real-world preset validation
- Differential Golden Test corpus against DSH Preset Enhance and SillyTavern.
- Validate MaiBot SDK manifest compatibility against a pinned MaiBot release.
- Improve request-tail detection and provider-specific role behavior.
- Add imported character PNG metadata extraction.

## v0.4 — character book / worldbook
- Character Book V2 parsing.
- Primary and secondary keyword activation.
- Selective scan depth, insertion order, budget, and recursive activation.
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
