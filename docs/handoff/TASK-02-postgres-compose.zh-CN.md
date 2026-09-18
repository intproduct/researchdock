# T02 · PostgreSQL、Compose 与恢复验证

状态：待 T01 accepted 后开始。依赖：包含 T01 的审计整合提交。预计规模：3–5 传统人日。本包完成可重复的本机/CI 部署验证；不等于已经上线用户云服务器。

## 目标

在全新隔离环境构建镜像、创建 PostgreSQL、执行全部迁移、通过同源网页/API 使用 T01、备份并恢复到另一套空数据库。默认 SQLite 开发方式继续可用。不引入 Kubernetes、队列或云供应商依赖。

## 已知验证缺口（须核查，非全部已确认的代码缺陷）

- 交接时 Docker daemon 未运行；Compose 只做过配置解析，CI 定义未在远端运行。
- backend/tests/conftest.py 无条件覆盖 DATABASE_URL 为临时 SQLite，并使用 create_all/drop_all。仅提供 PostgreSQL 环境变量不足以形成 PostgreSQL 证据。
- compose 服务 `env_file: .env` 写死；`docker compose --env-file` 只改变插值来源，不自动替换 service env_file。隔离联调必须同时解决这两处配置，不能偷用现有开发密钥。
- PostgreSQL 密码直接拼接 URL；应对 URL 保留字符明确支持正确编码，或在初始化工具中使用清晰约束并对不合法输入失败，不能静默错误连接。避免把带凭据 DSN 打印进报告。
- migrate 初始化账户只应幂等创建，重启不应重置密码或业务数据。后端 readiness、前端代理可用性目前缺少运行证据。

## 实施范围

1. 建立明确的隔离测试入口。SQLite 保持默认；PostgreSQL 测试通过独立 TEST_DATABASE_URL（或同等明确变量）显式启用。若指定 PostgreSQL 不可用，必须失败而非回退 SQLite。
2. 对测试库做防误删限制：单独测试连接变量、测试专用数据库名、显式测试模式。由脚本创建/拥有的临时库或 CI service 专用数据库可以清理；普通 DATABASE_URL 及用户 .env 永不作为 drop/create 的备用目标。完整 DSN 不出日志。
3. 把“ORM 单元测试”和“从 Alembic 创建的真实模式验证”区分开。不能先 create_all 再声称迁移成功。确保被测引擎确实为 postgresql，输出无秘密的 dialect/数据库测试标识作为证据。
4. 增加 Linux CI PostgreSQL service 测试；保留 SQLite 与前端构建检查。没有远端时只交付 workflow 定义并如实标注未执行，不为运行 CI 自动创建远端仓库。
5. Compose 隔离配置允许指定测试 env 文件、项目名、网页端口；文档给出精确命令，使用 -p research-manager-test-<唯一后缀> 和独立卷。默认仅回环暴露网页，数据库不对公网开放。
6. 构建 backend/frontend，执行迁移并验证健康检查；服务重启保留数据。只有依赖已启动不是应用 ready，验证数据库连接和 API 可用性。
7. 提供 PostgreSQL 备份/恢复操作说明及可执行入口。恢复只针对显式指定的空测试目标，默认拒绝覆盖已有业务库。备份不入 Git；日志无密码。

优先修改 compose.yaml、deploy/、scripts/、测试 fixtures/集成测试、.github/workflows/check.yml、相关配置与文档。业务 API 只修联调证明存在的问题；单列缺陷和回归。不得重写 T01 功能。

## 必须得到的运行证据

| 场景 | 验收结果 |
| --- | --- |
| 全新 PostgreSQL | 从空库 Alembic upgrade head，包含 T01；不依赖 create_all |
| 从 v0.1 升级 | 在旧 revision 放入测试项目、设备和副本，升级后内容、ID、序号和基线历史正确 |
| 真实 API | 登录、项目创建/更新、历史分页、所有权、设备配对/撤销、上报在 PG 上通过 |
| 并发事务 | 两独立连接更新同一 revision，恰好一个成功，快照唯一且与当前项目一致 |
| 观察序号 | 倒序/重复观察不能覆盖新观察，PG 上实际验证 |
| 配置隔离 | 测试使用独立 secrets/数据库/卷/端口，不读取或覆盖日常开发库 |
| 容器前端 | Nginx 同源 /api 转发可用，直接访问项目详情 SPA 路由也可加载 |
| 重启 | 项目、历史及设备状态保留；不会重新创建或重置现有用户密码 |
| 备份恢复 | pg_dump 后恢复到第二个空测试库；核对 UUID、内容、revision、history、序号，并验证旧 revision 仍 409 |
| 权限恢复 | 恢复后已撤销设备仍拒绝访问；保留 SECRET_KEY 等配置的恢复要求写清，密钥不塞进普通数据库报告 |
| 默认开发 | SQLite 测试及本机启动仍可用，前端 build 通过 |

只把 SQL 离线编译成功不能算 PostgreSQL 运行通过；容器 build 成功不能算服务启动通过；备份文件存在不能算恢复通过。

迁移回退仅在拥有的临时库验证，说明 T01 downgrade 丢弃历史的影响。备份/恢复工具不得默认指向 .env 的生产连接，不能裸执行 down -v 清理现有项目。

## 环境不可用时如何继续

先执行一次 Docker 状态检查，记录是否为 daemon 不可用、镜像下载或权限问题。不要未经要求安装/开启系统服务、改防火墙、提升 Docker 对外暴露程度。可用临时 PostgreSQL 则先完成数据库验证；无法运行容器则完成代码、CI、脚本和配置解析，报告明确状态 `blocked_environment` 及尚未验证矩阵。下游不能把它当 accepted。

无需云服务器账号即可完成本包大部分内容。真实域名、证书、服务器部署留给 T14；不会因为暂缺这些信息把所有编码停下。

## 交付

分支 codex/task-02-postgres-compose；docs/handoff/reports/T02-implementation.md；必要的 README/状态文档、测试命令和故障诊断。报告写实际数据库/镜像版本与执行平台、精确 base/head、通过/失败/未执行清单。容器或 PG 未验证时绝不标成“生产可用”。
