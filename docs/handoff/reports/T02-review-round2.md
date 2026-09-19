# T02 第二轮独立审计 · 2026-09-20

后续见 [第三轮报告](T02-review-round3.md)（交付 HEAD f9aa2c6）；以下保留第二轮结论。

## 结论：changes_requested；远端运行验证仍待完成

原 R1/R2/R3 的具体缺陷已关闭，本轮发现两项 P2：默认 CI 临时目录触发环境生成器异常；CLI 回归测试无法辨别原错误，且实际调用 Docker。需要修复后再交付。真实 PostgreSQL、完整容器栈和备份恢复仍缺少当前交付版本的独立运行证据；不整合 main，不开始 T03。

- 分支：`codex/task-02-postgres-compose`。
- main / T01 基线：`9feceacc19cccb062dda61bd7aa8ea09079763e7`。
- 上轮审计提交：`1091915`；本轮代码提交：`16509e62c34dac88756296105e57c26d7bea65eb`。
- 被审计交付 HEAD：`8a8042998ca6a8188f6aad2a4d574a4cb1f281d9`。
- 检查增量为 7 个文件；开始时只有此前审计侧提供的远端操作说明未跟踪，没有实现代码的未提交修改。
- 本轮未修改实现代码。运行产生的数据与日志均在被忽略的 runtime 内；测试自身临时创建的子测试文件已清理。

## R4 · P2：仓库外输出路径导致生成器报错，默认 CI 会触发

位置：`scripts/compose_env.py:62`；调用方 `backend/tests/test_compose_backup_cli.py:35–38`；CI `.github/workflows/check.yml:19,51`。

生成器允许绝对输出路径，但成功提示直接执行 `target.relative_to(ROOT)`。输出目录位于仓库外时，文件虽然已写入，脚本仍以 ValueError、退出码 1 结束。新增测试使用 pytest 的 tmp_path 并断言退出码 0；两个 CI job 均未设置仓库内 basetemp，Linux 默认临时目录通常在 /tmp，因而会触发该失败。本轮未运行 GitHub Actions，这一 CI 影响根据 workflow 和独立复现判断。

独立复现将生成器原样复制到 runtime 下的模拟仓库，输出到模拟仓库外的兄弟目录；全部实际文件仍在本项目 runtime 内。结果：退出码 1、输出文件存在、异常来自 relative_to。仓库内输出对照成功。实现方的本地通过记录和本轮使用仓库内 basetemp 的通过结果，均不能覆盖这一缺口。

修复建议：成功提示兼容仓库外路径（例如输出绝对路径或安全的相对/绝对显示分支）；增加仓库外路径回归。不要只把 CI 的临时目录移到仓库内来隐藏脚本缺陷。验收要求：仓库内和仓库外输出均返回 0，ENV_FILE 指向实际输出位置，重复生成仍拒绝覆盖；默认 CI 测试入口可用。

## R5 · P2：CLI 回归会误放行原错误，并调用真实 Docker

位置：`backend/tests/test_compose_backup_cli.py:72–90`。

断言 `returncode != 2 or "unrecognized arguments" not in stderr` 只排除一种错误文案。原解析器对文档顺序返回的却是缺少必需参数。独立负向对照直接加载 `6206329` 的原脚本，仅执行参数解析并阻止业务派发，得到退出码 2、缺必需参数；当前测试断言仍判为通过。因此这项回归不能证明修复有效。

同时，该测试通过子进程运行真实 backup/restore 入口，未模拟 Compose 或业务派发。解析成功后 backup 会尝试 `docker compose exec ... pg_dump`，失败、Docker 不可用或配置不完整都可能被上述断言当成成功。它并不是纯粹的无 daemon 解析测试。当前测试 env 缺少完整 Compose 必需变量，本轮没有执行这些命令，也不据此声称实际连接过引擎。

