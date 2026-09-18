# T01 · 研究进展的修订历史

状态：ready。依赖：当前交接 HEAD。预计规模：2–4 传统人日，仅作工作量参考，不设虚构 token 配额。

## 目标和边界

用户保存进展后，能查看每次保存的内容和时间；另一处已更新时，当前草稿不会被丢弃。保留现有项目创建和 PUT 更新的行为与字段。实现“项目状态快照历史”，不在本包实现独立研究日志、撤销/恢复版本、多人角色、Git 同步或 AI 总结。

优先读取：research_models.py 的 Project/Create/Update，research.py 的 create_project/edit_project/require_project，ProjectDetail、api.ts，test_research.py，现有迁移及 conftest。可新增专用历史组件和测试文件，不重构整个模板。

## 数据契约

新增 ProjectRevision 表，约束以迁移和数据库定义为准：

| 字段 | 要求 |
| --- | --- |
| id | UUID 主键 |
| project_id | Project 外键、索引；随项目删除级联，不另造永久审计存储承诺 |
| revision | >=1；与 project_id 组成唯一约束 |
| snapshot | 完整状态：name、description、stage、status_note、next_step；使用明确字段或有类型验证的 JSON；不可夹带 owner、token 或任意输入 |
| actor_id | 可空 User 外键；服务端提供，用户被删除时 SET NULL；不返还邮箱等多余用户信息 |
| origin | created / updated / migrated_baseline |
| recorded_at | 服务端 UTC 入库时间；迁移基线使用实际迁移时间，不冒充原始编辑发生时间 |
| project_updated_at | 对应快照的项目 updated_at，单独保存以区分迁移时间与项目最后更新时间 |

新建项目同时保存 revision=1、origin=created 的历史。每次现有 PUT 成功，revision 加 1，并保存返回状态的完整快照。保持原有“相同内容 PUT 也加版本”的兼容行为，不额外做内容去重。

历史只追加；当前功能没有更新/删除历史 API。不宣称数据库管理员也无法篡改。客户端传入 actor、recorded_at、origin 等字段不能改变可信字段。

## 事务和迁移要求

新 revision 的 down_revision 指向 d42026f707b5。对已有项目只补当前 revision 一条 migrated_baseline 快照；actor_id 为 null，保留真实当前内容和 project_updated_at，不伪造缺失的 1…N-1 版本。

项目创建+初始快照、条件更新+新快照必须分别同事务 commit。不能先提交 Project 再插历史。并发相同基线只有一个 PUT 成功；失败/过期请求不增加 revision、不追加历史、不覆盖内容。用条件更新和数据库唯一约束保证，不能仅靠 Python 先读后判断。

验证历史写入失败会回滚项目更新。更新快照应来自此次成功更新的状态，防止 SQLAlchemy identity map 中旧对象被误当成新数据。迁移须能对已有数据升级且重复 `upgrade head` 不重复插入。downgrade 只在隔离测试库执行；明确回退会丢失历史表，不在开发数据上做演示。

SQLite 迁移必须实际执行；PostgreSQL 实际迁移验证由 T02 完成。T01 中没有 PostgreSQL 环境不构成假装通过的理由，报告该项交由 T02。

## API 契约

沿用 `/api/v1` 前缀，新增：

```text
GET /projects/{project_id}/history?limit=20&before_revision=5
```

- limit 范围 1–100，默认 20；before_revision 可省略，给定时 >=1，表示 revision 严格小于该值。
- 响应 `{items: ProjectRevisionPublic[], next_before_revision: number|null}`，按 revision 降序。存在下一页时游标为本页最后一条 revision，否则 null。
- DTO 包含上述历史 ID、project_id、revision、snapshot、actor_id、origin、recorded_at、project_updated_at，时间明确为 UTC。
- 先检查项目所有权再查询；不存在/其他账户的项目统一 404，匿名和设备 token 不得读取此用户接口。
- 不变更现有 POST/PUT 响应结构或 PUT 409 约定。PUT 成功刷新当前项目及历史缓存。
- 只提供上述按页列表；本包无需 restore、diff 算法、全文搜索或单条详情 API。

## 前端行为

项目详情页增加历史列表/展开面板，可展开查看完整快照、时间、修订号及基线标签；分页加载，正确显示空、加载、错误及重试。

编辑开始时固定草稿对应的 baseRevision。背景 refetch 或 query cache 更新不能静默替换草稿，也不能把新版 revision 附到旧草稿再提交。当前 `form key={project.revision}` 值得检查：避免重挂载清空正在编辑的内容。

409 后保留全部草稿，显示“另一处已更新”；允许查看最新版本，并通过明确操作采用最新内容后重新编辑。采用最新会丢弃草稿时先清楚提示/确认。不要后台自动重试 PUT 或自动三路合并。网络失败也保留草稿。两个浏览器会话可复现该行为。无需把草稿永久保存到浏览器存储。

当前 api.ts 只抛 Error 文本，可扩展为携带 HTTP status 的错误类型；保持现有调用兼容，不用匹配中文文案来识别 409。

## 验收清单

- [ ] 新建项目返回 revision=1，只有一条对应快照。
- [ ] 更新到 2/3 后历史降序、每条内容正确；重复旧请求 409 且没有第四条历史。
- [ ] 两个独立请求使用相同基线，只一个成功；不能用串行两次调用冒充并发测试。
- [ ] 历史插入失败回滚 Project 内容与 revision；新建失败也不留下孤立项目。
- [ ] 外账户/匿名/设备凭据权限隔离，伪造 actor 不生效，非法分页参数被拒绝。
- [ ] 分页无重复遗漏；加载下一页期间新增 revision 不破坏向旧版本翻页。
- [ ] 已有 revision>1 的项目迁移仅产生当前基线；二次 upgrade 幂等；隔离库 upgrade/downgrade/upgrade。
- [ ] 两会话冲突、背景刷新、网络失败均保留草稿；明确采用最新后能正常保存。
- [ ] 原 66 项回归仍通过，新测试有实质断言；前端生产构建通过。
- [ ] 历史页面可实际操作，有浏览器结果或可重复的人工步骤；无法执行的 UI 检查标为未验证。

同包允许改 README/docs/status/architecture、当前 API/UI、相关测试、迁移和模型注册。依赖通常无需新增；必须新增时说明必要性并更新锁文件。没有环境的检查不能悄悄删除或 skip 后写全部通过。

交付：分支 codex/task-01-history，完整任务提交、docs/handoff/reports/T01-implementation.md，状态 ready_for_review。后续进入 T02 前先按审计修复。
