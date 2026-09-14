# frontend/src/components/dashboard

[English](README.md)

F-13 工作台外壳。冻结 id 对齐 `tests/webui-contract.md`（`#dashboard`、`#dash-projects`、`#dash-sessions`、`#workspace`、`#messages`、`#dock-notebook`）。`#composer-hint` 带 `role=status aria-live=polite`。`#tab-close` 是真 button。断连横幅接管不存在的 `#conn-dot`。

## 文件

| 文件 | 职责 |
| --- | --- |
| [`ModelSelect.tsx`](ModelSelect.tsx) | composer 里的 `#model-select`，由 Customize 的模型 store 渲染；切换时调用 `chooseComposerModel`。 |
| [`ModelSelect.test.tsx`](ModelSelect.test.tsx) | 每个 `/models` 条目一个选项且默认项选中；加载前只有一个空选项；切换 → `PUT /models/default`；被拒绝时恢复原选择。 |
| [`Shell.tsx`](Shell.tsx) | 仪表盘 + 工作台 + composer + 项目模态的标记。`#dash-project-search` 是首页项目筛选框。 |
| [`dashboard.css`](dashboard.css) | `#conn-banner` 与菜单焦点。全局 token 归 F-21。 |
| [`index.ts`](index.ts) | `Shell`，以及给后续产物瓦片 / 关标签钮车道用的键盘激活辅助函数。 |
