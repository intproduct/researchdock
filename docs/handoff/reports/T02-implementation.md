# T02 实现报告

- 状态：blocked_environment（部分运行证据已取得；容器栈、同源前端与恢复端到端未完成）
- 任务卡：docs/handoff/TASK-02-postgres-compose.zh-CN.md
- 分支：codex/task-02-postgres-compose
- 实际 base SHA：9feceacc19cccb062dda61bd7aa8ea09079763e7（T01 accepted 后的整合 main）
- 最后代码提交 SHA（此报告提交之前）：1e6a28d2a20dda3ec3ebcc495b09e73c969b3ad7
- 执行平台/解释器/Node/数据库版本：Windows 11 / Python 3.14.6 / Node 26.5 / PostgreSQL 17.11（容器，x86_64-pc-linux-musl）/ SQLite；Docker Desktop 29.3.1、Compose v5.1.1
- 实际模型与服务来源（不知道写 unknown）：Kimi 后端（用户配置的 Claude Code 会话），其余 unknown

**不要把这个状态当成 accepted。** 数据库层已在真实 PostgreSQL 上运行通过；容器栈与恢复流程因 Docker 环境故障未完成，见“阻塞”。

## 结果

在真实 PostgreSQL 17.11 上跑通后端全套测试，且被测模式**完全由 Alembic 迁移创建**（`create_all` 未参与），并验证了从 v0.1 旧 revision 升级到含 T01 历史表的过程：旧项目/设备/副本内容、ID、序号保留，仅补一条 `migrated_baseline`。测试库选择、防误删、DSN 密码编码、Compose 隔离配置与备份/恢复入口已实现。默认 SQLite 开发方式未变。

未完成：容器整套栈构建启动、Nginx 同源转发与 SPA 路由、重启持久化、pg_dump→恢复端到端核对、CI 远端执行。

主要修改文件及原因：

| 文件 | 原因 |
| --- | --- |
| backend/tests/conftest.py | 以 TEST_DATABASE_URL 显式选择测试库；PG 必须是明显的测试库否则失败；无 SQLite 回退；TEST_SCHEMA_FROM_MIGRATIONS=1 时用 Alembic 建模式；打印无秘密的 dialect 证据 |
| backend/app/core/config.py | 由 POSTGRES_PASSWORD 组合 DSN 时做百分号编码，修复含 `@`/`:` 密码静默解析错误 |
| backend/app/core/db.py | 抽出 create_engine_for(url)，允许显式 URL 建引擎而不依赖导入期 engine |
| backend/app/alembic/env.py | 支持进程内 override_url，使迁移可指向测试库且不改 .env（规避 ConfigParser 对 `%` 的插值） |
| backend/app/api/routes/utils.py | 新增 `/utils/readiness/`，真实探测数据库连通性 |
| compose.yaml | env_file 参数化为 ${ENV_FILE:-.env}；db/backend 增加 readiness 健康检查；端口仍仅回环 |
| .github/workflows/check.yml | 新增 postgres:17 service 作业（Alembic 建模式）；保留 SQLite 与前端构建 |
| scripts/compose_env.py | 生成隔离 compose env（随机密钥，git 忽略） |
| scripts/postgres_backup.py | compose 内 pg_dump/pg_restore；目标必须是明显测试库；非空目标默认拒绝覆盖 |
| docs/deployment-verification.md | 可重复的隔离验证步骤与清理方式 |

## 契约核对

| 任务卡要求 | 结果 | 证据 |
| --- | --- | --- |
| 全新 PostgreSQL：空库 Alembic upgrade head（含 T01），不依赖 create_all | 通过 | PG 17.11 容器；`TEST_SCHEMA_FROM_MIGRATIONS=1` 全套 73 passed；日志含 `dialect=postgresql driver=psycopg database='research_test' schema_from_migrations=True` |
| 从 v0.1 升级：旧 revision 放入项目/设备/副本，升级后内容、ID、序号、基线历史正确 | 通过 | runtime/tmp/pg_upgrade_check.py：seed revision=3 + device + copy sequence=5 → upgrade head → 仅 1 条 migrated_baseline(revision=3)、actor_id 为 NULL、project_updated_at 保留 2026-09-15、project revision 仍 3、copy sequence 仍 5 |
| 真实 API（登录/项目/历史分页/所有权/设备/上报）在 PG 上通过 | 通过 | 上述 73 passed 即 PG 上运行的 backend/tests（含 test_research.py、test_history.py 全部断言） |
| 并发事务：两独立连接同 revision，恰好一个成功，快照唯一 | 通过 | test_concurrent_same_baseline_only_one_succeeds 在 PG 模式通过 |
| 观察序号：倒序/重复不能覆盖新观察 | 通过 | test_device_scoping_observation_order_and_revocation 在 PG 模式通过 |
| 配置隔离：独立 secrets/库/卷/端口，不读写日常开发库 | 部分通过 | compose_env/env_file 参数化、独立项目名与卷、PUBLIC_PORT、loopback 已实现且 `docker compose config` 通过；未用真实栈实际起过（Docker 故障） |
| 容器前端：Nginx 同源 /api 与 SPA 路由 | 未执行 | 需容器栈运行 |
| 重启保留数据、不重置已有密码 | 未执行 | 需容器栈运行；initial_data 幂等逻辑已在 PG 单测中覆盖 |
| 备份恢复：pg_dump 恢复到第二个空库并逐项核对 | 未执行 | 脚本已实现但需运行中的 compose db；Docker 故障 |
| 权限恢复：恢复后已撤销设备仍拒绝 | 未执行 | 依赖上一条 |
| 默认开发：SQLite 测试与本机启动仍可用，前端 build 通过 | 通过 | SQLite 全套 79 passed；npm run build 成功 |
| 测试库防误删限制 | 通过（代码+守门） | conftest 对非测试库名抛错；无 SQLite 回退；restore 脚本拒绝非测试库名 |

