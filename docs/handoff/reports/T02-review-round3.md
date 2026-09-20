# T02 第三轮独立审计 · 2026-09-20

后续见 [第四轮报告](T02-review-round4.md)（交付 HEAD 1fade9c）：R6 已关闭，进入远端运行验收；以下保留第三轮结论。

## 结论：changes_requested；远端运行验收仍未完成

R4（仓库外输出）与 R5（CLI 解析回归）已修复。本轮新增一项 P2：Compose 配置检查吞掉非零退出码，把失败报告为通过。实际配置解析没有发现错误，但交付的回归检查被削弱，需恢复失败行为。不整合 main，不开始 T03。

- 分支：`codex/task-02-postgres-compose`；开始时工作树干净。
- main / T01 基线：`9feceacc19cccb062dda61bd7aa8ea09079763e7`。
- 上轮审计提交：`c9ddc9c`，已确认是本轮 HEAD 的祖先。
- 本轮代码提交：`f118154`；被审计交付 HEAD：`f9aa2c63e31b67a062d07e2e0c08c815a233294b`。
- 增量 4 个文件：环境生成器、备份 CLI、对应测试、实现报告。无业务 API、前端、迁移或依赖变更。

## R6 · P2：Compose 配置失败被当成测试成功

位置：`backend/tests/test_compose_backup_cli.py:75–77`，`test_generated_env_is_self_contained_and_compose_loads_it`。

本轮将原来的退出码断言替换成：

```python
if config.returncode != 0:
    return
```

`docker compose config --no-env-resolution` 不依赖 Docker daemon。非零退出可能表示 YAML 无效、必需变量缺失或其他配置错误，不能一概归因为 Docker 不可用。提前返回后，测试既不校验 backend/migrate 的 env_file，也不标记 skipped，pytest 会显示 passed。文件包含 ENV_FILE 只能证明生成器写了变量，不能证明服务确实使用该变量。

独立故障注入：保留真实环境文件生成，只把 Docker 配置命令替换为退出码 1、错误 `invalid compose project: required variable missing`。直接执行交付测试函数，结果正常返回，错误被放行。没有修改 compose.yaml 或运行 Docker 引擎。另独立执行当前真实配置解析，两个服务的完整 env_file 路径均正确，说明这是验证可靠性缺陷，不是已证明部署配置损坏。

最小修复：恢复对 config.returncode == 0 的断言。若确实支持未安装 Docker CLI 的开发机，应把生成器单测与 Compose 检查分开；仅对明确缺失的工具显式 skip 并显示原因，已执行的配置命令报错必须失败，CI 必须实际执行此检查。不要将所有非零退出归类为 skip。

验收要求：正常配置时核对两个服务的实际路径；模拟配置错误时必须失败；不能把故障注入计入通过。无需重写部署脚本或业务代码。

## 原问题复核

| 问题 | 结论 | 本轮证据 |
| --- | --- | --- |
| R4 仓库外路径抛异常 | 关闭 | 回退显示绝对路径；真实系统临时目录用例通过；重复生成仍拒绝覆盖 |
| R5 CLI 回归误放行/执行 Docker | 关闭 | parse_args 进程内解析四组顺序并校验字段；缺参退 2；额外独立模拟 main 的四组派发全部正确，禁止 Compose.run |
| 原 R2 环境隔离实现 | 维持关闭 | 独立 daemon-free 配置解析，backend/migrate 完整路径都等于本次隔离 env；其回归门槛新增的问题单列为 R6 |

R1/R3 没有新的实现变化；本轮完整回归覆盖相关现有测试。测试名称中的“负向对照”本身不能替代真实证据，本轮判断基于解析结果和独立入口派发验证。

## 独立执行记录

- `python -m pytest backend/tests agent/tests -q --basetemp runtime/t02-review-round3/pytest -p no:cacheprovider`：**91 passed，2 warnings，202.78 秒**，没有 deselect。TEST_DATABASE_URL 和 TEST_SCHEMA_FROM_MIGRATIONS 为空，默认使用测试拥有的临时 SQLite。未重设系统 TEMP，仓库外路径用例使用真实系统临时目录并自行清理。两条警告均为既有依赖弃用；禁用 cacheprovider 以避开已知旧缓存写入权限问题。
- `npm --prefix frontend run build`：**通过**，TypeScript 与 Vite 构建成功。
- `ruff check scripts/compose_env.py scripts/postgres_backup.py backend/tests/test_compose_backup_cli.py`：**通过**；`git diff --check` 通过。
- 独立探针：真实 Compose 完整路径 **2/2**；main 隔离派发 **4/4**；配置错误被测试误放行已复现。因此 91 passed 不能代替 R6 的判别性验证。
- 日志与探针（Git 忽略）：`runtime/t02-review-round3/pytest.txt`、`frontend-build.txt`、`probe.py`、`probe-results.json`。探针需使用新的输出目录重跑，避免环境生成器拒绝覆盖。

没有调用本机 Docker 引擎、重启服务、访问真实开发数据库或执行真实备份/恢复。没有修改实现代码。

## 远端缺口与交接

实现报告仍明确：当前版本 PG 套件未重跑，完整容器栈、Nginx 同源与 SPA、重启持久化、备份恢复及恢复后撤销权限均未执行。用户先前提供的远端 Docker/Compose 和四个基础镜像拉取成功，只是准备完成，不是 T02 验收通过。

请实现方仅修复 R6、补故障回归并更新交付证据。随后按 [远端操作说明](../T02-remote-server.zh-CN.md) 对确定版本补齐 PG/迁移、容器启动、网页/API、重启及第二空库恢复检查；保留已有 napcat/astrbot。代码问题清零后，若这些检查仍缺失，状态应为 blocked_environment，不能写 accepted。main 仍保留 T01 accepted 基线。
