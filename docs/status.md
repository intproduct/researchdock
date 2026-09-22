# 开发状态 · 2026-09-21

## 当前交付

v0.1 本地可运行的最小完整流程：登录 → 创建项目 → 配对设备 → 登记 Git 根目录 → 只读观察并上报 → 网页查看副本 → 保存研究进展。前后端和 Agent 独立，开发 SQLite、部署 PostgreSQL。

T01 追加“项目状态快照历史”：新建项目即写入 revision=1 的 `created` 快照，每次成功 PUT 追加一条 `updated` 快照，只追加不修改；`GET /api/v1/projects/{id}/history` 按 revision 降序分页返回，项目详情页有可展开的历史面板。历史写入与项目更新在同一事务，条件更新加数据库唯一约束保证并发下只有一个基线请求成功。

实现细节和边界见 architecture.md；使用方法见根目录 README.md。研究规划参考原项目 docs/cloud-research-management-plan.zh-CN.md 与 cloud-research-components.zh-CN.md；未搬入原知识库数据和代码。

## 验证记录

- Windows / Python 3.14：后端及 Agent 共 79 项测试通过（原 66 项回归 + T01 新增 13 项）。真实临时 Git 仓库覆盖领先、落后、分叉、未提交工作、浅克隆、游离 HEAD；API 覆盖账户隔离、设备撤销、重复及倒序上报、修订冲突。
- T01 新增覆盖：创建即为单条 created 快照、更新到 2/3 后降序且内容正确、重复旧请求 409 且不新增历史、同内容 PUT 仍加版本、并发相同基线仅一个成功、历史写入失败回滚项目更新与 revision、新建失败不留孤立项目、外账户/匿名/设备凭据隔离、伪造 actor/origin/recorded_at 不生效、非法分页参数 422、分页无重复遗漏且翻页期间新增 revision 不破坏向旧版本翻页。
- 迁移：临时 SQLite 上 upgrade 基线回填单条 `migrated_baseline`（actor_id 为 null，保留真实内容与 project_updated_at）、二次 upgrade 不重复插入、downgrade 删除历史表后再次 upgrade 恢复、空库 upgrade 得空历史、迁移后表结构与模型元数据一致。另对开发库副本做 upgrade 验证：已有 revision=2 的项目仅补一条基线，不伪造缺失的 1…N-1。
- 浏览器完成登录、创建示例项目、保存研究进展，修订从 1 更新为 2；T01 后在隔离端口（8011/5183）与隔离库上实测：历史面板降序展示、展开快照、基线标签、加载更早的修订（10→12 条）、两个会话冲突时 409 保留草稿、采用最新内容后重新保存成功，无页面报错。
- TypeScript 和 Vite 生产构建通过；新增页面的 Biome 检查通过。
- SQLite Alembic 升级 → 回退 → 升级通过；Compose 配置解析通过。
- npm audit：0 项已知漏洞。开发依赖 js-yaml 通过 override 固定为 4.3.2；后续升级生成器时复核该 override。
- 模板测试依赖有 2 条弃用警告，未隐藏。

## 未验收与下一步

1. 本机 Docker 不再用于验收；按用户决定改用远端 2 核 2GB 服务器。用户已验证远端引擎、Compose 及四个基础镜像拉取；应用栈尚未完成验收。当前版本真实 PostgreSQL、容器启动与备份恢复仍待独立验证；HTTPS/正式上线留待 T14。不得宣称已经部署到云端。T01 的 PostgreSQL 迁移验证交由 T02。
2. 历史只保存“项目状态快照”，不是完整研究日志：无撤销/恢复版本、diff 算法、全文搜索、单条详情 API，也不承诺数据库管理员无法篡改。
3. GitHub App/OAuth、远端刷新、跨设备祖先关系比较尚未实现。当前关系仅相对于本机缓存的 upstream，不是不同机器的直接对比。
4. 没有自动同步、合并或上传代码。下一阶段先做同步计划与人工可审查的差异，再考虑受控写入。
5. Agent 凭据目前保存在用户目录 SQLite；原生凭据保险库、签名分发、自动升级、网络超时退避可随后补充。
6. 非 Git 目录导入、DVC、MLflow、Zotero 为后续独立接入项。
7. 本机 `C:\Users\<用户>\AppData\Local\Temp\pytest-of-QXFang` 为无权限的陈旧目录，导致默认 pytest 临时目录不可用；受影响时用 `--basetemp` 指向可写目录。与 T01 代码无关。

