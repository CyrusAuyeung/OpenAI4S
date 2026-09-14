# Next improvements — 2026-09-14 / next 分支改进记录

This ledger covers the approved sequential T0–T9 plan, starting at
`8127907657d21a4cbb514bd1c21096801fd6cf6a`. It does not change the version,
schema, release policy or `main`. Each implementation is reviewed and validated
before pushing `next`; the following item waits for that commit's CI.

本记录跟踪本轮 T0–T9 顺序执行。原有 `TODO_zh.md` 与
`next-version-progress.md` 的未提交修改保留在工作区，不纳入本轮提交。
验证凭据只由进程环境或继承管道提供，不进入交付代码、保留日志或 Git。

| Stage / 阶段 | Status / 状态 | Evidence / 证据 |
|---|---|---|
| T0 Baseline / 基线 | Completed / 完成 | Locked Python 3.12 science + chemistry, frontend and three Playwright browsers installed; 90 LLM baseline tests passed. Baseline [CI 34819967908](https://github.com/PKU-YuanGroup/OpenAI4S/actions/runs/34819967908) succeeded at the starting SHA. |
| T1 P0-01 Retry and compatibility / 重试与降级 | Completed / 完成 | Shared three-send state, one compatibility POST, structured stream refusal only, cancellation before sends, semantic replay veto. Initial regression run reproduced 11 failures. Independent review passed after five findings were fixed; 144 targeted tests passed. |
| T2 P0-03 Editing / 编辑保护 | Completed / 完成 | Conditional writes, immutable editor baseline, bounded recoverable drafts and read-only reconciliation; backend, frontend and dist together. |
| T3 P0-02 Resource bounds / 资源边界 | Completed / 完成 | Shared total deadline, bounded input, backpressure and original usage evidence; independent review passed. |
| T4 P1-01 Files | Local validation passed; CI pending / 本地验收通过，待 CI | Shared owned filtering, pagination and refresh; 705 frontend tests passed. |
| T5 P1-03 Navigation / 导航 | Not started / 未开始 | Navigation identity and request generations. |
| T6 P1-02 Provenance and export / 溯源与导出 | Not started / 未开始 | Honest read states, validated responses and fixed version identity. |
| T7 P2-01 Snapshot design / 快照准备 | Not started / 未开始 | Design and acceptance only; no migration changes. |
| T8 P2-02 Slow connection design / 慢连接准备 | Not started / 未开始 | Design and acceptance only; no new runtime quotas. |
| T9 Final validation / 最终验收 | Not started / 未开始 | Final SHA gates, package and real Ark evidence. |

## Live Ark evidence / Ark 实测

Endpoint: `https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`.
Requested model: `doubao-seed-2.0-pro`. Values below are provider-returned usage,
not zero-filled estimates; missing usage is recorded as unknown.

| Stage / 阶段 | Request ID / 请求编号 | Returned model / 返回模型 | Time / 耗时 | Terminal / 终态 | Raw usage / 实际用量 |
|---|---|---|---|---|---|
| T0 short text | `021789376424524e2e425e7482a92db97bab17cb602abe8d89403` | `doubao-seed-2-1-turbo-260628` | 4.045 s | HTTP 200, stop | prompt 53; completion 24 (reasoning 21); total 77; cached 0 |
| T1 streaming text | `02178937694642171d94858e1bfbff6308a33b0bd3e33b8ea50f2` | `doubao-seed-2-1-turbo-260628` | 1.811 s | HTTP 200, stop; 3 deltas | prompt 53; completion 34 (reasoning 31); total 87; cached 0 |
| T1 native tool | `021789376948232c5962d2ff0c11c118c6b5d934e5fbaa186dcb7` | `doubao-seed-2-1-turbo-260628` | 5.032 s | HTTP 200, tool_calls; echo_value(value=7) | prompt 406; completion 88 (reasoning 55); total 494; cached 0 |
| T2 named-session artifact | `021789384515327427deff93a3e6360e32202b6d931cb308af2bf` | `doubao-seed-2-1-turbo-260628` | 6.816 s | HTTP 200, stop; one call; agent completed | prompt 15,648; completion 150 (reasoning 66); total 15,798; cached 2,360 |
| T3 initial streaming probe | `021789389419432fb9ad9ccefd1cf94f2af1554e5d9f81220d9f6` | `doubao-seed-2-1-turbo-260628` | 90.003 s | HTTP 200, deadline; no completed usage | Unknown / 未知 |

| T3 visible-delta Stop / 可见文本后停止 | `021789389644031a94a092d6e1517e56ac52cca715566be31a51a` | `doubao-seed-2-1-turbo-260628` | 4.092 s | HTTP 200, stop | prompt 57; completion 42 (reasoning 33); total 99; cached 0 |
| T3 next-call recovery / 下一调用恢复 | `021789389648026bfe35b6525b6a24c7ddbea7b420bd558f419dd` | `doubao-seed-2-1-turbo-260628` | 4.572 s | HTTP 200, stop | prompt 51; completion 24 (reasoning 23); total 75; cached 0 |
| T3 browser recovery tool 1 | `02178939012235529a69b00e37f9b7feeeb938de1ddf732b07129` | `doubao-seed-2-1-turbo-260628` | 6.164 s | HTTP 200, tool_calls | prompt 15,805; completion 84 (reasoning 26); total 15,889; cached 2,360 |
| T3 browser recovery tool 2 | `0217893901286014ab1b857f955f8c19d0609a2b480a31ea5d9e7` | `doubao-seed-2-1-turbo-260628` | 4.939 s | HTTP 200, tool_calls | prompt 15,911; completion 79 (reasoning 19); total 15,990; cached 15,672 |

The gateway returned a different model ID than requested; both are retained.
端点返回的模型编号与请求模型不同，记录保留两者，不假定它们相同。

## T1 validation / T1 验证

- Full offline suite through `capture_response_schemas.py --check`: **8,850
  passed, 25 skipped**, 1,165 captured route/status shapes, 212/212 routes,
  no breaking shape drift. `/kernel/packages` had an additive environment
  shape observation in this local environment; this item does not change that route or regenerate its contract.
- Full pre-commit (including mypy) passed in a complete candidate copy that
  excludes the two pre-existing document edits. Directory documentation and
  source secret scan passed. The PR harness passed all 38 scenarios.
- Skills installer: 16 selftests passed; npm pack verified 2,283 files and
  604 Skills (6.5 MB).
- Additional explicit kernel/agent/gateway regression: 254 passed and one
  15-second first-cell timeout under `--dist load`. The failed test,
  `test_kernel_survives_the_request_thread_that_created_it`, does not invoke
  the LLM and passed alone in 14.30 seconds (14.12-second test body). The full
  suite above used CI's `--dist loadfile` and already passed this test.
  The same 255 tests then passed together using CI's `--dist loadfile`
  (434.39 seconds). The timeout's cause was not proven by the available log.
  No kernel timeout or production behavior was changed to hide the result.
- Commit `c2cb02dde4f8752861fb1a093c73db9c986965e0` passed all 25 applicable jobs in [CI 34830046563](https://github.com/PKU-YuanGroup/OpenAI4S/actions/runs/34830046563). Temporary detailed
  logs are in `/private/tmp/openai4s-next-improvements-20260914`; this ledger
  retains the non-secret results for repository readers.

完整离线套件与 schema 门禁、独立复核、静态检查及 Ark 实测均已完成。
额外并行核心回归出现一次首次 Cell 的 15 秒超时；该用例不经过模型调用，
单独重跑通过，同一组 255 项按 CI 分配方式重跑也全部通过。保留这次观察，
不放宽超时或改动内核来消除测试结果。本项提交的 25 项适用 CI 门禁已全部通过。

## T2 validation / T2 验证

- Loading disables Save both in the DOM and callback. Saves compare the expected
  head inside the existing execution/write locks, before unchanged-content or
  snapshot handling. One of two writers sharing the same baseline succeeds;
  a conflict changes no bytes, versions or events. Omitted versions retain the
  legacy API behavior; explicit invalid values fail with 400.
- Editor baselines are immutable, checksum-verified version reads. Drafts retain
  original and modified text within 10 entries / 8 MiB, survive in-page refresh
  and navigation, and remain accessible after source deletion. Unknown save
  results trigger reads only, without replay or an unsupported success claim.
  Browser reload is guarded: cancelling it retains page memory; accepting it
  destroys memory, as documented. Historical tabs remain read-only.
- Independent read-only review passed after five findings were fixed: clipboard
  fallback, freeing draft capacity, missing historical snapshots, nullable old
  metadata and recovering drafts whose source was deleted. A second independent
  evidence audit found no remaining substantive acceptance gap.
- Backend targeted tests: **56 passed**, plus a real HTTP 400/409 projection test.
  Frontend: **690 passed** across 75 files; typecheck and production build passed.
  The full Chromium/Firefox/WebKit matrix passed **33/33** checks. Both original
  and final real Ark artifacts passed the conditional-editor scenarios in all
  three engines, including a response lost after the server committed the save.
- Final full offline suite and schema check: **8,878 passed, 26 skipped** in
  814.15 seconds, **1,167** captured route/status shapes and **212/212** routes,
  without breaking drift. Two newly covered PUT/PATCH edit success shapes were
  then captured with the existing recorder from real route tests and added to
  the frozen artifact; their fields match the existing POST success contract.
  All 76 schema/crosswalk metadata tests passed after that capture.
- The first full run had 8,876 passes, 25 skips and two failures. One was the
  pre-existing 15-second kernel first-cell timeout; it passed alone without any
  timeout change, then passed in the full run above. The available log does not
  establish its cause. The other was the R6/O4S-03 evidence digest: adding CAS
  tests changed one cited file. Independent re-audit confirmed the existing
  claim and old test ASTs were unchanged, and only that digest was refreshed.
- Full pre-commit including mypy passed on a clean candidate excluding the two
  original document edits. The PR harness passed all 38 scenarios; directory
  documentation, secret scan, route contract, 16 Skills installer selftests
  and the 2,283-file / 604-Skill npm package check passed. Wheel and sdist were
  built and verified without publishing. Source and committed Vite assets match.
- The named-session Ark probe above used a thread-owned observer and produced
  `ark-edit-notes.txt` as artifact `a-e173b9ee7826` in session `f-914c87c4d080`.
  An earlier completed probe retained request
  `02178938144336688a480d877f824556f2559e19636edcdfd3765` and a captured usage
  payload (prompt 15,568; completion 187, including 76 reasoning; total 15,755;
  cached 14,648), but its global observer mixed main and background title calls.
  Auxiliary usage and per-call elapsed attribution remain unknown; the captured
  usage is not the total cost of T2. The corrected probe does not erase that
  limitation or the earlier record.

T2 已完成实现、独立复核、本地完整验收及远端 CI。提交
`f558fc5225c7d45fc1c2ffba22b0a20d564a4ccc` 的 [CI 34837765300](https://github.com/PKU-YuanGroup/OpenAI4S/actions/runs/34837765300)
全部 25 个适用门禁通过（另有 4 个非适用作业跳过），包括 Python 3.10/3.12/3.13/3.14、
Linux、Docker、三浏览器及安装验证。Python 3.14 本轮运行 26 分 29 秒并通过；
无取消或重跑。独立无依赖 wheel 安装 smoke 通过 13 个模块及 604 个 Skills。
保留首次测试失败和实测记录缺口，不把未知用量当成零。
后端、前端及 dist 配套提交，不修改数据库 schema、迁移、版本号或发布流程。


## T3 validation / T3 验证

- A logical model call shares its three-send budget and absolute deadline across
  compatibility fallback, backoff, headers, body reads and cancellation drain.
  The default total timeout is 600 seconds (finite 1–3600); idle timeouts retain
  their meaning. The shared HTTP helper leaves its new idle option disabled for
  existing callers. DNS that is still resolving retains its detached slot, and
  returning after cancellation or expiry cannot open or send a new connection.
- JSON, error bodies, SSE lines/events/total input and queued UTF-8 text have
  enforced read-time bounds. Heartbeats count toward total input. Provider
  terminal events close promptly; OpenAI finish reasons still permit trailing
  usage. Oversized or incomplete tool arguments cannot become executable calls.
- Raw usage evidence remains separate from the compatible eight-field public
  projection. Missing, malformed or non-final counters are unknown; genuine
  measured zero stays zero. Cancelled calls keep their original accounting
  identity and detached capacity until accounting completes. Existing team
  quota entry points and automatic mode preserve unknown reservations rather
  than treating them as free calls. This item does not introduce new team quota
  entry points for previously unwired capabilities or change the database schema.
- Independent read-only implementation review found no remaining blockers after
  fixes to cancellation accounting, provider-error usage, malformed cache
  evidence, automatic-mode admission and late settlement branches. Targeted
  regression batches passed 268 tests and a final 82-test review acceptance run;
  strict mypy passed all eight configured source files. Full candidate pre-commit,
  38 PR harness scenarios, directory coverage and source secret scan passed.
- Real Ark short streaming requests confirm Stop after visible text, exactly one
  late callback for the old call (99 tokens), and successful next-call recovery
  (75 tokens). The initial 90-second probe reached HTTP 200 but no final usage;
  its usage remains unknown and is excluded from known usage subtotals.
- Chromium drove the real Stop control and then completed the same session via
  two native tool calls. Their returned usage (31,879 total tokens) matches the
  frame's 31,716 input + 163 output. The cancelled first browser call had no
  recorded response and unknown usage: it proves neither zero sends nor a
  cancellation after visible streaming. The separate short streaming test above
  covers that boundary. The UI issued two user-message POSTs and one cancel POST,
  reached done, and reported no uncaught page errors.
- The first live test failure exposed the supplied credential in a local pytest
  traceback through the configuration repr. That temporary log was immediately
  scrubbed. LLMConfig now omits its API key from repr, a regression test covers
  this, and subsequent live-test output is scrubbed before writing. No credential
  entered a source file, fixture, commit or CI configuration; retained evidence
  is checked before delivery.

T3 的慢头、滴流、心跳、长行、背压和协议终态由本地可控服务验证；
Ark 实测覆盖流式停止、旧调用回记和下一调用恢复。浏览器取消发生于
可见文本之前，记录明确保留该边界；不把未知计量或失败验证写成成功。
三浏览器矩阵 33/33 已通过，wheel/sdist 验证及独立无依赖安装 smoke
（13 个模块、604 个 Skills）已通过。完整离线套件及提交 CI 均已通过。


The first full T3 run reported three failures. Two characterization assertions
used an obsolete urllib monkeypatch and therefore injected zero attempts into
the new deadline-aware transport. The fixture now uses the transport injection
point and a finite, size-readable BytesIO response. Independent review confirmed
the same two-attempt recovery and byte-identical existing golden; no golden or
audit digest changed. The third failure was the unchanged first-cell 15-second
kernel timeout also observed in T1/T2. All three passed together after the fixture
fix (22.75 seconds; kernel test body 8.74 seconds), with the original timeout.
The full suite passed after this correction; its earlier failure is retained.

首轮完整测试的三处失败已如实保留：两处为旧 HTTP 夹具入口失效，
修复后原 golden 逐字节一致；另一处为原有首次 Cell 超时，未放宽阈值。
三项复测及随后完整套件均通过。


Final local T3 verification: **8,957 passed, 26 skipped**, zero failures/errors,
in 823.09 seconds. Response capture assembled all workers and checked **1,167
route/status shapes**, **212/212 routes**, with no breaking drift. The recorded
suite includes 209 kernel, 119 agent, 380 gateway, 81 MCP, 38 Doubao and 274 LLM
cases with no failures. Full clean-candidate pre-commit and all 38 PR harness
scenarios passed after the fixture correction. The final wheel/sdist is built
from that candidate so the two original user document edits are excluded from
both the commit and the distribution. Publishing, version changes, database
migration and merging to main remain outside this work.

最终本地验证通过：8,957 项通过、26 项跳过，耗时 823.09 秒；全部 worker 的
响应捕获完整合并，1,167 种响应形状无破坏性变化，212 条路由全部覆盖。
修复夹具后的全量 pre-commit 与 38 个 PR 场景均通过。
最终分发包从干净候选构建，排除两份原有文档修改；远端 CI 通过后进入 T4。


T3 commit `cc801345ccb10cecd14910f8ca177675258ab212` passed all 25 applicable
jobs (four not applicable jobs skipped) in [CI 34848725299](https://github.com/PKU-YuanGroup/OpenAI4S/actions/runs/34848725299).
The first local CI watcher exited on a TLS handshake timeout; a timestamped
read-only API monitor recovered and confirmed completion. No CI jobs were
cancelled or restarted.

T3 提交的 25 项适用 CI 作业全部通过；四项不适用作业跳过。首次本地监视进程
因 TLS 握手超时退出，随后恢复只读监视并核实最终状态，未取消或重跑 CI 作业。

## T4 Files validation / Files 验证

The initial regression run reproduced five failures: frame cards bypassed the
paged result, closed-dock loads did not populate filters, refresh lost requested
capacity, partial final pages did not grow correctly, and session switches could
paint previous cards. Cards, count, empty state and load-more now read the same
owned result. Frame data has a separate session/generation identity; project
refresh walks the existing artifact-index while retaining requested capacity.
Filters reset to 50, in-place WS updates re-slice current data, hidden rows stay
excluded, and conversation artifact visibility and retained drafts are unchanged.

Independent read-only review found no remaining implementation blockers. Its
project refresh and ownership probes were added to the fixed tests, including
second-page interleavings, repeated cursors and zero-progress failure. The full
frontend suite passed 705 tests; browser checks and full offline validation passed.

首轮复现五处失败。现在卡片、数量、空状态及加载更多共用具备会话归属的结果；
初始读取和 WS 更新都会重算，刷新保留已请求的容量，筛选变更回到第一页。
独立只读复核暂无阻断问题，补充的项目多页刷新与迟到响应测试已通过；
全量前端 705 项、浏览器检查和完整离线验证通过。


The real Chromium fixture found an additional server boundary: the project index
applied its limit before priority-hidden rows were removed by the client, so a
50-row response painted 49 cards. The index repository now excludes priority-hidden
rows before LIMIT; ordering, cursors, response shape and the legacy array endpoint
are preserved. Independent read-only review confirmed this scope. A real-route
regression covers 60 newer hidden rows in front of 125 visible rows, 50/50/25
pages, combined filters, all-hidden empty state and the unchanged legacy array.
The old in-progress full run was stopped after 3,801 passes and ten skips so the
updated candidate can receive a complete response-capture run; that partial run
is not final verification.

真实 Chromium 另发现项目索引的隐藏过滤发生于分页后，导致 50 行响应只显示
49 张卡片。现于 LIMIT 前排除 priority 隐藏行，排序、游标、响应结构及旧数组
接口保持；独立只读复核认可范围。新增真实路由回归覆盖 60 个隐藏新记录和
125 个可见记录的分页、组合筛选、全隐藏空状态及旧数组兼容性。
正在运行的旧候选完整测试在 3,801 项通过、10 项跳过后主动停止，后续以新候选
重新完成完整响应捕获，不把部分运行作为最终验证。


The three-engine matrix first passed 36/36. After strengthening the delayed-read
and REST-refresh assertions, all three Files scenes passed again, while the
existing WebKit editor scene timed out once waiting for ready (35/36 overall).
Its standalone recheck and the entire WebKit matrix then passed with unchanged
timeouts (12/12). Independent review found no T4 editor-state dependency that
explains this observation; its cause remains unproven and the failure is retained.
The final Files checks also compare both real DOM IDs for equal names in two
sessions, rather than relying only on intermediate arrays.

The existing Ark artifact `a-e173b9ee7826` / `ark-edit-notes.txt` passed Generated
versus Uploaded filtering in Chromium, Firefox and WebKit, with no new model
requests. The observed version was `v-37083588ebbd`, the head after T2 editor
validation; the original generation receipt records `v-4d33b4cdb21b`. These are
separate observations, not an assertion that editing left the original head intact.

三引擎矩阵首次 36/36 通过。加强迟到读取与 REST 刷新断言后，Files 三引擎再次
通过，但既有 WebKit 编辑器发生一次就绪超时；原阈值独立复查及整个 WebKit
矩阵随后通过（12/12）。未证明超时根因，保留失败记录；最终 Files 检查也在
真实 DOM 中核对跨会话同名文件的两个不同 ID。

复用 Ark 产物的来源筛选在三引擎均通过，本项没有新增模型请求。当前观察版本
为 T2 编辑验证后的 `v-37083588ebbd`，原始生成记录为 `v-4d33b4cdb21b`，
分别记录原始生成与本次读取事实。


Final T4 offline verification passed **8,958 tests, 26 skipped**,
with zero failures/errors in 916.088 seconds. All workers' response evidence
assembled successfully: **1,167 shapes, 212/212 routes**, no breaking drift.
The full frontend suite passed 705 cases; 58 targeted backend cases, typecheck,
i18n extraction, clean-candidate all-files pre-commit, 38 PR harness scenarios,
165-directory bilingual coverage (1,537 direct assets), source secret scan
(3,857 files), 212-route contract check, and Skills installer/package checks
(16 selftests; 2,283 files / 604 Skills) passed. Final source and dist are paired.
The two original document modifications remain byte-identical and excluded.

T4 完整离线验证：8,958 项通过、26 项跳过，零失败/错误，
耗时 916.088 秒；全部响应证据完整合并，1,167 种形状无破坏性漂移，
212 条路由全部覆盖。前端、针对性后端、类型、双语提取、全量 pre-commit、
harness、目录清单、secret scan、响应契约和 Skills 包检查均通过。
原有两份未提交文档保持逐字节一致，前端源码和 dist 同批交付。
