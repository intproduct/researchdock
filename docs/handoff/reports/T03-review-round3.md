# T03 第三轮独立审计 · 2026-09-22

## 结论：blocked_environment；R1–R4 已知代码问题全部关闭

最新修复中的 R3、R4 均通过独立复验。本轮未发现新的阻断代码缺陷，可以进入远端运行验收；但任务卡要求的真实 PostgreSQL 并发/迁移与 Linux CLI 冒烟仍缺证据，因此不是 accepted。部分 A11 异常时序组合也尚未完成独立验证，详见覆盖边界。

- 被审计 HEAD：`80b2102a65a6477a4f2cd341a93494a26d440b16`。
- 分支：`codex/task-03-repository-identity`。
- 实际 base / main：`62cb7f177ccf2c612783b284b4ac4b9c7d29c73c`。
- 增量起点：第二轮审计提交 `6f3f76f`，已验证是 HEAD 的祖先；后续单个修复提交涉及 4 个文件。
- 测试执行于 2026-09-21，报告于 2026-09-22 落盘。开始及测试结束时工作树干净。本轮只提交审计与交接文档，不修改实现、不合并 main、不推送、不开始 T04。

## R3 · 关闭：不存在与跨账户目标返回相同错误

`backend/app/api/routes/research.py` 的 require_repository 现在检查父项目所有权，并对不存在和无所有权两种情况返回相同的 `404 {"detail":"仓库不存在"}`。

独立使用全新迁移 SQLite、普通账户及其设备：用户 PUT `/copies/{id}/repository` 和设备 POST `/agent/copies` 分别提交另一账户真实仓库 UUID、随机不存在 UUID；四个响应均为上述状态及正文，完整 JSON 比较通过。现有授权分层回归另覆盖同账户其他项目 422、同项目成功，以及用户拒绝后副本关联和版本不变。不存在成功越权绑定的测试结果。

新增测试已比较完整错误正文，能阻止第二轮只统一 status_code 的修复再次回退。

## R4 · 关闭：编辑状态按副本隔离

`frontend/src/research/Workspace.tsx` 的 CopyBindingDialog 将 id、target、base、floor、conflict 合并为按 copy ID 初始化的状态对象；切换对象时同时重置基线和版本下限，同一对象的新 revision 才能提高 floor。

真实浏览器使用最新生产构建，连续操作同一项目页面、没有通过整页刷新清空状态来绕过问题：

1. 第一份副本起始为 A/version=1；对话框选择 C，第二会话改到 B/version=2。提交旧版本返回 409，对话框及 C 选择保留。显式采用最新基线后，请求携带 version=2，返回 200，第一份到 C/version=3。
2. 紧接着编辑第二份副本（A/version=1），选择 C；第二会话改到 B/version=2。旧版本提交返回 409；采用最新基线后的真实请求携带该副本自己的 version=2，返回 200。对话框关闭，仓库 C 下显示两份副本。
3. 关闭后重新打开第二份副本，选择值为刚保存的 C，没有串入其他对象的选择。

服务端隔离审计日志记录实际请求版本及响应状态，确认成功不是移除版本校验或误用前一份副本的 version=3。原 R2 的分组移动草稿保护同时再次通过；R1 原始改名复现沿用第二轮通过结论，本轮未改动该组件，也未重复完整改名 UI 测试。

## 补充交互验证

- 第二份副本选择“未归类”时，对隔离服务的绑定 PUT 注入 HTTP 503。对话框仍在、空 repository 选择保留；解除故障后在原对话框重试，以 version=3 成功解绑到 version=4，网页未归类组显示该副本。
- 从未归类组打开第二份副本并选择 A；第二会话将其绑定 B/version=5。本会话 version=4 提交返回 409，分组刷新后对话框和 A 选择仍在；明确采用最新基线后以 version=5 提交返回 200。
- 503 是应用请求失败模拟，不等于实际断网、TCP 中断或超时测试。

## 独立检查与证据

```powershell
$env:TEST_DATABASE_URL=''
$env:TEST_SCHEMA_FROM_MIGRATIONS=''
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q --basetemp runtime/t03-review-round3/pytest -p no:cacheprovider
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m ruff check backend/app/api/routes/research.py backend/tests/api/routes/test_repositories.py
git diff --check
```

- 完整回归：**111 passed，2 条既有弃用警告，220.78 秒**，无 skip/deselect。
- TypeScript/Vite 生产构建通过，增量 Ruff 与 diff 空白检查通过。
- 上述普通账户/设备权限探针和真实浏览器关联验证通过。附加 SQLite 用户/项目删除级联探针通过。
- 本轮 Agent 与迁移没有增量改动；完整 pytest 覆盖其回归，未重复独立 Windows 双 Agent HTTP 冒烟，相关既有证据见第二轮报告。
- 临时测试服务仅监听 loopback，采用全新 Alembic SQLite、一次性账户、设备及目录，不触碰开发数据库或用户工作仓库。

原始证据在忽略目录 `runtime/t03-review-round3/`：pytest.txt、backend-probe-results.json、binding-events.jsonl、browser-evidence.json 和隔离探针。日志未记录 Token；临时脚本与状态不提交。首次审计服务启动因测试中间件注册时机错误退出，调整临时探针初始化顺序后重建隔离库通过；这不是应用缺陷。

## 覆盖边界与后续交接

尚未验证：

1. A05：真实 PostgreSQL 下并发改绑与观察交错。
2. A10：真实 PostgreSQL 空库、T02 旧数据迁移及回退再升级。
3. A13：Linux 的独立 CLI 冒烟；本轮 Windows 冒烟证据未新增。
4. A11 剩余组合：旧响应延迟到达、真实断网/超时、请求在途时切换编辑对象/项目，以及完整 T01 UI 回归。不能把本轮的冲突与 503 检查写成 A11 全通过。
5. T02 遗留的远端容器启动、重启及备份恢复证据。

本机 Docker 未重试。实现报告所记 T02 提前推进例外不替代以上证据，也不构成本审计自行继续 T04 的授权。

下一步在确定的 T03 提交上补上述证据：按 [T02 远端说明](../T02-remote-server.zh-CN.md) 建立隔离验收环境，使用专用 TEST_DATABASE_URL 和 TEST_SCHEMA_FROM_MIGRATIONS=1，记录实际 dialect、提交 SHA、命令、退出码及完整日志。补 A11 尚未覆盖时序交互；无需重复实施已关闭的 R1–R4。证据齐备后提交复审，再决定 accepted 与本地整合。

实现报告仍保留早期“尚未独立审计”“A11 浏览器未执行”等历史文字，应按轮次理解；最新验收事实以本报告与 status 为准。

成本：本轮输入、缓存、输出 token 及费用不可取得，均为 unknown，不由耗时估算。
