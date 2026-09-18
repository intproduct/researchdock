# T01 实现报告

- 状态：ready_for_review（首轮 changes_requested 的 R1/R2/C1/C2 已修复；第二轮 changes_requested 的 R1 续项已修复，等待第三轮复审）
- 任务卡：docs/handoff/TASK-01-history.zh-CN.md
- 分支：codex/task-01-history
- 实际 base SHA：7e4c4a0828045547c373c8f47a39ec8ac10beafb
- 最后代码提交 SHA（此报告提交之前）：6712ded8c94825b26ecb52fdaf62c61ddc084d9d
- 首轮被审计交付 HEAD：c78495007ea85a684c9d08812654da79cd2978a1（对应审计 T01-review.md）
- 第二轮被审计交付 HEAD：a9e6d12fed458478ec6e13d775ff0423dc688473（对应审计 T01-review-round2.md）
- 执行平台/解释器/Node/数据库版本：Windows 11 / Python 3.14 / Node 26.5 / SQLite（开发与隔离测试），PostgreSQL 未执行
- 实际模型与服务来源（不知道写 unknown）：Kimi 后端（用户配置的 Claude Code 会话），其余 unknown

## 结果

用户保存进展后，现在能按时间倒序查看每次保存的完整快照与时间，并在另一处已更新时不丢失当前草稿。新建项目写入 revision=1 的 created 快照；每次成功 PUT 在与项目更新同一事务内追加一条 updated 快照；条件更新加 (project_id, revision) 唯一约束保证并发下只有一个基线请求成功，失败请求不追加历史、不回写内容。详情页新增可展开、可翻页的历史面板，409 时保留草稿并提供“查看最新/采用最新”操作。历史时间字段以明确 UTC 返回。

本包未实现独立研究日志、撤销/恢复版本、diff/搜索、Git 同步或 AI 总结。

主要修改文件及原因（不粘贴整个 diff）：

| 文件 | 原因 |
| --- | --- |
| backend/app/research_models.py | 新增 ProjectRevision 表、ProjectSnapshot、ProjectRevisionPublic、ProjectHistoryPage；修复 R2 的 UTC 归一化校验器 |
| backend/app/api/routes/research.py | create/edit 同事务写快照；新增 GET /projects/{id}/history；新增 record_revision 帮助函数 |
| backend/app/alembic/versions/b7f3a1c29e04_project_revision_history.py | 建表 + 已有项目基线回填，down_revision=d42026f707b5 |
| backend/tests/api/routes/test_history.py | 历史 API 与并发/回滚/权限/分页测试（9 项，含新增 R2 回归） |
| backend/tests/test_migration_history.py | 隔离 SQLite 上的迁移、幂等、downgrade/upgrade、schema 一致性（4 项） |
| frontend/src/research/api.ts | ApiError 携带 HTTP status；新增历史类型 |
| frontend/src/research/HistoryPanel.tsx | 可展开、可翻页的历史面板 |
| frontend/src/research/Workspace.tsx | 详情页草稿保留、baseRevision 固定、409 冲突与采用最新流程；修复 R1 保存期间新输入丢失；修正 C1 文案 |
| docs/architecture.md | 修复 C2：区分已交付的项目状态快照与尚未实现的完整研究日志 |

## 首轮审计问题逐项回应

审计报告：docs/handoff/reports/T01-review.md（结论 changes_requested）。修复提交：006902a（单次追加提交，未 squash）。

### R1 · P1：保存成功会清除请求发出后的新输入 —— 已修复

原因：`save.onSuccess` 无条件 `setDraft(null)`，而请求期间输入控件仍可编辑，导致提交后、响应前键入的内容被丢弃且从未进入历史。

修复（frontend/src/research/Workspace.tsx，ProjectDetail）：onSuccess 现在接收 mutation 的实际请求体 `body`，把它与当前 `draft` 逐字段比较：

- 若草稿与本次提交内容一致（用户未继续输入）→ 清空草稿，行为不变。
- 若不一致（保存期间有新输入）→ 保留草稿，不丢弃新文本。
- 两种路径都把 `baseRevision` 推进到 `saved.revision`，因此随后保存使用正确基线，不会因旧 revision 误报 409。

选择了“识别提交时的草稿版本、保留后续输入并推进基线”，而非“禁用全部编辑控件”。未新增“强制覆盖”功能。查询缓存 `projects` 与 `history` 仍照常 invalidate，避免显示旧缓存。

回归验证：

