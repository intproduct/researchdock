# T01 实现报告

- 状态：ready_for_review
- 任务卡：docs/handoff/TASK-01-history.zh-CN.md
- 分支：codex/task-01-history
- 实际 base SHA：7e4c4a0828045547c373c8f47a39ec8ac10beafb
- 最后代码提交 SHA（此报告提交之前）：36983911599dc87c08329617ed4ad1e72e79ab0a
- 执行平台/解释器/Node/数据库版本：Windows 11 / Python 3.14 / Node 26.5 / SQLite（开发与隔离测试），PostgreSQL 未执行
- 实际模型与服务来源（不知道写 unknown）：Kimi 后端（用户配置的 Claude Code 会话），其余 unknown

## 结果

用户保存进展后，现在能按时间倒序查看每次保存的完整快照与时间，并在另一处已更新时不丢失当前草稿。新建项目写入 revision=1 的 created 快照；每次成功 PUT 在与项目更新同一事务内追加一条 updated 快照；条件更新加 (project_id, revision) 唯一约束保证并发下只有一个基线请求成功，失败请求不追加历史、不回写内容。详情页新增可展开、可翻页的历史面板，409 时保留草稿并提供“查看最新/采用最新”操作。

本包未实现独立研究日志、撤销/恢复版本、diff/搜索、Git 同步或 AI 总结。

主要修改文件及原因（不粘贴整个 diff）：

| 文件 | 原因 |
| --- | --- |
| backend/app/research_models.py | 新增 ProjectRevision 表、ProjectSnapshot、ProjectRevisionPublic、ProjectHistoryPage |
| backend/app/api/routes/research.py | create/edit 同事务写快照；新增 GET /projects/{id}/history；新增 record_revision 帮助函数 |
| backend/app/alembic/versions/b7f3a1c29e04_project_revision_history.py | 建表 + 已有项目基线回填，down_revision=d42026f707b5 |
| backend/tests/api/routes/test_history.py | 历史 API 与并发/回滚/权限/分页测试（8 项） |
| backend/tests/test_migration_history.py | 隔离 SQLite 上的迁移、幂等、downgrade/upgrade、schema 一致性（4 项） |
| frontend/src/research/api.ts | ApiError 携带 HTTP status；新增历史类型 |
| frontend/src/research/HistoryPanel.tsx | 可展开、可翻页的历史面板 |
| frontend/src/research/Workspace.tsx | 详情页草稿保留、baseRevision 固定、409 冲突与采用最新流程 |

## 契约核对

| 任务卡验收项 | 结果 | 证据 |
| --- | --- | --- |
| 新建项目返回 revision=1，只有一条对应快照 | 通过 | test_create_records_single_created_snapshot；端到端 create→history 见执行记录 |
| 更新到 2/3 后历史降序、每条内容正确；重复旧请求 409 且没有第四条历史 | 通过 | test_updates_append_descending_history_and_409_adds_nothing；verify_api 输出 |
| 两个独立请求使用相同基线，只一个成功（非串行冒充） | 通过 | test_concurrent_same_baseline_only_one_succeeds（ThreadPoolExecutor 并发） |
| 历史插入失败回滚 Project 内容与 revision；新建失败不留孤立项目 | 通过 | test_history_insert_failure_rolls_back_project_update；test_create_failure_leaves_no_orphan_project（monkeypatch 注入失败） |
| 外账户/匿名/设备凭据权限隔离，伪造 actor 不生效，非法分页参数被拒绝 | 通过 | test_history_permissions_and_forged_fields |
| 分页无重复遗漏；加载下一页期间新增 revision 不破坏向旧版本翻页 | 通过 | test_history_pagination；端到端 page1→page2→page3 无重复 |
| 已有 revision>1 项目迁移仅产生当前基线；二次 upgrade 幂等；隔离库 upgrade/downgrade/upgrade | 通过 | test_migration_history.py（4 项）+ 开发库副本 upgrade 仅补一条基线 |
| 两会话冲突、背景刷新、网络失败均保留草稿；明确采用最新后能正常保存 | 通过（浏览器实测） | verify_ui.mjs 输出：冲突保留草稿、采用最新、再保存成功、无页面报错 |
| 原 66 项回归仍通过，新测试有实质断言；前端生产构建通过 | 通过 | 全套 78 passed；npm build 成功 |
| 历史页面可实际操作，有浏览器结果或可重复的人工步骤 | 通过 | Playwright+Chrome 实测历史面板、基线标签、翻页、冲突流程 |

## 执行记录