## 执行记录

| 命令（去秘密） | 环境/数据库 | 退出码与数量 | 结果 |
| --- | --- | --- | --- |
| `pytest backend/tests agent/tests -q` | Windows/Python 3.14/临时 SQLite | 0，79 passed | 默认路径未回归 |
| `TEST_DATABASE_URL=postgresql+psycopg://…@127.0.0.1:55432/research_test TEST_SCHEMA_FROM_MIGRATIONS=1 pytest backend/tests -q` | 真实 PostgreSQL 17.11 容器（Alpine） | 0，73 passed | PG + Alembic 建模式全绿 |
| `python runtime/tmp/pg_upgrade_check.py` | 第二个 PG 库 research_upgrade_test | 0 | 旧数据保留 + 单条基线回填，UPGRADE PATH OK |
| `npm run build`（frontend） | Node 26.5 / Vite 8 | 0 | 生产构建成功 |
| `ruff check backend/app scripts/` | Python 3.14 | 非 0，1 条 | 本包新增/修改文件全部通过；仅剩 `backend/app/api/deps.py` 的 I001 导入排序，该文件本包未改动，且在被审计的 T01 accepted 提交 `9feceac` 上已同样报错（预先存在，未顺手改，避免扩大范围） |
| `docker compose --env-file runtime/env/t02.env -p rm-t02 config` | Compose v5.1.1 | 0 | 隔离配置解析通过，env_file/端口/健康检查生效 |
| `docker compose -p rm-t02 up -d --build` | Docker Desktop 29.3.1 | — | **未完成**：镜像层下载停滞，随后 daemon 对全部 API 返回 500 |

关键日志位置（均已 git 忽略，位于 runtime/tmp/）：
- `pg-all.log`：PG 全套 73 passed。
- `pg_upgrade_check.py` 输出：升级路径断言。
- `compose-up.log`：容器构建停滞的原始进度行。

UI 操作步骤：**未执行**。容器栈未起来，无法在 Nginx 同源环境实际点击验证；本项不标通过。

迁移/恢复验证：升级路径已在真实 PG 上按上表核对。**备份恢复未执行**——脚本就绪但 compose db 未运行。T01 的 downgrade 影响（回退丢弃历史表）在 T01 报告中已于临时 SQLite 验证；本包未在 PG 上重复该回退。

## 阻塞和未解决事项

环境缺口（阻断本包其余验收）：

1. Docker Hub 镜像层下载失败：`production.cloudfront.docker.com` 返回 `EOF`（`alpine` 也曾失败）。经用户同意改用 `docker.m.daocloud.io` 镜像加速器后，`postgres:17-alpine`、`nginx:1.28-alpine` 已拉到并 `docker tag` 回官方名；`node:24-alpine`、`python:3.14-slim` 层下载极慢。
2. 在上述停滞拉取过程中，Docker Desktop 29.3.1 的 daemon 变为对所有 API 返回 `500 Internal Server Error`（`/info`、`/containers/json`、`/images/create` 均失败），`rm-pg-t02` 容器随 daemon 异常而不可用。恢复需要重启 Docker Desktop——按任务卡“不要未经要求开启/重启系统服务”，已停下询问，用户指示**先交付代码并标阻塞**。
3. 本机未安装 PostgreSQL，无法绕开容器做备份/恢复。

因此未验证矩阵：容器整套栈构建与启动、Nginx 同源 `/api` 与 SPA 路由、后端 readiness 在真实容器中的表现、重启持久化、pg_dump→恢复端到端核对、CI 远端执行。下游不得把本包当 accepted。

任务范围外（T02 明确不要求，或留待后续）：真实域名/证书/云服务器上线（T14）；Kubernetes、队列、对象存储；SQLite 开发数据自动迁移到 PostgreSQL。

已发现并要求“单列缺陷与回归”的问题：**DSN 密码未编码**（`p@ss:word/x` 使 `make_url` 把 host 解析为 `word`）已在 backend/app/core/config.py 修复，并由 compose 改为不把原始密码拼进 URL。本包未改业务 API 语义。

## 成本记录

| 项目 | 数值 | 单位/计量来源 |
| --- | --- | --- |
| 输入总量 | unknown | tokens |
| 其中缓存命中输入 | unknown | tokens；是否包含在上行需说明：unknown |
| 输出 | unknown | tokens |
| 推理 | unknown | tokens；与输出是否重叠需说明：unknown |
| 实际费用或套餐用量 | unknown | 原币种/额度、计费来源、日期 |
| 修复轮数 | unknown | 轮；本包尚未进入审计修复阶段 |
| 人类介入 | 2 | 次；确认镜像加速器来源、决定 Docker 故障时“先交付代码标阻塞” |

## 交接

- 状态 blocked_environment：数据库层已有真实 PG 运行证据；容器/恢复未验证，需环境恢复后继续。
- 环境恢复后待办（按序）：重启 Docker Desktop → 用镜像加速器补齐 `node:24-alpine`/`python:3.14-slim` 并 tag 回官方名 → `up -d --build` 起栈 → 验证 Nginx 同源与 SPA 路由 → 重启持久化 → 备份恢复到第二空库逐项核对。
- 最终回复中提供包含本报告的 HEAD SHA。
- 不自行写 accepted，不整合 main，不进入 T03。