- 可重复脚本 `runtime/verify_t01_browser.mjs`（Playwright + 本机 Chrome，隔离后端 :8011 + 隔离前端 :5183 + 独立 SQLite）：用 `page.route` 延迟项目 PUT 响应，提交 `R1_SENT` 后在“保存中…”期间键入 `R1_TYPED_WHILE_SAVING`，放行响应。结果：保存成功后输入框仍为 `R1_TYPED_WHILE_SAVING`；随后在该草稿上再次保存成功（走新基线）。
- 判别性验证：把 Workspace.tsx 换回被审计提交 3698391 的版本重跑同一脚本，得到与审计一致的现象——输入框从 `R1_TYPED_WHILE_SAVING` 回退为 `R1_SENT`（新输入丢失）；换回修复版后恢复通过。证明该脚本确实能捕获 R1，而非恒真断言。
- 原有 409 保留草稿行为的回归仍成立：同一脚本的两个会话冲突流程通过（409 后草稿保留、采用最新后保存成功）。
- 网络失败保留草稿未单独端到端验证，标为未验证，见“阻塞和未解决事项”。

### R2 · P2：历史 API 时间字段缺少 UTC 标记 —— 已修复

原因：列为 `DateTime(timezone=True)`，但 SQLite 读回无时区的 datetime（值为 UTC 墙钟），DTO 直接序列化，于是 HTTP 返回 `2026-09-18T18:30:31.244783` 这类无 `Z`/offset 的字符串。

修复（backend/app/research_models.py，ProjectRevisionPublic）：新增 `field_validator("recorded_at", "project_updated_at", mode="before")`，在响应边界统一归一化到 UTC：

- 无时区值 → 视为 UTC 墙钟并补上 `tzinfo=UTC`（不改动数值，不错误位移）。
- 已有时区值 → `astimezone(UTC)` 转换（不简单替换 offset）。

依据：`get_datetime_utc()` 与迁移回填写入的均为 UTC，所以给无时区值贴 UTC 标签是正确的语义；没有把该问题扩大到 T02 的 PostgreSQL 部署。

回归验证：

- 新增后端测试 `test_history_timestamps_carry_utc_for_every_origin`：覆盖 created、updated、migrated_baseline 三种 origin，断言两个时间字段都带 UTC offset；并断言一条写入为无时区 12:00（模拟迁移产生的值）的基线，经 API 返回后解析出的 UTC 瞬间仍是 12:00，以证明“不是改成了本地时间”。
- 先建立失败基线：修复前该测试失败，报 `AssertionError: 2026-09-18T18:53:18.360114`（无 Z），与审计报告一致；修复后通过。
- 真实 HTTP 校验：对隔离后端 `GET /projects/{id}/history` 的实际响应，三个 origin 的两个字段均形如 `2026-09-18T19:04:01.966875Z`，保留正确瞬间。
- 说明：`Project` 自身响应（POST/PUT /projects）的 `updated_at` 仍是无时区字符串——任务卡要求“不变更现有 POST/PUT 响应结构”，故未改动；历史 DTO 与项目的比较在测试里改为按瞬间比较。

### C1 · 非阻断：无依据的“直接保存覆盖”提示 —— 已修复

Workspace.tsx 冲突提示原文“可以……或直接保存覆盖”不成立：旧基线再次提交仍返回 409。已改为不承诺覆盖。第二轮审计又指出“继续编辑自己的草稿，请采用最新内容后再保存”仍不准确（采用最新会丢弃草稿），本轮一并改为“要在此基础上继续，请采用最新内容（会丢弃当前草稿）后重新编辑并保存”。未为匹配文案新增覆盖功能。

### C2 · 非阻断：architecture.md 范围描述过期 —— 已修复

docs/architecture.md 原先写“does not yet preserve a full revision history”。已改为明确区分：已交付的是可编辑项目字段的状态快照历史（含无 undo/restore、diff、自由研究日志的说明），完整研究记忆与溯源知识编译仍为 planned separately。

## 第二轮审计问题回应

第二轮审计报告：docs/handoff/reports/T01-review-round2.md（结论 changes_requested，剩余 1 项 P1）。修复提交：6712ded（追加，未 squash）。

### R1 续项 · P1：慢刷新期间用旧缓存内容 + 新 revision 覆盖刚保存的状态 —— 已修复

原因（审计复现）：PUT 成功后 `setDraft(null)` 且 `baseRevision=saved.revision`，但 `project` 仍来自尚未刷新完的列表缓存；表单回退为缓存中的旧内容、修订号却已前进，再次保存把旧字段和新 revision 一起提交，后端接受并覆盖刚保存的进展。

修复（frontend/src/research/Workspace.tsx，ProjectDetail，不改 API 同内容仍递增 revision 的契约）：

