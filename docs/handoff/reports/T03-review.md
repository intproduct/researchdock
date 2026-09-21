# T03 独立审计 · 2026-09-21

## 结论：changes_requested；另有远端运行证据缺口

发现三项 P2：仓库改名冲突后无法用保留草稿重新提交；副本关联冲突会卸载对话框并丢失选择；关联接口区分其他账户仓库与不存在仓库，泄漏存在性。前两项已在真实浏览器与隔离 API 上复现，第三项在普通账户上独立复现。未发现成功越权绑定或读取其他仓库内容的证据。

- 实际 base / 当前 main：`62cb7f177ccf2c612783b284b4ac4b9c7d29c73c`，已确认是交付 HEAD 的祖先。
- 被审计 HEAD：`1ee164df7724932bbb880ddd7d17d4e0a59c12a3`；分支 `codex/task-03-repository-identity`。
- 实现报告最后代码提交为 `9e4df7b`，但 HEAD 的文档提交也新增了可执行 `scripts/audit/t03_smoke.py`，本审计覆盖它。
- 增量 14 个文件；开始/测试结束时工作树均干净。未修改实现代码，不整合 T03、不启动 T04。
- 启动例外：实现报告记录其会话中用户豁免 T02 启动门槛；当前 Git 确认 T02 已进入 main。本审计按实际交付基线继续，不重写历史；没有将该例外视作 T02 或 T03 远端验收通过，也未独立读取另一会话的授权原文。

## R1 · P2：改名冲突提示可以重试，但请求始终携带旧 revision

位置：`frontend/src/research/Workspace.tsx:500–519`，关联 `527–534`。

RenameRepository 的 base 只在打开对话框时设置。409 后仅 setConflict(true) 和 onDone() 刷新；repo props 已更新，但保留草稿的对话框内 base 仍是旧值，保存继续发送旧 revision。关闭重开才能取得新 base，同时 setName(repo.name) 会重置用户草稿。

浏览器复现：打开 revision=1 的 UI-A，输入 Retained Draft；另一会话通过真实 API 改名为 External Rename、revision=2。首次提交后界面准确显示“修订 2、输入已保留、确认后请重新提交”；再次保存仍停留在同一冲突。独立 GET 确认服务端仍为 External Rename/revision=2，草稿未写入。无冲突改名作为对照成功。

修复要求：提供明确采用最新版本再提交的恢复路径，在保留名称草稿的同时更新期望基线；加载最新值失败时不能假定已拿到新基线。维护已知成功 revision，避免慢响应把它倒退。不能用去掉乐观锁或关闭重开来解决。

回归：双会话改名冲突 → 草稿保持 → 用户确认使用最新基线 → 成功写入 revision=3；另覆盖刷新失败、再次发生并发更新及较旧响应晚到。

## R2 · P2：改绑冲突后的分组刷新卸载对话框，丢失未提交选择

位置：`frontend/src/research/Workspace.tsx:614–617`，与 `793–805`、`818–831` 的分组内 BindCopy 实例共同触发。

BindCopy 的 open/target/base 都保存在各仓库分组内的组件中。另一会话改绑后，本会话的 409 会触发副本刷新；副本从 A 的 article 移到 B 的 article，原组件被卸载，冲突提示与选择也随之消失。copy.id 的 key 不能跨不同父节点保留组件状态。

浏览器复现：副本在 A、binding_revision=1；打开关联框并选择 C，另一会话将副本改到 B/revision=2；本会话提交后对话框数量变成 0，副本显示在 B。重开关联框选中 B，原选择 C 已丢失。正常无冲突改绑到 C 的对照成功。

修复要求：将编辑中的 copy ID、目标选择、期望版本和冲突状态移到不会随分组变化卸载的稳定层（例如项目级单一关联对话框）；展示服务端最新关联并提供明确确认后重试。BindCopy 的 base 同样只能在打开时更新，恢复路径要一并修复；不得自动覆盖用户选择或悄悄重试写入。

回归：A→B 的外部改绑与本地 C 草稿冲突，刷新/移动分组后对话框和 C 选择仍保留；明确采用最新基线后可提交。覆盖从/到未归类组以及旧响应晚到，不只测试成功路径。

## R3 · P2：校验目标仓库时未先校验所有权，返回码泄漏存在性

位置：`backend/app/api/routes/research.py:273–278`；同类契约不一致还在 Agent 登记入口 `376–381`。

