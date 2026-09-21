# T03 第二轮独立审计 · 2026-09-21

## 结论：changes_requested；两项 P2 待修复

首轮 R1 改名冲突恢复、R2 分组移动丢失选择的原始复现已通过；R3 只统一了状态码，错误正文仍泄漏目标仓库是否存在。新增 R4：面板级关联对话框的版本下限未按副本隔离，连续编辑不同副本可导致冲突恢复失败。未发现成功越权关联或读取其他账户仓库内容的证据。

- 被审计 HEAD：`e99cad705ced16252f199351acf375b7a34ce277`，分支 `codex/task-03-repository-identity`。
- 实际 base / main：`62cb7f177ccf2c612783b284b4ac4b9c7d29c73c`。首轮审计文档提交 `9c29234` 为本轮增量起点，修复为其后的单个提交，涉及 7 个文件。
- 开始及测试结束时工作树干净；本轮不修改实现，只提交独立报告与交接状态。不整合 T03，不推送，不启动 T04。
- T02 提前整合的授权例外沿用首轮记录；本审计不把该例外视为远端运行验收通过。

## R3（部分修复）· P2：404 的错误正文仍能区分跨账户仓库与不存在仓库

位置：`backend/app/api/routes/research.py:198–206` 的 `require_repository`，由用户绑定入口第 277 行和设备登记入口第 381 行复用。

不存在的 Repository 直接返回 `404 {"detail":"仓库不存在"}`；真实但属于其他账户的 Repository 则进入 require_project，返回 `404 {"detail":"项目不存在"}`。因此虽然原 404/422 差异消失，调用者仍可用响应正文判断给定 UUID 是否存在，违反任务卡 §4 的“不泄漏存在性”。该问题也影响复用此函数的仓库改名入口。

独立证据：全新 SQLite 中，用普通账户（非管理员）操作自己的副本，分别传入另一账户的真实仓库 UUID 与随机不存在 UUID。用户 PUT `/copies/{id}/repository` 和设备 POST `/agent/copies` 均返回上述两个不同正文。四个请求均为 404，没有发生成功越权写入。

修复要求：将目标仓库不存在和无所有权统一为相同的对外状态码及错误正文，之后再区分本账户另一项目的 422；避免将底层项目授权错误直接暴露为仓库查找结果。扩展本次新增的授权分层回归，比较完整错误 JSON，而非只断言 status_code，并核对拒绝后无数据变更。

## R4（新增）· P2：不同副本共用版本下限，冲突后无法正确采用基线

位置：`frontend/src/research/Workspace.tsx:657–671`；采用基线在第 706–713 行。

CopyBindingDialog 保持在面板中，floor ref 会一直保留。copyId 切换时只重置 base 和 target，没有将 floor 重置/关联到新 copyId；之后使用 Math.max，使较高版本的旧副本污染低版本的新副本。采用最新基线因此可能采用另一个副本的 binding_revision。

真实浏览器复现（同一项目页面内，不刷新整个页面）：

1. 第一份副本 `C:/audit/UI` 初始在仓库 A、版本 1；打开对话框选择 C，另一会话通过 API 改到 B、版本 2。
2. 本会话提交发生冲突；对话框仍在且 C 选择保留，点击“采用最新基线（保留选择）”后提交成功，第一份副本到 C、版本 3。此步骤证明原 R2 的具体丢选择问题已修复。
3. 打开另一份副本 `C:/audit/UI-second`（A、版本 1），选择 C；另一会话将这份副本改到 B、版本 2。
4. 本会话冲突后点击采用最新基线，再次确认关联，仍留在冲突提示中；采用按钮随后 disabled，C 选择仍在。独立 GET 确认第二份副本仍为 B、版本 2，第一份仍为 C、版本 3。

结合源码，步骤 4 的 base 被前一份副本遗留的 floor=3 覆盖；新副本实际版本为 2，因此重试不能成功。刷新整个页面或关闭重开可绕开某些表现，但不是保留选择的正常冲突恢复路径。

修复要求：按副本 UUID 隔离当前值与版本下限；切换编辑对象时原子初始化对应状态，不能继续用旧对象的 current 更新新对象的 floor。保留稳定层对话框和显式确认，不移除后端版本校验。增加真实交互回归：先编辑高版本副本，再编辑低版本副本，后者发生并发冲突，采用其自身最新基线后成功提交；同时覆盖关闭重开、切换项目及未归类分组，确保不串用版本或选择。

## 已验证修复与回归

- R1 原始复现通过：改名对话框内输入 `My retained draft`；第二会话改为 External Rename/revision=2；冲突后显示最新名称，显式采用新基线，成功保存草稿；独立 GET 为草稿名称/revision=3。
- R2 原始复现通过：跨分组刷新不再卸载对话框，选择 C 保持；显式采用版本 2 后写入版本 3。R4 是连续编辑不同对象时的新缺陷。
- R3 状态码分层测试通过，但完整响应不一致，未关闭。
- 首轮非阻断项：修改文件 Ruff 全部通过；双 Agent 冒烟脚本重跑退出 0；Agent 无 `--repository` 重复登记的返回文案回归包含在完整测试中。

独立执行：

```powershell
$env:TEST_DATABASE_URL=''
$env:TEST_SCHEMA_FROM_MIGRATIONS=''
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q --basetemp runtime/t03-review-round2/pytest -p no:cacheprovider
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m ruff check backend/app/api/routes/research.py backend/tests/api/routes/test_repositories.py agent/research_agent/cli.py agent/tests/test_cli_repositories.py scripts/audit/t03_smoke.py
.\.venv\Scripts\python.exe scripts/audit/t03_smoke.py
```

结果：**111 passed，2 条既有弃用警告，248.62 秒**，无 skip/deselect；TypeScript/Vite 构建、上述 Ruff 和 Windows 两套隔离 Agent 的真实 HTTP 登记/扫描冒烟通过。浏览器使用本次生产构建和全新 Alembic SQLite，仅绑定 loopback；所有账户、设备与目录均为一次性测试数据。附加 SQLite 账户/项目级联删除探针通过。

证据位于被忽略的 `runtime/t03-review-round2/`：pytest.txt、backend-probe-results.json、browser-evidence.json、隔离探针与 app-state.json。测试账户凭据仅留在被忽略的临时脚本，不进入交接文档或提交。

## 未验证项与下一步

没有重试本机 Docker。真实 PostgreSQL 并发与迁移、远端容器/重启/备份恢复，以及 Linux CLI 冒烟仍未独立验证。浏览器本轮覆盖上述成功/冲突路径，未完成全部网络失败、延迟旧响应、未归类迁移与 T01 UI 回归组合；不能据此宣称 A11 全通过。

实现方在现有 T03 分支修复 R3/R4，补充能暴露问题的回归与实际结果，再交复审；不重复开发已关闭的原始 R1/R2。代码问题全部关闭后，若必需运行证据仍缺失，整体状态应为 blocked_environment，而非 accepted。

成本：模型 token/缓存/费用未取得，均为 unknown，不以测试耗时估算。
