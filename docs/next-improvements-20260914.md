# Next improvements — 2026-09-14 / next 分支改进记录

This ledger covers the approved sequential T0–T9 plan, starting at
`8127907657d21a4cbb514bd1c21096801fd6cf6a`. It does not change the version,
schema, release policy or `main`. Each implementation is reviewed and validated
before pushing `next`; the following item waits for that commit's CI.

本记录跟踪本轮 T0–T9 顺序执行。原有 `TODO_zh.md` 与
`next-version-progress.md` 的未提交修改保留在工作区，不纳入本轮提交。
验证凭据只由进程环境提供，不进入代码、日志或 Git。

| Stage / 阶段 | Status / 状态 | Evidence / 证据 |
|---|---|---|
| T0 Baseline / 基线 | Completed / 完成 | Locked Python 3.12 science + chemistry, frontend and three Playwright browsers installed; 90 LLM baseline tests passed. Baseline [CI 34819967908](https://github.com/PKU-YuanGroup/OpenAI4S/actions/runs/34819967908) succeeded at the starting SHA. |
| T1 P0-01 Retry and compatibility / 重试与降级 | Locally validated; CI pending / 本地验收通过，待 CI | Shared three-send state, one compatibility POST, structured stream refusal only, cancellation before sends, semantic replay veto. Initial regression run reproduced 11 failures. Independent review passed after five findings were fixed; 144 targeted tests passed. |
| T2 P0-03 Editing / 编辑保护 | Not started / 未开始 | Loading guard, version condition, drafts, conflict and uncertain save. |
| T3 P0-02 Resource bounds / 资源边界 | Not started / 未开始 | Total deadline, bounded input, backpressure and usage evidence. |
| T4 P1-01 Files | Not started / 未开始 | Shared filtering and pagination. |
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
- Final acceptance still requires the pushed commit's CI. Temporary detailed
  logs are in `/private/tmp/openai4s-next-improvements-20260914`; this ledger
  retains the non-secret results for repository readers.

完整离线套件与 schema 门禁、独立复核、静态检查及 Ark 实测均已完成。
额外并行核心回归出现一次首次 Cell 的 15 秒超时；该用例不经过模型调用，
单独重跑通过，同一组 255 项按 CI 分配方式重跑也全部通过。保留这次观察，
不放宽超时或改动内核来消除测试结果。当前仍等待本项提交的 CI 验收。