用户关联接口直接 session.get(Repository, id)：不存在返回 404，存在但不属于当前 copy.project_id 返回 422，其中包含其他账户仓库。普通账户由此能区分给定 UUID 是否存在；任务卡要求不存在与其他账户统一 404，仅同账户的另一项目才返回 422。

独立验证使用两个新建普通账户（调用者 is_superuser=False）：针对自己副本提交另一账户真实仓库 UUID，得到 422；提交随机不存在 UUID，得到 404。没有成功写入该跨账户关联。Agent 登记将不存在和跨项目统一 422，虽本次没有同样的存在性区别，也未遵循约定的 404/422 分层。

修复要求：两入口复用先验证目标 Repository 所有权的查询/require_repository，再判断同项目；其他账户/不存在为 404，本账户其他项目为 422。拒绝时关联、binding_revision、sequence 不变，不能产生孤立副本。

回归：普通用户与设备分别覆盖不存在、其他账户、本账户其他项目、本项目四类目标；与 repository 列表/改名授权语义一致。

## 独立验证结果与边界

| 检查 | 本轮实际结果 |
| --- | --- |
| 完整后端/Agent pytest | 109 passed，2 条既有弃用警告，238.80 秒；无 skip/deselect |
| 前端 TypeScript + Vite 生产构建 | 通过 |
| 交付的双 Agent Windows HTTP/CLI 冒烟 | 独立执行成功：两个隔离配置绑定同 Repository 并实际上报；不代表 Linux 已测 |
| 新建隔离数据库 | 通过真实 Alembic upgrade head 创建，然后初始化审计专用账户；未使用开发库 |
| 浏览器 | 实际构建产物 + 同源回环 API；登录、项目/仓库分组、空仓库/未归类展示、无冲突改名/改绑通过；R1/R2 冲突失败 |
| 后端授权探针 | 普通账户 R3 复现；本次 SQLite 中带已绑定副本的账户删除返回 200，直接删除测试项目成功，先前 FK 级联疑点未复现，不列为缺陷 |
| 增量 Ruff | 返回四条错误，均在新增 scripts/audit/t03_smoke.py：F401 threading、BLE001 两处、PLW1510 缺显式 check；其他列入检查的变更文件无报告错误 |
| git diff --check | 通过 |
| PG、Linux、完整 UI 异常矩阵 | 未执行 PG 迁移/并发及 Linux CLI；浏览器未穷尽断网/较旧响应晚到等全部矩阵，不能因本轮启用浏览器就把 A11 全标通过 |

完整测试命令：`python -m pytest backend/tests agent/tests -q --basetemp runtime/t03-review/pytest -p no:cacheprovider`。TEST_DATABASE_URL / TEST_SCHEMA_FROM_MIGRATIONS 为空；默认自建临时 SQLite；关闭 cacheprovider 仅避开已有目录权限问题。

原始证据（均忽略于 Git）：`runtime/t03-review/pytest.txt`、`cli-smoke.txt`、`backend_probe_server.py`、`backend-probe-results.json`、`regular-user-scope.json`、`concurrent_action.py`、`browser-evidence.json`。浏览器证据摘要基于本轮实际 DOM 操作与独立 API 状态核对。探针创建自有一次性账户/数据库；浏览器临时页已关闭，审计服务已核实进程身份后停止。没有调用本机 Docker 引擎或操作真实工作仓库。

## 交接与非阻断改进

1. 先修 R1–R3，补足会暴露原版错误的回归，再交付同分支追加提交。不要重写业务框架或删除现有版本校验。
2. 冒烟脚本的 Ruff 四条问题与“本任务改动文件全部通过”的报告不一致，应修正并记录准确检查范围；脚本异常路径也建议用 finally 回收自建服务。此项不另列核心功能阻断编号。
3. Agent 无 --repository 重复登记已关联副本时，服务端正确保留关联，但 CLI 总打印“未归类”；这是非阻断文案问题，按返回的 repository_id 显示实际状态即可。
4. 实现报告应把 A11 更新为已独立发现缺陷；A05/A10 的 PG 和 A13 Linux 继续保留未执行。用户对 T02 启动门槛的例外不能自动解释成豁免这些 T03 验证。
5. T02 的历史运行缺口继续单列保留；T03 不因代码自测通过就自动 accepted。当前 main 保持 62cb7f1，不整合本包。