根目录 .env、credentials.local.txt、开发数据库和 runtime 下的验收记录都不提交。示例项目用于展示验收结果，验收设备在交付前撤销。首次 Git 提交不配置任何远端。

## 协作交接 · 2026-09-19

用户已选择 Claude Code / Kimi 实现、Codex 设计与独立审计。T01 已通过第三轮审计（`accepted`），被审计交付 HEAD 为 `757dee0`，报告见 [T01-review-round3](handoff/reports/T01-review-round3.md)。79 项测试、前端构建及 6 项独立源码状态探针通过，旧版本对照有 3 项失败。UTC、保存期间新增草稿和慢刷新旧内容回写问题已关闭。浏览器工具本轮启动失败，未独立重跑端到端 UI，具体覆盖边界见报告。按协议本地整合 main 并保留全部历史；T02 已交付并完成首轮审计，结论 `changes_requested`：测试连接与 Compose 环境隔离有 2 项 P1，备份命令有 1 项 P2；Docker 重试仍返回 500，容器/恢复未独立验收。详见 [T02-review](handoff/reports/T02-review.md) 和 [手动验证步骤](handoff/T02-manual-test.zh-CN.md)。T02 未整合 main，不开始 T03。后续任务仍按 [路线图](handoff/ROADMAP.zh-CN.md) 规划。

交接文档已落盘；没有启动 Claude Code、自动通知或后台协调服务。实现方按任务卡创建本地提交和报告，再由用户转交审计请求；无需远端仓库。

## T02 第二轮审计 · 2026-09-20

交付 HEAD `8a80429` 已复审，结论 `changes_requested`。原 R1/R2/R3 具体缺陷已关闭；剩余两项 P2 为生成器仓库外路径报错（影响默认 CI）和 CLI 回归误放行原错误且调用真实 Docker。独立检查 84 passed、1 deselected（以四组无 Docker 派发探针补验）；前端构建通过。远端只完成基础环境准备，完整容器/PG/重启/恢复验收仍待完成。详见 [第二轮报告](handoff/reports/T02-review-round2.md)。main 保持 T01 accepted 基线；不开始 T03。

## T02 第三轮审计 · 2026-09-20

交付 HEAD `f9aa2c6` 已复审，结论 `changes_requested`。R4/R5 已关闭；新增一项 P2：Compose 配置检查将非零退出直接作为测试通过（R6）。独立完整回归 91 passed、2 条既有弃用警告；前端构建和增量 Ruff 检查通过；真实配置路径 2/2 与模拟 CLI 派发 4/4 通过。配置故障注入证实误放行，需修复回归门槛。远端运行证据仍未补齐，不整合 main、不开始 T03。详见 [第三轮报告](handoff/reports/T02-review-round3.md)。

## T02 第四轮审计 · 2026-09-20

交付 HEAD `1fade9c` 已复审，R1–R6 已知代码问题全部关闭，本轮未发现新的阻断代码缺陷。独立回归 93 passed、2 条既有弃用警告，无 skip/deselect；前端构建、增量 Ruff、真实 Compose 路径检查及新旧入口故障注入通过。整体状态为 `blocked_environment`：可以进入远端验收，但当前版本 PG/容器/重启/备份恢复证据仍未补齐，尚非 accepted；不整合 main，不开始 T03。详见 [第四轮报告](handoff/reports/T02-review-round4.md)。下一步从 [远端说明](handoff/T02-remote-server.zh-CN.md) 第 5 节上传确定版本，已有基础环境准备无需重做。

## T03 规划交付 · 2026-09-21

按用户请求新增 [T03 完整任务卡](handoff/TASK-03-repository-identity.zh-CN.md)，明确 Repository UUID、同项目副本显式关联、并发版本、旧 Agent 兼容、迁移与 A01–A13 验收；更新 [后续路线图](handoff/ROADMAP.zh-CN.md)，区分多机器手动试用、GitHub 总览和个人日常使用，并拆分可提前执行的 T14a 云运行基础与 T14b 上线验收。

