# T01 独立审计 · 2026-09-19

> 最新结论见 [第二轮独立审计](T01-review-round2.md)：交付 HEAD `a9e6d12`，仍为 changes_requested，剩余 1 项 P1。以下保留首轮审计记录。

## 结论：changes_requested

78 项现有测试和前端生产构建通过，但独立验证发现两项必须修复的问题：保存期间继续输入会丢失草稿；历史 API 的时间没有明确 UTC 时区。暂不整合 main，不启动 T02。此结论只针对下列提交，不自动覆盖后续修复。

- 审计者：Codex；实现者：Claude Code / Kimi。
- 分支：`codex/task-01-history`。
- 基线：`7e4c4a0828045547c373c8f47a39ec8ac10beafb`。
- 最后代码提交：`36983911599dc87c08329617ed4ad1e72e79ab0a`。
- 被审计交付 HEAD：`c78495007ea85a684c9d08812654da79cd2978a1`。
- 开始审计时工作树干净，基线为交付 HEAD 的祖先。审计报告另行提交，不修改上述被审计代码。

## 必须修复

### R1 · P1：保存成功会清除请求发出后的新输入

位置：[Workspace.tsx](../../../frontend/src/research/Workspace.tsx)，`ProjectDetail` 的 `save.onSuccess`，489–494 行；输入控件在请求期间仍可编辑。

成功回调无条件 `setDraft(null)`。如果用户提交 A 后、响应返回前继续输入 B，回调会把 B 一并清除，界面显示已保存的 A。B 既未进入请求，也未进入历史，构成实际内容丢失。

独立浏览器复现（隔离 SQLite、生产构建、隔离端口 8027）：

1. 仅在测试服务外层延迟项目 PUT 响应 4 秒，应用代码不变。
2. 将“当前进展”填写为 `AUDIT_SENT`，点击“保存进展”。
3. 在“保存中…”按钮禁用期间，把同一输入框改为 `AUDIT_TYPED_WHILE_SAVING`；浏览器确认新文本已进入输入框。
4. 响应成功后，版本变为 2，输入框恢复为 `AUDIT_SENT`，后输入的内容消失。

修复可选择在请求期间禁用全部相关编辑控件，或识别提交时的草稿版本、保留后续输入并正确推进其版本基线。不能只禁用保存按钮。若保留后续输入，应同时处理查询缓存刷新与提交结果，避免显示旧缓存或让第二次保存使用错误 revision。

验收：增加可重复的延迟响应回归验证；覆盖提交后的继续输入不会丢失，且后续保存使用正确基线。已有 409/网络失败保留草稿的行为须继续成立。

### R2 · P2：历史 API 时间字段缺少 UTC 标记

位置：[research_models.py](../../../backend/app/research_models.py)，`ProjectRevisionPublic.recorded_at` / `project_updated_at`，94–95 行。

SQLite 读取后的无时区 datetime 直接序列化，历史 API 返回例如：

```json
{
  "recorded_at": "2026-09-18T18:30:31.244783",
  "project_updated_at": "2026-09-18T18:30:31.240692"
}
```

两个字段都没有 `Z` 或 UTC offset，不满足 T01 的“API 明确为 UTC”契约。当前网页补加 `Z` 的展示处理不能修复 API 契约，其他客户端也无法从响应本身判断时区。

修复应在模型/响应边界明确转换为 UTC：确认数据库既有无时区值的 UTC 语义后补上时区；已有时区值转换为 UTC，不能简单替换其 offset。无需为此提前扩大到 T02 的 PostgreSQL 部署。

验收：针对 `created`、`updated`、`migrated_baseline` 的实际 HTTP 历史响应，检查两个字段均携带 UTC 时区且保留正确时间含义。只比较两个无时区字符串相等不足以证明契约成立。

## 非阻断改进

- C1：[Workspace.tsx](../../../frontend/src/research/Workspace.tsx) 第 713 行提示“或直接保存覆盖”，但旧基线再次提交仍返回 409；改为实际支持的查看、采用最新内容并重新编辑路径。不要为匹配文案新增强制覆盖功能。
- C2：[architecture.md](../../architecture.md) 中仍保留未实现完整修订历史的旧范围描述。请区分已交付的项目状态快照与尚未实现的完整研究日志，使架构说明与当前范围一致。

## 独立验证证据

| 检查 | 结果与范围 |
| --- | --- |
| 后端及 Agent 测试 | 78 passed，2 条现有弃用警告，67.65 秒；Windows / Python 3.14.6，隔离临时 SQLite 和 Git 仓库 |
| 前端生产构建 | TypeScript + Vite 构建成功 |
| 迁移测试 | 上述 78 项中包含 4 项迁移测试，覆盖基线回填、重复升级、回退再升级及空库等既有断言 |
| 实际历史插入失败 | 用 SQLite BEFORE INSERT trigger 主动拒绝历史写入；更新返回 500 后项目内容/revision/历史不变，新建失败不留孤立项目，通过 |
| 同基线并发 | 在两个请求均完成项目读取后用 barrier 同步放行；结果为一个 200、一个 409，历史为 [2, 1]，通过 |
| 历史时间格式 | 两个字段均缺少 UTC 时区，失败，见 R2 |
| 保存期间继续输入 | 独立浏览器稳定复现新输入被成功回调清除，失败，见 R1 |
| 409 与后台刷新 | 浏览器保留本地草稿，另一个客户端推进服务端版本；旧基线保存返回 409 后，最新项目重新获取，本地草稿仍在，通过 |

执行命令：

```powershell
# 在 research-manager 根目录，使用已有虚拟环境；每次使用新的临时目录。
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$reviewTemp = Join-Path (Get-Location) ('runtime/t01-review-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q --basetemp=$reviewTemp -p no:cacheprovider
npm.cmd --prefix frontend run build
```

实际测试临时目录为 `runtime/t01-review-d5a156ce76ad42be9d65d8fb4d379a58`。不要重复使用已有数据目录作为 pytest basetemp。

额外失败注入、并发及浏览器延迟响应验证使用一次性审计脚本和隔离数据，不修改产品代码，不连接用户开发库。修复方可直接按本报告步骤重现，不依赖审计者工作区里的临时脚本。浏览器测试服务已停止。

实现报告中的其他浏览器场景并未全部独立重跑；本报告不把实现者的验证声明当作独立通过证据。网络失败场景未完成最终结果确认，不计入独立通过项。PostgreSQL、Docker、HTTPS、云部署与备份恢复不在本轮实际运行验证范围，仍归 T02。

## 给 Claude Code / Kimi 的修复交接

1. 留在 `codex/task-01-history`，先读本报告、T01 任务卡及现有实现报告；按 R1、R2 修复并补有意义的回归验证。C1、C2 可一并修正。
2. 追加提交，不 squash，不修改本审计报告为 accepted，不自行整合 main，不启动 T02。
3. 更新 `T01-implementation.md`，逐项回应问题、填写新的最后代码 SHA 和实际验证证据；更新状态为待复审。不要把旧的审计结论套用到新代码。
4. 交付含修复报告的最终 HEAD，由用户发起下一轮独立复审。

本轮审计只更新报告和协作状态，不代替实现方修复。实际 token 与金额没有可核验计费数据，记为 unknown；首轮阻断问题数为 2，修复轮数待后续统计。
