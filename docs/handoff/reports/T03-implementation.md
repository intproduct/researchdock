# T03 实现报告

- 状态：ready_for_review
- 任务卡：docs/handoff/TASK-03-repository-identity.zh-CN.md
- 分支：codex/task-03-repository-identity
- 实际 base SHA：62cb7f177ccf2c612783b284b4ac4b9c7d29c73c（含 T02 + T03 任务卡的 main）
- 最后代码提交 SHA（此报告提交之前）：9e4df7b3fccb84ff6851b064a66de27bb9e74a3b
- 执行平台/解释器/Node/数据库版本：Windows 11 / Python 3.14.6（.venv）/ Node（npm，Vite 构建）/ 本地 SQLite；PostgreSQL 见“阻塞和未解决事项”
- 实际模型与服务来源：Claude Code（Kimi 后端）实现与自测；无外部服务调用

## 结果

用户现在可以在一个项目下创建多个逻辑仓库（UUID 身份，与 remote 无关、同名不合并），把不同机器的副本显式关联/改绑/解绑到某个仓库，并在网页项目详情页按仓库分组查看副本，另有“未归类”组。Agent 可列出项目仓库、在登记时可选 `--repository` 绑定；旧 Agent（不传 repository_id）行为不变且不会清空已有绑定。仓库改名、副本关联均用期望修订做并发保护；改名/关联不触碰项目修订历史与本地文件。

主要修改：
- `backend/app/research_models.py`：新增 `Repository` 表与 DTO；`WorkingCopy` 增 `repository_id`(null=未归类)、`binding_revision`(默认0)；复合 FK `(repository_id,project_id)→repository(id,project_id)` 在数据库层强制同项目绑定。
- `backend/app/alembic/versions/c4d8e2f15a07_repository_identity.py`：新迁移，父 `b7f3a1c29e04`，不自动建仓库。
- `backend/app/api/routes/research.py`：仓库 CRUD、副本绑定接口、Agent 仓库只读列表与登记扩展。
- `agent/research_agent/cli.py`：`repositories` 命令、`link --repository` 及旧服务器确认校验。
- `frontend/src/research/{api.ts,Workspace.tsx}`：Repository 类型、仓库分组面板（创建/改名/关联），连接指引更新。
- 测试：`backend/tests/api/routes/test_repositories.py`、`backend/tests/test_migration_history.py`（A10）、`agent/tests/test_cli_repositories.py`（A09）。
- `scripts/audit/t03_smoke.py`：A13 端到端冒烟。

## 契约核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| A01 一项目两仓库、两设备绑定同仓库 | 通过 | test_repository_create…（同名不合并）、A13 冒烟：2 副本 repository_id 相同 |
| A02 同名/相同remote/无remote 不自动合并 | 通过 | 无 remote 匹配逻辑；同名仓库各自独立 UUID（create 测试）；改 remote 走观察，不改 repository_id |
| A03 创建/改名校验、稳定 UUID、revision 冲突 | 通过 | test_repository_create_rename_and_validation |
| A04 关联/改绑/解绑/同值重试 | 通过 | test_copy_binding_lifecycle_and_binding_revision |
| A05 并发改绑单基线单成功、观察与改绑不互吞 | 通过（SQLite 实测） | test_concurrent_rebind_same_baseline_only_one_succeeds、test_observation_does_not_overwrite_binding；PG 实测未执行 |
| A06 越权与设备角色 | 通过 | test_repository_cross_account_and_device_role |
| A07 登记重试/并发/冲突 | 通过 | test_agent_registration_retry_and_legacy_compatibility、test_concurrent_registration_no_duplicate_copy |
| A08 旧 API/旧 Agent payload 兼容 | 通过 | 旧登记不传 repository_id → 未归类且不清空已有绑定（同测试文件） |
| A09 新 Agent 遇旧服务器不谎报 | 通过 | agent/tests/test_cli_repositories.py |
| A10 空库/旧库升级、回退再升级、模式一致 | 通过（SQLite） | test_t03_upgrade_preserves_data…、test_t03_downgrade…；strict metadata diff 为空；PG 未执行 |
| A11 页面创建/改名/分组/关联冲突保留输入 | 部分（构建+类型通过；浏览器实测未执行） | 前端 build 与 Biome 通过；冲突保留输入逻辑在 RenameRepository/BindCopy 实现，未经浏览器实测 |
| A12 约束与清理、级联不退化 | 通过 | 复合 FK 拒绝跨项目绑定（test_binding_rejects_cross_project_and_bad_values）；全量回归无级联回归 |
| A13 独立端到端（两 Agent 绑定同仓库） | 通过（Windows） | scripts/audit/t03_smoke.py 实跑成功；Linux 冒烟未执行 |