本次只修改规划与交接文档，没有新增 Repository 模型/API 或开始 T03 编码。T03 状态 planned，实施等待 T02 accepted 并整合 main。T02 仍以第四轮报告为准，远端运行验收尚未完成。后续各包不因出现在路线图就自动获得实施授权。

## T02 整合与 T03 交付 · 2026-09-21

用户在本会话明确授权：豁免 T02 远端运行验收即推进，并在 T02 正式 accepted 前开始 T03 编码（偏离既定协议，T02 远端 PG/容器/重启/备份恢复证据仍缺失，不视为 accepted）。据此 T02 分支已快进整合入 main（无重写），T03 自实际 main（base `62cb7f1`）建 `codex/task-03-repository-identity`。

T03 已交付实现：Repository 身份模型与同项目复合 FK、迁移 `c4d8e2f15a07`、仓库 CRUD 与副本绑定 API、Agent `repositories`/`link --repository`、前端仓库分组面板，及 A01–A13 测试（A05/A10 仅 SQLite 实测、A11 浏览器与 A13 Linux 未执行）。详见 [T03 实现报告](handoff/reports/T03-implementation.md)。状态 `ready_for_review`，等待 Codex 独立审计；未自标 accepted。

## T03 首轮独立审计 · 2026-09-21

交付 HEAD `1ee164d` 已审计，结论 `changes_requested`：三项 P2 为仓库改名冲突后旧 revision 无法更新、关联冲突分组刷新卸载对话框丢失选择、目标仓库授权返回码泄漏跨账户存在性。真实浏览器复现前两项，普通账户 API 探针复现第三项。独立回归 109 passed、前端构建与 Windows 双 Agent 冒烟通过；新增冒烟脚本 Ruff 报四条错误。PG/Linux 和未覆盖的 UI 异常路径仍未验收。报告见 [T03-review](handoff/reports/T03-review.md)。不整合 T03、不进入 T04；main 保持已实际整合 T02 的 62cb7f1，T02 的远端缺口继续保留。

## T03 第二轮独立审计 · 2026-09-21

交付 HEAD `e99cad7` 已复审，仍为 `changes_requested`。R1/R2 原始复现已通过；R3 404 正文仍泄漏跨账户仓库存在性；新增 R4 为不同副本共用版本下限导致冲突重试失败。两项 P2 见 [第二轮报告](handoff/reports/T03-review-round2.md)。独立完整回归 111 passed、2 条既有弃用警告；前端构建、增量 Ruff、Windows 双 Agent 冒烟通过，真实浏览器复现 R4。PG/Linux 与其余 UI 异常路径仍待验证。不整合 T03，不开始 T04，main 仍为 62cb7f1。

## T03 第三轮独立审计 · 2026-09-22

交付 HEAD `80b2102` 已复审，R3/R4 通过独立 API 与浏览器复验，R1–R4 已知代码问题全部关闭，本轮未发现新的阻断代码缺陷。111 passed、2 条既有弃用警告；前端构建、增量 Ruff 通过。真实浏览器连续编辑高/低版本副本、关闭重开、HTTP 503 后重试及未归类分组冲突恢复通过。整体为 `blocked_environment`：PG 并发/迁移、Linux CLI、T02 远端运行及 A11 其余异常时序证据待补，尚非 accepted。详见 [第三轮报告](handoff/reports/T03-review-round3.md)。不整合 T03、不启动 T04；main 保持 62cb7f1。

## T04 计划交付 · 2026-09-22

按用户请求完成 [T04 任务卡](handoff/TASK-04-github-connection.zh-CN.md)，状态 `planned`。根据当前代码与 GitHub 官方文档，选定个人精细权限 PAT、每用户一连接、本人 GitHub 仓库与 Repository UUID 显式映射；规定凭据加密/轮换/本地断开、身份与版本、错误脱敏、迁移、前端草稿保护及 A01–A13 验收。规划分 T04.1–T04.5 实施，复用现有 httpx 并采用成熟加密库，不克隆其他项目、不引入额外服务。

本次仅修改规划与交接文档，没有实现 GitHub 接口、创建真实连接或处理真实 PAT。正常实施等待 T03 accepted 并整合及 T02 运行缺口补齐；用户如另行明确授权提前推进须记录例外，不能自动推定。T03 仍为 blocked_environment，main 保持 62cb7f1。
