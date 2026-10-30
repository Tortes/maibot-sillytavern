# Scope and compatibility roadmap

## v0.1 (this scaffold)
- Source JSON / wrapper validation, ordered overlay, known marker mapping.
- Exact MaiBot session binding, disabled by default.
- No implicit group wide changes.

## v0.2
- Exact ST preset message order & depth semantics with Golden Test fixtures.
- Requests that preserve MaiBot tool-call/result and required replyer constraints.
- Read-only final prompt debug snapshots, private by default.

## v0.3
- Character Card V2/V3 PNG + JSON, ST worldbook keyword matching.
- Per chat group binding & relation data connection.

## Compatibility matrix
| Feature | v0.1 |
|---|---|
| ST preset JSON prompts | Partial (text overlay) |
| prompt_order | Enabled/order honored |
| chatHistory marker | MaiBot history preserved |
| charDescription marker | Basic JSON supported |
| Macro char/user | Supported |
| setvar/getvar | Skipped with warning |
| Depth injection | Not supported |
| Assistant prefill | Not supported |
| Regex | Not executed |
| Worldbook / character_book | Detected, not executed |
| JavaScript | Never executed |
