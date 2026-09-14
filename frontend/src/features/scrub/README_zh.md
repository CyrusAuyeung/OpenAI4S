# frontend/src/features/scrub

[English](README.md)

给用户可见字符串涂抹凭证样串。移植 app.js `publicText`，另有用于模型 id 与协议名的 `publicModelId`：仅有凭证前缀（如 `ark-code-latest`）并不等于密钥。

## 文件

| 文件 | 职责 |
| --- | --- |
| [`scrub.ts`](scrub.ts) | `publicText`；`publicModelId`（带前缀的串只有同时像随机串时才涂抹）。 |
| [`scrub.test.ts`](scrub.test.ts) | Bearer / 密钥样串 / query 涂抹；超限省略号；模型 id 保持原样而真实密钥样串仍被涂抹。 |
