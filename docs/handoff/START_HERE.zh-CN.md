# Claude Code / Kimi 开发交接

交接日期：2026-09-19。实现基线：`2a0d8eb`。本文件与其他交接文档将作为后续独立文档提交；实际工作从包含这些文件的当前干净 HEAD 开始，**不要 reset 到实现基线**。

## 1. 工作目标与现状

用户要统一管理多台机器及 GitHub 上的科研项目。云端保存身份、观察、权限和研究记录；源代码和未提交工作留在各设备。当前 v0.1 已跑通账号登录、项目创建、设备配对/撤销、只读 Agent、状态上报、研究进展保存。尚未实现 GitHub 实时接入、跨设备直接历史比较、自动同步、完整研究日志，也尚未完成云部署。

当前实际仓库为 `D:\files\research-manager`；不要在 `D:\files\Ran-ASKS-Fang` 开发。这是独立 MIT 模板衍生项目，复用来源见 `THIRD_PARTY_NOTICES.md`。不需要再 clone 模板或研究参考仓库。

入口地图：

| 路径 | 内容 |
| --- | --- |
| backend/app/research_models.py | Project、Device、WorkingCopy 及输入模型 |
| backend/app/api/routes/research.py | 所有当前科研 API，包含权限及修订/观察序号检查 |
| backend/app/api/deps.py | 用户和设备相关认证依赖的基础入口 |
| backend/app/core/config.py、db.py | 配置、引擎和模型注册 |
| backend/app/alembic/versions/ | 迁移，基线 revision 为 d42026f707b5 |
| backend/tests/conftest.py | 当前强制临时 SQLite，默认 create_all/drop_all |
| backend/tests/api/routes/test_research.py | 权限、修订、设备与倒序上报现有测试 |
| frontend/src/research/Workspace.tsx | 总览、项目详情、设备页面；按需拆出新组件 |
| frontend/src/research/api.ts | 科研 API 类型与请求函数 |
| agent/research_agent/ | Python 标准库客户端和 Git 只读扫描器 |
| compose.yaml、deploy/ | 尚未完成运行验收的容器栈 |
| scripts/setup_local.py、dev.py | 本地初始化与前后端启动 |

先读当前任务卡，再读取这些入口的相关部分。旧调研文档中的 `../.scripts`、`../operations` 等指向的是参考仓库，不是本应用；它们是历史调研证据，不是新项目的执行规则。当前事实以源码、`docs/status.md` 和真实验证结果为准。

## 2. 当前任务与交付顺序

1. 执行 [T01：研究记录修订历史](TASK-01-history.zh-CN.md)。含迁移、API、前端与测试，形成一份完整可审查交付。
2. 提交 `docs/handoff/reports/T01-implementation.md`，回复提交范围，等待 Codex 独立审计。
3. 按审计问题在同一任务分支追加修复提交，保留可比较的历史。
4. 审计通过后，由 Codex 在本地整合；再执行 [T02：PostgreSQL 与 Compose 联调](TASK-02-postgres-compose.zh-CN.md)。重复同样流程。

T01 代码审计与 T02 不同时改同一工作目录。无需保持一个模型空转等待：交付时结束会话；用户把提交信息交给审计方后，再根据审计结果续接。这里没有跨客户端自动唤醒机制，也没有部署常驻协调器。

## 3. 分工与 Git 约定

- Codex：明确契约、评审独立 diff、重跑必要检查、记录缺陷和验收结论；高风险架构变化由其审查。
- Claude Code / Kimi：在范围内实现、自测、修复审计问题、维护交付报告。不要让用户人工复制代码或合并文件。
- 用户：提供外部资源（未来的 GitHub/服务器配置）、在两个客户端之间转交简短审计请求；决定后续范围。

启动检查 `git status --short`、当前分支与 HEAD。若工作树有别人的修改，保留并说明，不能 reset/clean/stash 后继续假装干净。

干净仓库从当前交接 HEAD 创建 `codex/task-01-history`；T02 从审计整合后的 main 创建 `codex/task-02-postgres-compose`。分支已存在则先核查对应报告和提交，不覆盖重建。任务报告记录实际 base SHA，不能只写旧基线。