| 工作目录与完整命令（去掉秘密） | 环境/实际数据库 | 退出码与测试数量 | 结果 |
| --- | --- | --- | --- |
| `python -m pytest backend/tests agent/tests -q --basetemp=<repo>/runtime/tmp/pytest -p no:cacheprovider` | Windows / Python 3.14 / 隔离临时 SQLite | 0，78 passed | 全绿（原 66 + 新增 12） |
| `python -m pytest backend/tests/test_migration_history.py -q --basetemp=... -p no:cacheprovider` | 隔离临时 SQLite 文件（4 个独立库） | 0，4 passed | 基线回填、幂等、downgrade/upgrade、schema 一致 |
| `npm run build`（frontend） | Node 26.5 / Vite 8 | 0 | tsc + vite 生产构建成功 |
| `npx biome lint ./src/research`（frontend） | Node 26.5 | 0，3 files | 新增/修改的 research 文件 lint 通过 |
| `python -m ruff check <changed backend files>` | Python 3.14 | 0 | 全部通过 |
| `python -m research_agent --help` | Python 3.14 | 0 | CLI 正常（Agent 协议未改动） |
| 隔离后端（uvicorn :8011，独立 SQLite）+ verify_api.py | 隔离 SQLite | 0 | create/rev1、update/rev2、旧请求 409、分页 5,4→3,2→1、匿名 401、limit=0 422 |
| 隔离前端（vite :5183）+ verify_ui.mjs（Playwright+本机 Chrome） | 隔离库 + 浏览器 | 0 | 历史面板降序、展开快照、基线标签、加载更早（10→12）、两会话冲突保留草稿、采用最新后保存成功、无页面报错 |

UI 操作步骤及可观察结果：

1. 登录（verify@example.com）→ 打开“分页验证项目”（12 修订）→ 历史面板首屏 10 条、顶部为修订 12、有“加载更早的修订”按钮；点击后共 12 条、最后一条为修订 1（创建）。
2. 打开“基线验证项目”→ 历史面板 1 条、显示“迁移基线”标签；展开可见迁移前的进展快照。
3. 打开“浏览器验证项目”，在“当前进展”填入“草稿：会话 A 未保存”；在另一会话把该项目保存为“会话 B 的保存”；回到会话 A 点保存 → 顶部出现“另一处已更新到修订 N”警告且草稿仍为“草稿：会话 A 未保存”。
4. 点“采用最新内容（丢弃草稿）”并在确认框确定 → 表单变为“会话 B 的保存”；改写为“采用最新后的新编辑”再保存 → 提示“研究进展已保存”。
5. 全程无 pageerror；截图留存于 runtime/tmp/conflict.png。

迁移/恢复验证：在临时目录新建 4 个独立 SQLite 文件，分别执行 `upgrade head`（空库）、`upgrade head` 两次（幂等）、`upgrade head` → `downgrade d42026f707b5` → `upgrade head`（恢复基线）、`upgrade head` 后核对表结构与模型元数据一致；另对开发库 research.db 的副本（runtime/tmp/devcopy.db）执行 upgrade，仅补一条 revision=2 的 migrated_baseline，不伪造缺失版本。**没有真实 PostgreSQL，未执行容器化迁移**，该项交由 T02。

## 设计决定与偏离

- 快照来源：更新后的快照取自本次校验通过的请求体（ProjectSnapshot.from(body)），而非 SQLAlchemy identity map 中的旧 Project 对象，避免把旧对象误当新数据；project_updated_at 用本次条件更新的时间戳。与任务卡“快照应来自此次成功更新的状态”一致，无偏离。
- record_revision 只在调用方事务内 add 快照，不自行 commit，保证与项目更新原子。
- 前端移除 `form key={project.revision}` 的重挂载写法，改为草稿由组件状态持有并固定 baseRevision；409 后 onError 触发 projects.refetch() 以显示“最新修订号”，但不覆盖草稿。
- ApiError 携带 status，前端用 `isApiError(e, 409)` 判断冲突，不依赖中文文案。
- 无新增依赖。

## 阻塞和未解决事项

- 环境缺口：本机 `C:\Users\QXFang\AppData\Local\Temp\pytest-of-QXFang` 为无权限的陈旧目录，使 pytest 默认临时目录不可用；上述测试用 `--basetemp` 指向仓库内可写目录绕过。与代码无关，属本机环境，需用户自行清理该目录或改 TEMP 指向。这不是 skip 测试，所有用例均已实际运行。
- 范围外：真实 PostgreSQL 迁移与容器启动属 T02，本机 Docker daemon 未启动，未执行。
- 浏览器验证使用本机已安装的 Chrome（channel=chrome）；未下载 Playwright 自带浏览器（下载慢且非必需）。

## 成本记录

| 项目 | 数值 | 单位/计量来源 |
| --- | --- | --- |
| 输入总量 | unknown | tokens |
| 其中缓存命中输入 | unknown | tokens；是否包含在上行需说明：unknown |
| 输出 | unknown | tokens |
| 推理 | unknown | tokens；与输出是否重叠需说明：unknown |
| 实际费用或套餐用量 | unknown | 原币种/额度、计费来源、日期 |
| 修复轮数 | unknown | 轮 |
| 人类介入 | 0 | 次；全程自动实现与自测 |

## 交接

- 尚未进行独立审计；请按 REVIEW_PROTOCOL 审计。
- 最终回复中提供包含报告的 HEAD SHA。
- 下一任务：等待审计；不要自行写 accepted。
