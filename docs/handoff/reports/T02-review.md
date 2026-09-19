# T02 独立审计 · 2026-09-19

## 结论：changes_requested，另有 Docker 环境阻塞

发现 3 项可独立于 Docker 复现的代码/交付缺陷（2 项 P1、1 项 P2）。Docker 重试仍返回服务端 500；真实 PostgreSQL、容器栈与备份恢复本轮未独立运行，不能将实现者已有 PG 记录当作本轮通过证据。暂不整合 main，不开始 T03。

- 基线 / main：`9feceacc19cccb062dda61bd7aa8ea09079763e7`。
- 最后实现代码：`1e6a28d2a20dda3ec3ebcc495b09e73c969b3ad7`。
- 被审计交付 HEAD：`62063291d46d1e0279dd791c7c9e56e2051eb149`。
- 分支：`codex/task-02-postgres-compose`；开始时工作树干净，基线为交付 HEAD 的祖先。
- 原交付 11 个文件，重点检查测试库选择、DSN、Compose 服务环境、健康检查、备份恢复及 CI。

## R1 · P1：默认测试会沿用普通 DATABASE_URL，并删除已有表

位置：[backend/tests/conftest.py](../../../backend/tests/conftest.py)，30–32 行；关联 58–62 行和 db fixture 的 teardown。

未提供 TEST_DATABASE_URL 时，代码虽然创建了临时目录，却用 `os.environ.setdefault("DATABASE_URL", ...)` 设置连接。如果启动 pytest 的终端已经存在普通 DATABASE_URL，则继续使用这个连接。SQLite 还会跳过测试库名检查，测试结束执行 `SQLModel.metadata.drop_all(engine)`，清掉其中的应用表。这直接违反“普通 DATABASE_URL 永不作为 drop/create 备用目标”的 T02 契约。

独立复现只使用审计者新建的一次性 SQLite 文件：在普通 DATABASE_URL 指向的文件预先创建 user 表和测试账号，不设置 TEST_DATABASE_URL；调用实际 session fixture 完整运行 setup/teardown。结果：

```text
ordinary_DATABASE_URL_selected = true
existing_user_table_before = true
existing_user_table_after = false
```

没有触碰真实开发库。名称过滤也不能替代连接来源限制：普通环境中的 PostgreSQL URL 若碰巧以 _test 结尾，仍可能被误选。

修复：默认模式无条件使用本次拥有的临时 SQLite；外部测试库只能来自显式测试连接及明确测试模式，并校验受控目标。对显式 SQLite 文件也应规定所有权或拒绝任意已有文件，不能因为不是 PostgreSQL 就直接放行。测试身份配置应避免沿用业务账户/秘密。

回归必须覆盖：普通 DATABASE_URL 指向已有哨兵库时，默认测试执行后该库完全不变；无 TEST_DATABASE_URL 时不连接外部 PG；非法/不可用 TEST_DATABASE_URL 明确失败且不回退。

## R2 · P1：生成的隔离 env 未指定 ENV_FILE，容器仍加载日常 .env

位置：[scripts/compose_env.py](../../../scripts/compose_env.py)，32–45 行；关联 compose.yaml 中 `env_file: ${ENV_FILE:-.env}` 及部署文档第 1–2 节。

生成器的 values 没有 ENV_FILE，文档的启动命令也没有设置它。`docker compose --env-file ...` 只指定插值来源，不能自动替换 service env_file。按交付说明执行，backend/migrate 仍加载根目录 .env，混用日常 SECRET_KEY、账号及 DATABASE_URL；后者非空时还优先于本轮 PostgreSQL 分项配置，可能连错数据库或导致启动失败。

独立执行生成器，再调用无须 daemon 的 `config --no-env-resolution --format json`，只输出路径而不读取/显示秘密，结果：

```text
GENERATED_ENV_FILE_KEY = false
backend.env_file = D:\files\research-manager\.env
migrate.env_file = D:\files\research-manager\.env
```

修复：生成器写入可正确解析的 ENV_FILE，或明确通过命令/配置传递；统一启动、迁移、备份、恢复入口的行为。新增回归应验证生成后按文档原样调用，两个服务加载的都是所生成文件；根 .env 有不同 DATABASE_URL / secrets 的场景也不能混入。

## R3 · P2：备份/恢复文档命令无法通过参数解析