修复建议：模拟 cmd_backup/cmd_restore（或提取可单独调用的解析函数），断言四组参数完整、调用目标正确；模拟或禁止任何 Docker 执行；缺参必须退出 2；把原版解析器作为负向对照时应失败。真正的 Docker 集成测试独立运行并要求操作实际成功，不能用任意异常作为解析成功的证据。

本轮独立模拟验证了两种参数顺序 × backup/restore，共四组均正确派发，项目名、env 路径、恢复目标及 dump 参数均正确。因此 R3 的实现修复可以关闭；R5 针对交付的回归质量与执行边界。

## 上轮问题复核

| 问题 | 本轮结果 | 独立证据 |
| --- | --- | --- |
| R1 普通 DATABASE_URL 被默认测试采用 | 关闭该缺陷 | 默认分支无条件指定本次临时 SQLite；真实 fixture 子进程回归通过，普通连接未被采用；显式测试连接生效；不可用 PG 失败 |
| R2 Compose 仍加载日常 .env | 关闭该缺陷 | 仓库内生成 env 后，仅运行 daemon-free config --no-env-resolution；backend/migrate 的完整解析路径均等于生成文件绝对路径 |
| R3 文档顺序无法解析 | 关闭该缺陷 | 四组隔离派发探针全部通过，禁止 Compose.run；不是以 Docker 报错推断解析成功 |

上述结论只覆盖原问题，不代表所有显式 TEST_DATABASE_URL 目标都具备所有权校验，也不代表容器环境已实际启动验证。

## 独立执行记录

1. Windows / 项目现有 Python 虚拟环境：

   `python -m pytest backend/tests agent/tests -q --basetemp runtime/t02-review-round2/pytest --deselect backend/tests/test_compose_backup_cli.py::test_backup_cli_accepts_documented_argument_order`

   **84 passed, 1 deselected, 3 warnings，228.55 秒**。未设置 TEST_DATABASE_URL，TEMP/TMP 指向本次 runtime 临时目录。排除项的原因和替代验证见 R5。警告为 2 条既有依赖弃用和 1 条既有 pytest cache 写入权限警告；没有隐藏它们，不据此扩大修复范围。

2. `npm --prefix frontend run build`：**通过**（TypeScript + Vite）。
3. 独立探针 `runtime/t02-review-round2/probe.py`：Compose 完整路径 2/2、CLI 隔离派发 4/4 通过；R4 仓库外路径失败、R5 原版负向对照被错误放行均成功复现。探针使用一次性文件名，重新执行应换用新临时目录，避免生成器拒绝覆盖。
4. 没有调用本机 Docker 引擎、重启 Docker Desktop 或使用实际开发数据库。Compose config 仅解析配置，未输出密码或完整 DSN。

原始证据均忽略于 Git：`runtime/t02-review-round2/pytest.txt`、`frontend-build.txt`、`probe-results.json`、`probe.py`。

## 远端验收进度与下一步

用户已提供远端 Docker Engine 29.3.0 / Compose 5.1.0 正常运行，以及 postgres:17-alpine、python:3.14-slim、node:24-alpine、nginx:1.28-alpine 拉取成功的输出。服务器为 2 核 2GB，最后显示约 913MiB available、42GB 可用磁盘；短时 vmstat 未见持续换页。上述是用户提供的服务器准备证据，不是本审计者远程执行，也不代表应用已部署。

实现方先只修复 R4/R5 并更新交付报告，不重写业务 API。随后按 [远端操作说明](../T02-remote-server.zh-CN.md) 上传确定版本、串行构建并启动隔离栈，保留原有 napcat/astrbot。需要补齐：当前版本 PG + Alembic 套件、旧库升级、同源页面/API 与 SPA 路由、重启保留数据/密码、恢复到第二空测试库并核对项目/历史/观察序号/撤销权限及旧 revision 409。现有旧提交 PG 73 项记录不能代替当前 HEAD 的复验。

此轮无需为上述两项修复增加服务器配置或更换服务器。T02 的最终 accepted 仍取决于代码检查与远端运行验收都完成。
