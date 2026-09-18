# 开发状态 · 2026-09-19

## 当前交付

v0.1 本地可运行的最小完整流程：登录 → 创建项目 → 配对设备 → 登记 Git 根目录 → 只读观察并上报 → 网页查看副本 → 保存研究进展。前后端和 Agent 独立，开发 SQLite、部署 PostgreSQL。

T01 追加“项目状态快照历史”：新建项目即写入 revision=1 的 `created` 快照，每次成功 PUT 追加一条 `updated` 快照，只追加不修改；`GET /api/v1/projects/{id}/history` 按 revision 降序分页返回，项目详情页有可展开的历史面板。历史写入与项目更新在同一事务，条件更新加数据库唯一约束保证并发下只有一个基线请求成功。

实现细节和边界见 architecture.md；使用方法见根目录 README.md。研究规划参考原项目 docs/cloud-research-management-plan.zh-CN.md 与 cloud-research-components.zh-CN.md；未搬入原知识库数据和代码。

## 验证记录

- Windows / Python 3.14：后端及 Agent 共 78 项测试通过（原 66 项回归 + T01 新增 12 项）。真实临时 Git 仓库覆盖领先、落后、分叉、未提交工作、浅克隆、游离 HEAD；API 覆盖账户隔离、设备撤销、重复及倒序上报、修订冲突。
- T01 新增覆盖：创建即为单条 created 快照、更新到 2/3 后降序且内容正确、重复旧请求 409 且不新增历史、同内容 PUT 仍加版本、并发相同基线仅一个成功、历史写入失败回滚项目更新与 revision、新建失败不留孤立项目、外账户/匿名/设备凭据隔离、伪造 actor/origin/recorded_at 不生效、非法分页参数 422、分页无重复遗漏且翻页期间新增 revision 不破坏向旧版本翻页。
- 迁移：临时 SQLite 上 upgrade 基线回填单条 `migrated_baseline`（actor_id 为 null，保留真实内容与 project_updated_at）、二次 upgrade 不重复插入、downgrade 删除历史表后再次 upgrade 恢复、空库 upgrade 得空历史、迁移后表结构与模型元数据一致。另对开发库副本做 upgrade 验证：已有 revision=2 的项目仅补一条基线，不伪造缺失的 1…N-1。
- 浏览器完成登录、创建示例项目、保存研究进展，修订从 1 更新为 2；T01 后在隔离端口（8011/5183）与隔离库上实测：历史面板降序展示、展开快照、基线标签、加载更早的修订（10→12 条）、两个会话冲突时 409 保留草稿、采用最新内容后重新保存成功，无页面报错。
- TypeScript 和 Vite 生产构建通过；新增页面的 Biome 检查通过。
- SQLite Alembic 升级 → 回退 → 升级通过；Compose 配置解析通过。
- npm audit：0 项已知漏洞。开发依赖 js-yaml 通过 override 固定为 4.3.2；后续升级生成器时复核该 override。
- 模板测试依赖有 2 条弃用警告，未隐藏。

## 未验收与下一步

1. Docker daemon 在当前电脑未启动；真实 PostgreSQL、容器启动、HTTPS、云端部署及备份恢复待验收。不得宣称已经部署到云端。T01 的 PostgreSQL 迁移验证交由 T02。
2. 历史只保存“项目状态快照”，不是完整研究日志：无撤销/恢复版本、diff 算法、全文搜索、单条详情 API，也不承诺数据库管理员无法篡改。
3. GitHub App/OAuth、远端刷新、跨设备祖先关系比较尚未实现。当前关系仅相对于本机缓存的 upstream，不是不同机器的直接对比。
4. 没有自动同步、合并或上传代码。下一阶段先做同步计划与人工可审查的差异，再考虑受控写入。
5. Agent 凭据目前保存在用户目录 SQLite；原生凭据保险库、签名分发、自动升级、网络超时退避可随后补充。
6. 非 Git 目录导入、DVC、MLflow、Zotero 为后续独立接入项。
7. 本机 `C:\Users\<用户>\AppData\Local\Temp\pytest-of-QXFang` 为无权限的陈旧目录，导致默认 pytest 临时目录不可用；受影响时用 `--basetemp` 指向可写目录。与 T01 代码无关。

根目录 .env、credentials.local.txt、开发数据库和 runtime 下的验收记录都不提交。示例项目用于展示验收结果，验收设备在交付前撤销。首次 Git 提交不配置任何远端。

## 协作交接 · 2026-09-19

用户已选择 Claude Code / Kimi 实现、Codex 设计与独立审计。T01（研究修订历史）实现已完成并提交在分支 `codex/task-01-history`，报告见 [T01-implementation](handoff/reports/T01-implementation.md)，状态 `ready_for_review`，**尚未**独立审计。T02（PostgreSQL/Compose/恢复）等待 T01 审计整合。后续任务只在 [路线图](handoff/ROADMAP.zh-CN.md) 中规划。

交接文档已落盘；没有启动 Claude Code、自动通知或后台协调服务。实现方按任务卡创建本地提交和报告，再由用户转交审计请求；无需远端仓库。