## 执行记录

| 工作目录与命令（去秘密） | 环境/数据库 | 退出码与数量 | 结果 |
| --- | --- | --- | --- |
| backend：`alembic upgrade head`/`downgrade -1`/`upgrade head` | 临时 SQLite（runtime/t03mig，已删） | 0 | 升级/降级/再升级通过；repository 表空、旧数据保留 |
| backend：`pytest tests/api/routes/test_repositories.py` | 临时 SQLite | 0，9 passed | 通过 |
| backend：`pytest tests/test_migration_history.py` | 临时 SQLite 子进程 | 0，6 passed | 通过（含 A10 三新增） |
| backend+agent：`pytest backend/tests agent/tests` | 临时 SQLite | 见下 | 见“最终回归” |
| agent：`pytest tests/` | 临时 home | 0，11 passed | 通过 |
| frontend：`npm run build` | Node/Vite | 0 | TypeScript+Vite 构建通过 |
| frontend：`biome check src/research/*` | — | 0 | 通过（格式化 --write 后） |
| `python scripts/audit/t03_smoke.py` | 临时 SQLite+回环端口+一次性 git 仓库 | 0 | A13 两 Agent 绑定同仓库，分组正确 |
| `ruff check`（本任务改动文件） | — | 0 | 通过 |

UI 操作步骤及可观察结果：浏览器端到端（A11）未执行——本轮浏览器工具未启动。前端经生产构建与类型检查通过；仓库分组、未归组、改名/关联 409 保留输入为代码实现，未经真实浏览器人工确认。

迁移/恢复验证：临时 SQLite 上 T02→T03 升级保留 project/workingcopy/device/观察/history，repository 初始为空，不自动建仓库；downgrade 仅删新元数据、保留副本与历史；再升级恢复绑定列。PostgreSQL 迁移验证未执行（见下）。

## 最终回归

交付前完整 `pytest backend/tests agent/tests -q --basetemp runtime/t03-final`：**109 passed，2 条既有弃用警告，0 失败，222.39s**（基线为 T02 第四轮 93 项；T03 新增 16 项：repositories 9 + migration A10 三新增 + agent 5，migration 原有 6 项中 HEAD_REVISION 更新后全过）。前端生产构建与 Biome 通过，本任务改动文件 Ruff 通过。

## 设计决定与偏离

- 用复合 FK `(repository_id, project_id)→repository(id, project_id)` 并在 `repository(id,project_id)` 上加唯一约束，使“同项目绑定”由数据库强制，而非仅靠服务端下拉过滤（任务卡 §3 允许此方案）。
- 副本绑定用独立 `binding_revision`（初始 0/显式绑定 1），改名用 `Repository.revision`，二者互不影响，符合不变量 3（不触碰 Project.revision/T01 历史）。
- 并发首次登记：捕获唯一约束 IntegrityError 后重读胜者行，相同参数收敛为 200、不同参数 409，避免并发下误报重复。
- Agent 本地 SQLite 未存 repository_id（任务卡 §5 允许：服务端为关联来源）；未改本地模式。
- 无新增第三方依赖。
- 偏离：A13 冒烟中设备配对用 HTTP `POST /devices` 直接写各 agent 的 settings（等价于 `login`），因 Windows 下 `getpass` 无法从管道读密码；不涉及仓库绑定逻辑。

## 阻塞和未解决事项

- 环境缺口：本机 Docker/PostgreSQL 不可用。A05 并发、A10 迁移在 **PostgreSQL** 上的实测未执行；A13 的 **Linux** CLI 冒烟未执行。需要可用的 PG（TEST_DATABASE_URL + TEST_SCHEMA_FROM_MIGRATIONS=1）与一台 Linux 环境。
- A11 浏览器端到端未执行（浏览器工具本轮未启动）。
- 以上不属于代码缺陷；在缺失环境前无法补齐，已在报告如实标注“未执行”。

## 交接

- 尚未进行独立审计；请按 REVIEW_PROTOCOL 审计。
- 包含报告的 HEAD SHA 见最终提交（本报告随文档提交一并落地）。
- 下一任务：等待审计；不自行写 accepted、不整合 main、不推送、不开始 T04。

## 重要：本次会话的协议偏离（用户明确授权）

用户在本会话明确授权两点，偏离了 `docs/status.md` 与任务卡 §1 的既定启动条件：(1) 豁免 T02 远端运行验收即视为可推进；(2) 在 T02 正式 accepted 之前开始 T03 编码。据此我将 T02 分支快进整合入 main 并基于此建立 T03 分支（base `62cb7f1`）。T02 的远端 PG/容器/重启/备份恢复证据仍缺失；本报告不因此宣称 T02 已 accepted，相应审计结论以 Codex 正式记录为准。
