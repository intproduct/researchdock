# T01 第三轮独立审计 · 2026-09-19

## 结论：accepted（验证范围见下文）

未发现新的阻断问题。第二轮的旧缓存回写问题经源码检查和独立状态回归验证已关闭；79 项后端/Agent 测试及前端生产构建通过。本轮浏览器工具启动失败，未独立重跑端到端界面操作；本结论依据代码检查、实际执行的状态探针，以及前两轮已完成的验证，不声称本轮浏览器验收全部通过。

- 原任务基线 / 整合前 main：`7e4c4a0828045547c373c8f47a39ec8ac10beafb`。
- 第二轮审计提交：`d4dc3cc`。
- 本轮修复代码：`6712ded8c94825b26ecb52fdaf62c61ddc084d9d`。
- 被审计交付 HEAD：`757dee0096ba80cd99cfd68c204c51e08e5942e0`。
- 分支：`codex/task-01-history`；开始及验证完成时工作树均干净，第二轮审计提交为本轮 HEAD 的祖先。
- 实现方本轮仅修改 Workspace.tsx 与实现报告，未变更后端、迁移、Agent、权限或依赖。

## 问题关闭依据

R1 续项：成功回调在清除已提交草稿前，先把 PUT 返回的完整项目应用到查询缓存；显示内容和后续编辑基线随保存一起更新。列表查询的 revision 下限检查可以保留已知较新项目，避免较旧响应覆盖本次保存。保存期间新增的草稿继续保留，并推进到正确提交基线。保持同内容 PUT 仍产生新 revision 的契约。

R2：本轮后端未再修改；UTC 回归随 79 项测试独立通过。非零时区转换的独立验证见第二轮报告。

C1：冲突文案已明确采用最新会丢弃当前草稿，并要求重新编辑。C2 的架构范围修正保持不变。实现报告也已统一将真实断网端到端检查标为未执行，修正了前后矛盾的通过声明。

## 独立执行结果

| 检查 | 本轮证据 |
| --- | --- |
| 后端及 Agent 回归 | 79 passed，2 条既有弃用警告，56.79 秒；Windows / Python 3.14.6，隔离 SQLite 与临时 Git 仓库 |
| 前端构建 | TypeScript + Vite 成功 |
| 保存成功、列表 GET 尚未完成 | 状态探针通过：表单数据保持新内容，重复提交使用新内容和新 revision |
| 保存前取得的旧列表响应晚到 | 状态探针通过：释放旧响应后仍保持刚保存的项目状态 |
| PUT 等待期间继续输入 | 状态探针通过：后续草稿保留，下一次提交使用新基线 |
| 保存后、GET 尚未完成时开始新编辑 | 状态探针通过：不会将草稿固定到旧 revision |
| 409 后后台缓存更新 | 状态探针通过：保留草稿和原基线、标记冲突 |
| 网络错误回调 | 状态探针通过：不清除草稿；这不等于真实断网浏览器验收 |
| 判别性对照 | 对第二轮被审计源码 a9e6d12 执行同一探针，6 项中 3 项失败；当前源码 6 项全部通过 |

状态探针保存于 [scripts/audit/t01-state-probe.cjs](../../../scripts/audit/t01-state-probe.cjs)。它通过 TypeScript 转译读取实际 ProjectDetail 的渲染前代码，使用已安装的 TanStack QueryClient 和最小 hook 适配器执行保存、查询与编辑回调；没有复制产品的缓存更新实现。探针不启动浏览器，不模拟完整 React 调度或 DOM，因此不会将其结果表述为浏览器端到端通过。

可重复命令（在项目根目录，依赖已安装）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$reviewTemp=Join-Path (Get-Location) ('runtime/t01-review3-tests-'+[guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q --basetemp=$reviewTemp -p no:cacheprovider
npm.cmd --prefix frontend run build
node.exe scripts/audit/t01-state-probe.cjs
# 负面对照应退出 1，并出现 3 个失败；不 checkout、不改工作树。
node.exe scripts/audit/t01-state-probe.cjs a9e6d12
```

实际 pytest 目录：`runtime/t01-review3-tests-9d1f7a4c27fe4b1cae462f135c15468f`。测试不要复用已有数据目录作为 basetemp。

## 验证边界与后续

- 浏览器执行工具在运行任何代码前报“failed to write kernel assets: 系统找不到指定的路径”；重试及重置后仍失败。未因此推断产品有故障，也未调用实现者的 Playwright 脚本冒充独立浏览器验证。
- 本轮准备的隔离服务脚本位于本项目 runtime/t01-review3/server.py，但没有启动。没有访问或修改开发数据库，没有启动额外服务。所有本轮新增文件均在 research-manager 下。
- 本轮没有独立端到端验证慢响应、原生确认框及真实断网。保留此限制；T02 原本要求的容器网页/API 联调应同时复跑这些保存场景。已交付浏览器脚本只作为实现方证据，独立验证栏不据此记通过。
- PostgreSQL、应用容器、备份恢复、HTTPS 与云部署仍未验收。Docker 可用不代表这些检查通过；T01 accepted 不替代 T02。
- 审计不是无缺陷保证。当前未发现需要继续退回实现方的具体代码问题，因此按协议接受本包并本地 fast-forward 整合 main，保留完整实现与三轮审计历史；不 push，不自动实施 T02。

本轮仅新增审计报告及可重复的独立状态探针，更新审计入口和开发状态，不修改产品代码。实际 token/费用 unknown；两轮实现修复后，本轮剩余阻断问题数为 0。