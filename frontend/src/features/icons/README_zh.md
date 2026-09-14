# frontend/src/features/icons

[English](README.md)

工作台的线性图标（`app.js:7-77` 的 lucide 路径），集中在一张表里。移植时把 app.js 的表拆成了各车道的副本，副本之间逐渐走样：`panel-left`、`panel-right`、`moon`、`sun` 不在 `paintIcons()` 读取的任何一张表里，于是侧栏、停靠面板和主题按钮只画出空的 `<svg>`。`features/sessions/icon.ts` 与 `features/chrome/dom.ts` 都从这里取图形；新增图标名加到这张表，不要加到某个车道里。

表项是按 app.js 的方式以 innerHTML 注入的静态标记。不要用数据拼出表项。

## 文件

| 文件 | 职责 |
| --- | --- |
| [`paths.ts`](paths.ts) | `ICON_PATHS` 与 `iconSvg(name, size, cls)`。未知名称不画任何图形。 |
| [`icons.coverage.test.ts`](icons.coverage.test.ts) | 源码中每个 `data-icon="…"` / `setAttribute("data-icon", "…")` 名称，加上主题切换用的 sun/moon，经 `paintIcons` 都能画出图形；sessions 与 chrome 两个辅助函数对同一名称画出相同的图。 |