1. `save.onSuccess` 在清空已提交草稿之前，先用 PUT 返回的 `saved` 对象 `cache.setQueryData(["projects"], …)` 更新列表缓存：把该 id 的项目替换为 saved。这样即使列表 GET 尚未返回，表单也始终显示刚保存的内容，而不是回退到旧缓存。
2. 新增按项目隔离的 `floorRevision`（`useRef`，随渲染取“渲染出的 project.revision 与已保存 revision 的较大者”，切换项目时重置，避免把一个项目的下限带进另一个项目）。
3. 列表 `queryFn` 获取结果后，若其中当前项目的 revision 小于 `floorRevision`（说明该 GET 在本次保存前发出、数据偏旧），则保留本地已应用的较新状态、不覆盖，直接返回修正后的列表；其余项目照常更新。
4. 保存后仍后台 `refetch()` 列表以对账，但已被上述下限保护，不会把表单拉回保存前。

回归验证（runtime/verify_t01_round3.mjs，Playwright + 本机 Chrome，隔离后端 :8011/前端 :5183/独立 SQLite）：

1. 保存一次使项目稳定在 revision=2（内容 `R3_STEP1`）。
2. 用 `page.route` 暂缓列表 `GET /projects`（仅第一个，PUT 与历史 GET 正常），把进展改为 `R3_COMMITTED_WITH_SLOW_REFRESH` 并保存，期间不再输入。
3. PUT 成功产生 revision=3，但列表 GET 仍在等待。此时输入框保持 `R3_COMMITTED_WITH_SLOW_REFRESH`，界面显示“当前修订 3”——没有回退。
4. 不修改输入框，再次保存成功。独立 HTTP 读取历史确认为 revision 3、4 均为 `R3_COMMITTED_WITH_SLOW_REFRESH`，revision 2 为 `R3_STEP1`，没有任何旧内容被回写。
5. 放行列表 GET，界面仍一致。
6. 判别性对照：把 Workspace.tsx 换回第二轮被审计提交 a9e6d12 的版本重跑同一脚本，输入框在慢刷新期间回退为 `R3_STEP1`、修订显示 2（复现 R1 续项）；换回修复版后恢复通过。证明该脚本有判别力。
7. 首轮 R1（保存期间继续输入）与 409 冲突保留草稿回归：重跑 runtime/verify_t01_browser.mjs 全部通过，未回归。

未改变：API 相同内容 PUT 仍递增 revision（见历史 revision 2→3→4，内容为重复值也正常落库）；409 保留草稿；后台刷新不覆盖草稿。

## 契约核对

| 任务卡验收项 | 结果 | 证据 |
| --- | --- | --- |
| 新建项目返回 revision=1，只有一条对应快照 | 通过 | test_create_records_single_created_snapshot |
| 更新到 2/3 后历史降序、每条内容正确；重复旧请求 409 且没有第四条历史 | 通过 | test_updates_append_descending_history_and_409_adds_nothing |
| 两个独立请求使用相同基线，只一个成功（非串行冒充） | 通过 | test_concurrent_same_baseline_only_one_succeeds（ThreadPoolExecutor 并发） |
| 历史插入失败回滚 Project 内容与 revision；新建失败不留孤立项目 | 通过 | test_history_insert_failure_rolls_back_project_update；test_create_failure_leaves_no_orphan_project |
| 外账户/匿名/设备凭据权限隔离，伪造 actor 不生效，非法分页参数被拒绝 | 通过 | test_history_permissions_and_forged_fields |
| 分页无重复遗漏；加载下一页期间新增 revision 不破坏向旧版本翻页 | 通过 | test_history_pagination |
| 已有 revision>1 项目迁移仅产生当前基线；二次 upgrade 幂等；隔离库 upgrade/downgrade/upgrade | 通过 | test_migration_history.py（4 项）+ 开发库副本 upgrade 仅补一条基线 |
| 两会话冲突、背景刷新保留草稿；明确采用最新后能正常保存 | 通过（本轮重跑） | runtime/verify_t01_browser.mjs：冲突保留草稿、采用最新、再保存成功、无 pageerror |
| 网络失败保留草稿 | 未执行 | 未对真实断网做端到端确认；仅代码路径核实（api() 捕获 fetch 异常抛 ApiError(0)，非 409 分支不动草稿），见“阻塞和未解决事项” |
| 保存期间继续输入不丢失，后续保存使用正确基线（审计 R1 验收） | 通过 | runtime/verify_t01_browser.mjs 延迟 PUT；对照旧代码可复现丢失 |
| 历史响应两个时间字段均带 UTC，且保留正确时间含义（审计 R2 验收） | 通过 | test_history_timestamps_carry_utc_for_every_origin；真实 HTTP 响应含 `Z` |
| 原 66 项回归仍通过，新测试有实质断言；前端生产构建通过 | 通过 | 全套 79 passed；npm build 成功 |
| 历史页面可实际操作，有浏览器结果或可重复的人工步骤 | 通过 | 脚本 + 截图为可重复步骤 |

