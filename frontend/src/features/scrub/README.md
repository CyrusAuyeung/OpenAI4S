# frontend/src/features/scrub

[中文说明](README_zh.md)

Credential-shaped substring redaction for user-visible strings. Port of app.js `publicText`, plus `publicModelId` for model ids and protocol names, where a credential prefix alone (`ark-code-latest`) is not a key.

## Files

| File | Responsibility |
| --- | --- |
| [`scrub.ts`](scrub.ts) | `publicText`; `publicModelId` (redacts a prefixed token only when it also looks random). |
| [`scrub.test.ts`](scrub.test.ts) | Bearer / key-shaped tokens / query redaction; ellipsis cap; model ids kept while real key shapes are still redacted. |