一个任务可有几个连贯提交（迁移/API、页面、测试修复）；不要提交构建产物、依赖、测试数据库或密钥。提交命令仅 add 本任务文件。无需远端、PR 或 push。交付后不自行合并 main，不自行进入下一个任务；这是本次分工的审计边界，不是每次编辑前向用户求批准。

## 4. 本地运行与验证

后端 Python 3.14；Agent 必须保持 Python 3.11+；前端 Node 24+；部署 PostgreSQL 17。依赖已安装时不要先重新安装或整批升级。不要因看到依赖更新提示扩大本任务范围。

Windows（在项目根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m research_agent --help
```

Linux 对应 `.venv/bin/python` 和 `npm`。需要新环境时按 README 安装。`.venv` 不随 Git 交付；在新 worktree 要另建环境或显式使用已知解释器，不能假定激活脚本可迁移。

初始开发服务使用 8000/5173；它们可能已由用户运行，先确认端口归属，不为测试结束任意进程。隔离联调用其他端口和数据库。未经明确指定，不把真实 `.env`/credentials.local.txt 用于测试，不运行会对当前开发库迁移或清空的命令。首次测试基线为 66 passed，含模板测试；这不是覆盖率或“全系统安全”证明。

当前 SQLite 单测会覆盖 DATABASE_URL，因此仅在外面设置 PostgreSQL URL 并跑旧命令，并没有测到 PostgreSQL。T02 必须解决这个验证缺口。

## 5. 共同不可破坏的约束

- 项目关联必须显式绑定 UUID，不按同名路径、时间戳或 AI 猜测合并。
- Dirty 与提交关系独立；本地缓存 upstream 不代表实时 GitHub。历史不足返回 unknown。
- Agent 扫描保持只读，不 fetch/push/checkout/reset，不上传内容；这两包不修改 Agent 协议。
- 权限必须由后端执行；用户/设备 Token 的权限不能混用；客户端传来的 actor/owner 不能作为授权依据。
- 项目版本更新、历史落库属于同一个事务；重复或失败请求不允许留下孤立历史。
- 新增 Alembic revision，不改已发布的初始迁移来“绕过迁移”。不在 GET 或启动 Web 请求中 create_all。
- 不引入 Redis、Celery、对象存储、AI 编排等额外服务来完成当前两包。

## 6. 省 token 的执行方式

每包只加载本入口、任务卡及必要代码。进度更新只写发现、决策和阻塞，不复述整份计划。失败时保留相关错误片段；完整输出留在被忽略的 runtime 下，不反复粘贴安装日志。先跑受影响检查，最终跑约定回归；无改动、无新疑点不重复全量执行。

使用固定任务 ID + base/head SHA + 报告传递上下文，不拷贝整段聊天。每包只记录实际可取得的输入、缓存输入、输出/推理计量及费用；不可取得写 unknown，不以耗时或代码行数反推 token。不要求更换用户已经配置的模型。

## 7. 可直接发给 Claude Code 的启动消息

```text
请在 D:\files\research-manager 工作。阅读 CLAUDE.md、AGENTS.md、docs/status.md，按 docs/handoff/START_HERE.zh-CN.md 的约定执行 TASK-01-history.zh-CN.md。先核对当前分支和干净状态，从当前包含交接文档的 HEAD 建立任务分支；不要回退到旧基线。完成实现、迁移、测试和前端验证，创建本地提交，并按 REPORT_TEMPLATE.md 写 T01 实现报告。只完成 T01，不推送、不自行合并、不启动 T02。交付实际 base/head SHA、检查结果和未解决事项，等待独立审计。现有模型使用你已配置的 Kimi 后端，不需要改模型设置。
```

实现结束后发给 Codex：

```text
请按 D:\files\research-manager\docs\handoff\REVIEW_PROTOCOL.zh-CN.md 审计 T01。实现报告在 docs/handoff/reports/T01-implementation.md，分支为 codex/task-01-history；请读取报告中的实际 base/head SHA，独立检查和验证，写审计结论。不要仅凭实现报告判通过。
```