## 执行记录

| 工作目录与完整命令（去掉秘密） | 环境/实际数据库 | 退出码与测试数量 | 结果 |
| --- | --- | --- | --- |
| `python -m pytest backend/tests agent/tests -q --basetemp=<repo>/runtime/tmp/pytest -p no:cacheprovider` | Windows / Python 3.14 / 隔离临时 SQLite | 0，79 passed | 全绿（原 66 + T01 新增 13，其中 1 项为 R2 回归） |
| `python -m pytest backend/tests/api/routes/test_history.py -q` | 隔离 SQLite | 0，9 passed | 含 R2 回归；修复前该新测试失败 |
| `python -m pytest backend/tests/test_migration_history.py -q` | 4 个独立临时 SQLite 文件 | 0，4 passed | 基线回填、幂等、downgrade/upgrade、schema 一致 |
| `npm run build`（frontend） | Node 26.5 / Vite 8 | 0 | tsc + vite 生产构建成功 |
| `npm run check` + `npx biome lint ./src/research`（frontend） | Node 26.5 | 0，3 files | tsc 无错；research 文件 lint 通过 |
| `python -m ruff check <changed backend files>` | Python 3.14 | 0 | 全部通过 |
| 隔离后端（uvicorn :8011，独立 SQLite）+ 前端（vite :5183）+ `runtime/verify_t01_browser.mjs` | 隔离库 + 本机 Chrome | 0 | R1 保留新输入、后续保存成功、409 保留草稿、采用最新后保存成功、无 pageerror |
| 对照实验：同一脚本跑被审计提交 3698391 的 Workspace.tsx | 同上 | — | 输入框回退为 `R1_SENT`，复现 R1；证明回归脚本有判别力 |
| 真实 HTTP 时间字段抽查（python urllib 请求 :8011 历史接口） | 隔离 SQLite | 0 | 三种 origin 两字段均为 `...Z` |
| 隔离后端 + 前端 + `runtime/verify_t01_round3.mjs`（慢 GET 回归，第二轮） | 隔离库 + 本机 Chrome | 0 | 慢列表 GET 期间表单保持刚保存内容与修订 3，再保存不回写旧内容，放行后一致，无 pageerror；HTTP 历史确认 rev3/4 为新内容、无旧内容回写 |
| 对照实验：同一脚本跑第二轮被审计提交 a9e6d12 的 Workspace.tsx | 同上 | — | 慢刷新期间输入框回退为 `R3_STEP1`、修订显示 2，复现 R1 续项；证明回归脚本有判别力 |

UI 操作步骤及可观察结果（R1 复现，与审计报告步骤一致）：

1. 登录（verify@example.com）→ 新建“T01 回归项目”并打开详情。
2. 当前进展填 `R1_SENT`；测试脚本在外层延迟项目 PUT 4 秒（不改产品代码）。
3. 在“保存中…”期间把输入框改为 `R1_TYPED_WHILE_SAVING`。
4. 放行响应、提示“研究进展已保存”后，输入框仍显示 `R1_TYPED_WHILE_SAVING`（修复前会变回 `R1_SENT`）。
5. 再次保存成功；随后两会话冲突流程仍保留草稿并能采用最新后保存。截图 runtime/tmp/t01-regression.png。
6. 可重复方式：先在隔离端口起后端（8011）与前端（5183），再执行 `node runtime/verify_t01_browser.mjs`；脚本内模块需从 frontend 目录解析，实际执行时从 `frontend/` 下运行同一文件。

慢刷新回归（第二轮 R1 续项）步骤及可观察结果：

1. 新建“R3 慢刷新项目”→ 保存一次，项目稳定在 revision=2，内容 `R3_STEP1`。
2. 测试脚本用 `page.route` 暂缓第一次列表 `GET /projects`（PUT 与历史 GET 正常放行），把进展改为 `R3_COMMITTED_WITH_SLOW_REFRESH` 并保存（期间不再输入）。
3. PUT 成功产生 revision=3、列表 GET 仍被阻塞时：输入框仍为 `R3_COMMITTED_WITH_SLOW_REFRESH`，界面显示“当前修订 3”（修复前会回退为 `R3_STEP1`/修订 2）。
4. 不修改输入框再次点击保存 → 成功；HTTP 历史确认为 rev 3、4 均为新内容，没有旧内容被回写。
5. 放行列表 GET → 界面保持一致。截图 runtime/tmp/r3-slow-refresh.png。执行方式同第 6 条，脚本为 `runtime/verify_t01_round3.mjs`。