位置：[scripts/postgres_backup.py](../../../scripts/postgres_backup.py)，143–149 行；[docs/deployment-verification.md](../../deployment-verification.md)，44–46 行。

--project 和 --compose-env 定义在顶层 parser，文档及脚本示例却将它们放在 backup/restore 子命令之后。按文档执行 backup，尚未访问 Docker 就以退出码 2 报顶层必选参数缺失。恢复示例同样受影响。

本轮实际执行文档形式，得到：

```text
postgres_backup.py: error: the following arguments are required: --compose-env, --project
```

修复可让 CLI 接受文档顺序，或统一修正文档和示例。当前 parser 可识别的顺序是：

```powershell
python scripts/postgres_backup.py --project <项目名> --compose-env <隔离env> backup
python scripts/postgres_backup.py --project <项目名> --compose-env <隔离env> restore --file <备份> --target-db <新测试库>
```

补无 Docker 的 CLI 解析测试；Docker 恢复后仍需执行真实 dump/restore，不得只修帮助文字就算验收通过。

## 独立检查与边界

| 检查 | 结果 |
| --- | --- |
| Docker 重试 | 使用具有管道访问权限的环境执行 docker version，Client 29.3.1；Server `/v1.54/version` 返回 500；Compose v5.1.1 可用。不是沙箱权限报错，未擅自重启/重置 Docker |
| 默认测试隔离探针 | 失败，实际删除一次性已有库的 user 表，见 R1 |
| 生成器 + Compose 服务 env 文件解析 | 失败，仍指向根 .env，见 R2；没有打印解析后的秘密 |
| 文档备份命令解析 | 失败，退出 2，见 R3 |
| 保留字符密码的 DSN | 独立 Settings / make_url 探针通过：含 @、:、/、% 的密码 round-trip 正确，host/db 正确，未打印密码 |
| SQLite + Agent 回归 | 显式覆盖到全新隔离数据库后 **79 passed，2 条既有弃用警告，70.62 秒** |
| 前端生产构建 | TypeScript + Vite 通过 |
| 审计新增手动 API 助手 | 通过语法检查；在实际 FastAPI + 一次性 SQLite + TestClient 传输适配下 seed/verify 通过，包含历史/副本序号、旧版本 409 与撤销凭据 401；这不是 Docker 或真实网络验证 |
| PostgreSQL / 镜像构建 / 容器网页 / 重启 / 真实备份恢复 | 本轮未独立执行；Docker 恢复后按任务卡继续 |
| CI | 定义已检查，未远端执行 |

全套 SQLite 回归为避免 R1，明确设置 TEST_DATABASE_URL 与 DATABASE_URL 到本轮新建 SQLite 文件，并覆盖测试账号/秘密；这只能证明显式隔离路径的回归通过，不能证明默认路径安全。首次审计命令有一次 PowerShell basetemp 参数传递错误，修正后完成上述 79 项；该命令错误不计为产品缺陷。

复现工具/证据均在本项目 runtime/t02-review/ 内；测试数据库、生成 env、fixture 和秘密不提交。源码审计未发现本轮越过 Agent 只读边界或新增业务 API 写入语义。恢复工具实际行为尚无 Docker 运行证据，表数量检查/失败恢复等边界应在后续补测，不把缺少证据当作通过。

## 修复与人工验证交接

1. Claude Code 在当前分支追加修复 R1/R2/R3，补针对性回归，更新实现报告；不 squash、不合并、不启动 T03。
2. 用户可先按 [T02 手动验证说明](../T02-manual-test.zh-CN.md) 第 1 步重启 Docker Desktop 并检查 Server。第 2 步以后建议等代码修复后再执行，文档已显式处理 ENV_FILE 和备份参数顺序，避免照旧说明误操作。
3. 手动验证覆盖隔离栈、同源网页、重启和第二空库恢复。提供 [API 数据核对助手](../../../scripts/audit/t02-api-probe.py)，可比较源/恢复 API 的项目与历史、副本 ID/序号和撤销权限。
4. 真实 PG 测试、旧版本迁移、并发、备份恢复矩阵仍需补齐。手动验证摘要与准确代码 HEAD 一并交回审计后，才能决定 accepted。

本次仅新增审计报告、人工步骤与审计助手并更新协作状态，未修产品代码。所有新增文件均位于 research-manager；main 保持 9feceac，未推送远端。实际 token/费用 unknown。