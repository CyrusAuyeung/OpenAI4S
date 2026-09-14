# frontend/src/features/messages

[中文说明](README_zh.md)

F-10 message stream. Framed history paint (40 rows per rAF + one fragment), dual-node streaming markdown (sealed prefix + live tail), tool output `textNode.appendData(delta)`, follow-scroll coalesced on rAF. 1MB live-output cap is F-08 `appendLiveOutput`; this lane only turns it into a delta. Window names (`openConversation`, `fetch*Messages`, `down`) are assigned here, not left as F-05 stubs.

## Files

| File | Responsibility |
| --- | --- |
| [`copy.ts`](copy.ts) | Source-owned bilingual history-recovery text; generated locale extracts stay unchanged. |
| [`components.tsx`](components.tsx) | `MessageList` (`#messages` / `#jump-pill`), accessible history status/retry outside the message host, and `StreamingPre`. |
| [`cut.ts`](cut.ts) | Incremental `_mdStableCut` / `mdStableCut` (app.js:5378-5402). |
| [`cut.test.ts`](cut.test.ts) | Incremental scan matches the original from-scratch cut; fence / 120-char tail. |
| [`delta.ts`](delta.ts) | `liveOutputDelta`, `bindStreamingPre` (`appendData`), `toolMetaLabel`. |
| [`delta.test.ts`](delta.test.ts) | 1MB truncation idempotent; newlines counted on the increment only. |
| [`dom.ts`](dom.ts) | `$` / `el` / `#messages` / `ensureMessageDom`. |
| [`fetch.ts`](fetch.ts) | `fetchRecentMessages` / `fetchOlderMessages` / `fetchAllMessages` (6926-6961). |
| [`handlers.ts`](handlers.ts) | `text_reset` / `text_chunk` WS handlers. |
| [`handlers.test.ts`](handlers.test.ts) | mine / stale-turn guards; idempotent register. |
| [`identity.ts`](identity.ts) | Candidate identity + `storedCandidateOwnsChunk` at the feed boundary. |
| [`index.ts`](index.ts) | Public exports; `installMessages` assigns window names via `isReady`. |
| [`install.test.ts`](install.test.ts) | Contract names are real (`isReady`), not F-05 stubs. |
| [`list.ts`](list.ts) | `renderStored`, `insertMessageByTime`, framed batch paint. |
| [`list.test.ts`](list.test.ts) | 640 rows → 16 frames of 40; insert-by-time skips `#msgs-earlier`. |
| [`messages.css`](messages.css) | `.md-sealed` / `.md-tail { display: contents }`; the stopped-turn marker and stopped card (muted glyph, neutral bar). |
| [`open.ts`](open.ts) | `openConversation` / `recoverConversation`: generation-scoped read results, GET-only retries, confirmed-history retention and atomic framed paint. |
| [`open.test.ts`](open.test.ts) | Generation-scoped history failures, GET-only recovery, REST/WS races and retained older pages. |
| [`raf.ts`](raf.ts) | Shared `requestAnimationFrame` / setTimeout fallback. |
| [`scroll.ts`](scroll.ts) | `down` / `updateJumpPill` on one rAF; throttled scroll listener. |
| [`stopped.ts`](stopped.ts) | The stopped-turn marker: a `text_chunk` or stored row carrying `cancelled` renders as one marker (feature-local copy), the still-running activity card is marked stopped (stop glyph instead of the success check, and the generated "Running analysis · cell N" title becomes "Analysis · cell N"), and a `cancelled` terminal whose chunk was missed gets the same marker. |
| [`stopped.test.ts`](stopped.test.ts) | Live marker instead of prose, stopped card (glyph, generated title replaced, the cell's own title kept) vs. a card that finished first, terminal fallback without duplicates, reopen via both stored renderers, malformed metadata stays prose. |
| [`stream.ts`](stream.ts) | `feed` / `flushRender` / `scheduleRender` / `startStream` / `sealText`. |