迁移/恢复验证：在临时目录新建 4 个独立 SQLite 文件，分别执行 `upgrade head`（空库）、`upgrade head` 两次（幂等）、`upgrade head` → `downgrade d42026f707b5` → `upgrade head`（恢复基线）、`upgrade head` 后核对表结构与模型元数据一致；另对开发库 research.db 的副本（runtime/tmp/devcopy.db）执行 upgrade，仅补一条 revision=2 的 migrated_baseline，不伪造缺失版本。**没有真实 PostgreSQL，未执行容器化迁移**，该项交由 T02。

## 设计决定与偏离

- 快照来源：更新后的快照取自本次校验通过的请求体，而非 identity map 中的旧 Project 对象；project_updated_at 用本次条件更新的时间戳。与任务卡一致。
- record_revision 只在调用方事务内 add 快照，不自行 commit，保证与项目更新原子。
- 前端移除 `form key={project.revision}` 的重挂载写法，改为草稿由组件状态持有并固定 baseRevision；409 后 onError 触发 projects.refetch() 以显示“最新修订号”，但不覆盖草稿。R1 修复没有改变这些既有行为。
- R1 采用“比较提交体与当前草稿”判定是否保留，而不是在请求期间禁用控件：保留用户输入优先于阻止输入，且不牺牲原有“保存中…”反馈。
- R2 只在历史 DTO 边界补 UTC，未改动 Project 现有响应结构和 SQLite 存储语义。
- ApiError 携带 status，前端用 `isApiError(e, 409)` 判断冲突，不依赖中文文案。
- 无新增依赖。

## 阻塞和未解决事项

- 环境缺口（与代码无关，首轮已记录）：本机 `C:\Users\QXFang\AppData\Local\Temp\pytest-of-QXFang` 为无权限的陈旧目录，导致 pytest 默认临时目录不可用；测试用 `--basetemp` 指向仓库内可写目录绕过。所有用例均已实际运行，无 skip。
- 范围外：真实 PostgreSQL 迁移与容器启动属 T02。第二轮审计更正：用户已启动 Docker，环境具备 Docker Engine 29.3.1 与 Compose v5.1.1（此前“Docker 未启动”的表述已过时，本报告据此更新）。环境具备不代表 T02 的应用容器、迁移与恢复验证已通过。
- 浏览器验证使用本机已安装 Chrome（channel=chrome）；未下载 Playwright 自带浏览器。
- 前端无单元测试框架（无 vitest/jest、无 playwright 配置）；本包按仓库现状以可重复脚本 + 真实浏览器验证，未为 T01 引入测试框架（属扩大范围）。若审计认为需要常驻前端回归，建议单列任务引入 Playwright 项目配置。
- 首轮审计提到“网络失败场景未完成最终结果确认”。本次仍未对真实断网做端到端确认；代码路径为 `api()` 捕获 fetch 异常后抛 ApiError(0)，onError 非 409 分支只弹 toast、不动草稿。该结论来自代码阅读，未用真实断网复现，标为未验证。

## 成本记录

| 项目 | 数值 | 单位/计量来源 |
| --- | --- | --- |
| 输入总量 | unknown | tokens |
| 其中缓存命中输入 | unknown | tokens；是否包含在上行需说明：unknown |
| 输出 | unknown | tokens |
| 推理 | unknown | tokens；与输出是否重叠需说明：unknown |
| 实际费用或套餐用量 | unknown | 原币种/额度、计费来源、日期 |
| 修复轮数 | 2 | 轮；首轮 changes_requested（R1、R2 两项阻断）→ 修复提交 006902a；第二轮 changes_requested（R1 续项 1 项阻断）→ 修复提交 6712ded |
| 人类介入 | 2 | 次；用户两次转交审计报告并指示按报告修复 |

## 交接

- 已完成两轮审计问题修复（首轮 R1/R2/C1/C2、第二轮 R1 续项）；请按 REVIEW_PROTOCOL 对第二轮后的新代码做独立复审。不要把旧审计结论套用到新提交。
- 最终回复中提供包含本报告的 HEAD SHA。
- 下一任务：等待复审；不要自行写 accepted，不整合 main，不启动 T02。
