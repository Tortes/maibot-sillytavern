# SillyTavern compatibility matrix

The bridge targets SillyTavern Chat Completion preset JSON. The implementation is a safe subset, not a full runtime.

## Preset fields

| Field / behavior | v0.2 | Notes |
|---|---|---|
| prompts | Supported | Up to 2,000 entries |
| prompt_order | Supported | Select explicit character_id, else global 100001, else first group |
| enabled | Supported | prompt_order entry is authoritative when present |
| role: system/user/assistant/model | Supported | model maps to MaiBot AssistantMessageItem |
| chatHistory marker | Supported | Before/after boundary |
| injection_position 0 | Supported | Before or after host history according to chatHistory marker |
| injection_position 1 | Supported | Insert into host history by item depth |
| injection_depth | Supported | Counted over MaiBot Context Items, not reconstructed ST messages |
| injection_order | Supported | Orders depth entries at a shared insertion point |
| injection_trigger | Partial | Exact string match against configured binding trigger; default normal |
| assistant_prefill | Opt-in | Disabled by default; emits an AssistantMessageItem at request end |
| marker: charDescription | Supported | From character JSON description |
| marker: charPersonality | Supported | From character JSON personality |
| marker: scenario | Supported | From character JSON scenario |
| marker: dialogueExamples | Supported | From character JSON mes_example |
| arbitrary marker IDs | Partial | Can be supplied through compiler API, not yet exposed in plugin config |
| DSH Preset Enhance share wrapper | Supported | Reads nested preset.data |
| prompt scripts / JavaScript / EJS | Not supported | Never executed |

## World Info / Lorebook fields (v0.3)

| Field / behavior | v0.3 | Notes |
|---|---|---|
| Standalone World Info JSON | Supported | `entries` may be an object keyed by UID or an array |
| Embedded V2 `character_book` | Supported | Automatically loaded from the character card when enabled |
| Primary keywords `key` | Supported | OR matching; plain text only |
| Secondary keywords `keysecondary` | Supported | `selectiveLogic` 0–3 (AND ANY / NOT ALL / NOT ANY / AND ALL) |
| Constant / disabled | Supported | `constant=true` always activates; `disable=true` suppresses |
| Scan depth | Supported | Per-entry `scanDepth`, then book `scanDepth`, then binding default |
| Case-sensitive / whole-word | Supported | Entry overrides book/binding defaults; whole-word is ASCII-boundary based |
| Probability | Supported | Only applied when `useProbability=true` |
| Recursive activation | Partial | Bounded per book; supports `recursiveScanning`, `delayUntilRecursion`, `excludeRecursion`, `preventRecursion` |
| Character description/personality/scenario scan | Partial | Supports the corresponding per-entry match flags |
| Position 0 / 1 | Supported | Before / after character definitions, approximated within the pre-history prompt block |
| Position 4 (depth) | Supported | Maps role 0/1/2 to System/User/Assistant; depth is counted over MaiBot Context Items |
| Character-card embedded book + external book | Supported | Both are loaded; each book is scanned independently |

Not implemented: regex keyword evaluation (skipped for ReDoS safety), imported scripts/decorators, vectorized activation, inclusion-group scoring, sticky/cooldown/delay timed effects, min activations, Author's Note positions 2/3, Example Message positions 5/6, outlet position 7, persona-description / character-depth / creator-notes scanning, character filters, and cross-book recursive activation. Entries that depend on unsupported filters, timed effects, decorators, or scan sources are skipped with a warning rather than silently treated as ordinary keyword entries. `ignoreBudget` is also not honored; the normal character budget still applies.

The Worldbook budget is a **character** limit (`worldbook_max_chars`), not ST's tokenizer-based token budget. The scan buffer contains recent textual UserMessageItem and AssistantMessageItem content, including the current user message when present; it excludes recognized MaiBot-generated request-tail prompts and does not scan image payloads or tool protocol items. The default scan depth is 2. Recursive activation is off by default. An explicit book-level `recursiveScanning` value takes precedence; otherwise the binding setting is used. Recursion is capped at 5 passes.

## Macro subset

| Macro | Behavior |
|---|---|
| char | Character name |
| user | Configured user name |
| description | Character description |
| personality | Character personality |
| scenario | Character scenario |
| mesExamples | Character example dialogue |
| lastMessage | Last non-tail textual context item |
| lastUserMessage | Last user context item |
| lastCharMessage | Last assistant context item |
| newline | Newline |
| noop | Empty string |

Any unknown macro causes the affected prompt entry to be skipped with a warning. This is intentional: sending control macros literally can produce confusing or unsafe prompts.

Not supported: local/global variable mutation, random/pick/roll, regex capture macros, dynamic template API, DSH-specific macros, recursive macro evaluation, and arbitrary JavaScript.

## MaiBot Context Item mapping

- Existing leading SystemMessageItems remain first and are not rewritten.
- Before-history prompts are inserted after the leading system block.
- After-history prompts are inserted immediately before the current-time final UserMessageItem when detected; otherwise they are appended.
- Depth prompts are inserted relative to existing history Context Items.
- MaiBot request-tail prompts are excluded from depth counting when recognizable by known text prefixes or explicit reply-reason/reference values.
- A depth insertion that would split a tool-call logical turn is moved before that turn.
- New items use unique item IDs, null logical_turn_id, ISO timestamps, and ordinary text parts.
- Existing item payloads are copied without changing content; MaiBot can match unchanged snapshots and preserve provider replay fragments.

This adapter depends on MaiBot's current Replyer request shape. If MaiBot changes the final-user marker or Context Item schema, depth and after-history placement must be revalidated.

## Explicitly not equivalent to SillyTavern yet

- MaiBot builds a final request-tail user message containing the current time, target message, Planner reason, and output instruction. SillyTavern generally treats the whole chat transcript as chatHistory. The bridge cannot reconstruct a perfect 1:1 transcript from the current hook payload.
- MaiBot's history is Context Items, which may include multimodal parts and tool protocol items; it is not identical to a flat ST chat log.
- Prompt regex scripts, depth-targeted regex processing, and arbitrary worldbook scripts are not run.
- Provider-specific role ordering and assistant-prefix continuation vary. Test the selected model provider before enabling assistant prefill.

## Test strategy

The unit tests cover deterministic ordering, role preservation, depth placement, tool-turn closure, session binding, and resource validation. They are not yet a byte-for-byte differential test against a running SillyTavern or DSH Preset Enhance compiler. A future golden corpus should store:
1. Source preset and card JSON.
2. A normalized source chat history.
3. Expected DSH Preset Enhance compiled message list.
4. MaiBot adapter output and documented host-specific differences.
