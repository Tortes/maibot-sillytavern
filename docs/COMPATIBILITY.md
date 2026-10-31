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
- MaiBot request-tail prompts are excluded from depth counting when recognizable by known prefixes or same-second timestamps.
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
