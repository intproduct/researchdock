# Claude Code / Kimi 开发交接

更新日期：2026-09-22。T01 已 accepted；T02 已关闭代码问题，等待远端运行验收；T03 已完成第三轮审计，已知代码问题关闭，当前 blocked_environment；T04 任务卡已编写，状态 planned。状态以 docs/status.md 和对应审计报告为准。实现时记录实际 main/base/head，**不要 reset 到历史参考提交**。

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
| backend/tests/conftest.py | 默认自建临时 SQLite；显式 TEST_DATABASE_URL 启用 PG，TEST_SCHEMA_FROM_MIGRATIONS=1 使用 Alembic |
| backend/tests/api/routes/test_research.py | 权限、修订、设备与倒序上报现有测试 |
| frontend/src/research/Workspace.tsx | 总览、项目详情、设备页面；按需拆出新组件 |
| frontend/src/research/api.ts | 科研 API 类型与请求函数 |
| agent/research_agent/ | Python 标准库客户端和 Git 只读扫描器 |
| compose.yaml、deploy/ | 尚未完成运行验收的容器栈 |
| scripts/setup_local.py、dev.py | 本地初始化与前后端启动 |

先读当前任务卡，再读取这些入口的相关部分。旧调研文档中的 `../.scripts`、`../operations` 等指向的是参考仓库，不是本应用；它们是历史调研证据，不是新项目的执行规则。当前事实以源码、`docs/status.md` 和真实验证结果为准。

## 2. 当前任务与交付顺序

1. T01 已通过第三轮独立审计并整合 main，不重复实施。
2. T02 已通过代码修复复审（[第四轮报告](reports/T02-review-round4.md)），整体仍有运行缺口。实际已整合至 main（62cb7f1）；实现报告记录了提前推进的授权例外，不等于远端验收已通过。按 [远端说明](T02-remote-server.zh-CN.md) 补证据。
3. [T03：Repository 身份及项目关联](TASK-03-repository-identity.zh-CN.md) 已交付，当前按 [第三轮审计](reports/T03-review-round3.md) 在现有 codex/task-03-repository-identity 分支补远端运行及剩余 UI 验证；R1–R4 已关闭，不重新建分支或重复启动。
4. [T04：个人 GitHub 连接](TASK-04-github-connection.zh-CN.md) 已完成计划，选定精细 PAT 与本人仓库显式映射；正常实施等待 T03 accepted 并整合、T02 运行缺口补齐，除非用户另有明确例外。任务卡含分步实现、A01–A13 和转交文本，本次不启动编码。
5. T05–T14 见 [路线图](ROADMAP.zh-CN.md)，包含多机器手动试用、GitHub 总览和日常云使用里程碑。后续每包实施前另定完整契约，不自动连续开发全部任务。

每包交付实现报告 → Codex 独立审计 → 实现方追加最小修复 → accepted 后整合。交付后结束会话，由用户转交简短消息；没有跨客户端自动唤醒或后台协调服务。不同时在同一工作目录修改不同任务。

## 3. 分工与 Git 约定

- Codex：明确契约、评审独立 diff、重跑必要检查、记录缺陷和验收结论；高风险架构变化由其审查。
- Claude Code / Kimi：在范围内实现、自测、修复审计问题、维护交付报告。不要让用户人工复制代码或合并文件。
- 用户：提供外部资源（未来的 GitHub/服务器配置）、在两个客户端之间转交简短审计请求；决定后续范围。

启动检查 `git status --short`、当前分支与 HEAD。若工作树有别人的修改，保留并说明，不能 reset/clean/stash 后继续假装干净。

T03 启动时从已包含 T02 accepted 与任务卡的实际 main 创建 `codex/task-03-repository-identity`。T02 当前分支保留到验收整合。任何任务分支已存在时先核查报告和提交，不覆盖重建；记录实际 base SHA，不能只写历史参考提交。

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

当前默认测试强制使用本次拥有的临时 SQLite。PG 测试必须显式设置专用 TEST_DATABASE_URL；从迁移建模式另设置 TEST_SCHEMA_FROM_MIGRATIONS=1，检查日志的实际 dialect。容器测试按用户决定在远端执行，本机 Docker 不再重试。不能用普通 DATABASE_URL 或开发 .env 作为测试目标。

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

## 7. T03 的转交消息

以下保留首次启动提示作历史参考。当前 T03 已交付，应直接按 T03-review-round3.md 补验证证据，不再执行首次建分支步骤。实际提前启动例外见实现报告与 status。

```text
请在 D:\files\research-manager 工作，读取 AGENTS.md、docs/status.md、docs/handoff/START_HERE.zh-CN.md 和 docs/handoff/TASK-03-repository-identity.zh-CN.md。核对 T02 已 accepted 并整合 main，工作区干净；条件不满足只报告实际缺口。满足后从实际 main 创建 codex/task-03-repository-identity，按任务卡实施并验证 A01–A13，只做 T03。保持 Agent 只读与旧数据兼容；本机 Docker 不重试，PG/容器测试在远端隔离环境完成。分步提交，创建 docs/handoff/reports/T03-implementation.md，记录实际 base/head、执行证据和未执行项；不自标 accepted、不合并、不推送、不自行开始 T04。
```

交付后发给 Codex：

```text
请按 D:\files\research-manager\docs\handoff\REVIEW_PROTOCOL.zh-CN.md 审计 T03。任务卡是 TASK-03-repository-identity.zh-CN.md，报告是 reports/T03-implementation.md。核对实际 base/head，重点检查显式身份、所有权、关联并发、迁移保真、旧 Agent 兼容与只读边界，独立验证后把结果写入 research-manager 的交接目录。
```

## 8. T04 计划入口

使用 [TASK-04-github-connection.zh-CN.md](TASK-04-github-connection.zh-CN.md)。已固定：个人 github.com 精细权限 PAT、每用户一连接、本人仓库显式映射、令牌加密/轮换/本地断开、稳定平台 ID、并发校验与错误脱敏；分支/提交观察留给 T05。不需要 clone 额外仓库。实施步骤和可直接转交的提示在任务卡 §10–§12；先核对启动条件，不能把编写计划当作开始实现或豁免验收。
