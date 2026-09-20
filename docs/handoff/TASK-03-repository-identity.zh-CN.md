# T03 · Repository 身份、项目关联与副本分组

编制日期：2026-09-21。状态：`planned`（任务卡已就绪，实施等待 T02 accepted 并整合 main）。本次只授权编写任务卡与路线图，不代表已启动 T03 实现。

## 1. 目标与启动基线

用户可以为一个科研项目建立多个逻辑仓库，将不同机器的工作副本明确关联到其中一个仓库；在网页上按仓库查看副本，纠正关联，不因同名目录、相同 remote 或相同提交而误合并。

当前实现只有 Project → WorkingCopy，副本含 project_id、device_id、local_path 与最新观察，没有 Repository 实体。Agent 在 cli.py 中保存本地 SQLite 登记与 outbox；不要假定已有单独的 state.py 或仓库身份服务。

- 当前设计参考提交：`5ce1fdd`（包含 T02 第四轮审计）；不是将来实现时强制 checkout 的基线。
- T02 已知代码问题关闭，但 PG/容器/恢复远端验收尚未完成。必须先核对最新 status 和审计结论。
- 实施分支：`codex/task-03-repository-identity`，从包含 T02 accepted 和本任务卡的实际 main 创建；记录实际 base/head SHA，禁止 reset 到上述参考提交。
- 沿用 FastAPI/SQLModel/Alembic、React、标准库 Agent；不增加数据库服务、队列或通用仓库管理框架。

## 2. 用户流程与范围

示例：项目“论文 A”下创建“分析代码”“论文排版”两个 Repository。在 Windows 和 Linux 上把各自的分析目录绑定到“分析代码”的同一 UUID，排版目录绑定到另一个 UUID。网页展示两组及各自副本；同名但不同 UUID 的仓库不会合并。

本包实现：仓库创建/列表/改名；新副本明确登记仓库；现有副本的人工关联、更正和解除关联；网页分组和 Agent 列表/绑定；旧数据、旧 Agent 的兼容迁移。

本包不实现：仓库合并/移动到另一项目/删除、项目间共享仓库、GitHub 授权或联网查库、remote URL 规范化匹配、跨机器历史关系计算、fetch/push/checkout/reset、文件上传、自动同步。Fork 可以由用户建立独立 Repository；本包不声称能判定 fork 关系。

## 3. 身份与数据契约

关系为 `Project 1 → N Repository 1 → N WorkingCopy`，允许 WorkingCopy 暂未归类；一个副本最多关联一个 Repository。Repository 是用户在本系统确认的逻辑身份，不等于 Git 的远程地址或平台账号中的同名仓库。

### Repository（新增表，表名 repository）

| 字段 | 约束/含义 |
| --- | --- |
| id | 服务端生成 UUID，主键；改名不变 |
| project_id | 非空，关联 Project；创建后不可修改；所有者由 Project.owner_id 推导 |
| name | trim 后非空，1–120 字符；同项目允许重名，不能作为身份或自动去重条件 |
| revision | 非空整数，初始 1；仓库改名采用期望 revision 条件更新 |
| created_at / updated_at | 服务端 UTC；API 输出显式时区；SQLite 与 PG 行为一致 |

不新增 repository.remote_url 或平台连接字段。已有 WorkingCopy.remote_url 继续仅表示该副本的一次观察，不能作为身份依据。GitHub provider ID、连接与仓库映射在 T04/T05 单独设计，届时不得改变 Repository UUID。

### WorkingCopy（增量字段）

- 保留现有 id、project_id、device_id、local_path、sequence 和全部观察字段。
- 新增 `repository_id: UUID | null`，带索引/FK；null 表示“未归类”，不是默认仓库。
- 新增 `binding_revision: int >= 0`，数据库默认 0；迁移旧副本为 0。新副本指定仓库则初始 1，未指定则 0。
- 同一副本只能绑定同一 project_id 的 Repository；所有入口服务端检查。数据库必须有 repository 存在性约束，并保证项目一致性（可用 `(repository_id, project_id)` 复合 FK + Repository 对应唯一约束）。不能只靠下拉框过滤。
- 保留 `(device_id, local_path)` 唯一约束。服务端不按操作系统大小写规则或相似路径猜测同一个副本；Agent 继续沿用现有路径解析和 Git 根校验。
- Repository.project_id 固定，T03 不提供迁移项目接口。账户删除等现有级联行为不能因新增 FK 被破坏；实现时核对 SQLite/PG。

### 必须维持的不变量

1. UUID 是身份；名称、路径、remote、HEAD、时间戳均不能自动建立或改变关联。
2. 仓库关联只影响组织关系。它不证明提交相同、共同历史或实时远端状态；既有 comparison 仍相对该设备缓存的 upstream。
3. 改名/关联/解绑不修改 Project.revision，不追加 T01 状态快照。T01 历史仍只覆盖已有项目状态字段，不能暗示已记录仓库关联历史。
4. 关联更改不触碰 Git，不改变 copy ID、device/path、sequence、outbox 或观察时间。观察描述物理副本；重新归类后可以展示已有观察，但不能当作一次新扫描或新的跨仓库比较证据。
5. 设备凭据只可查询该所有者项目的仓库、为本设备登记副本和提交观察；不能创建/改名仓库，不能用观察请求篡改 project_id、repository_id、binding_revision 或 device_id。

## 4. API 契约

以下均以 `/api/v1` 为前缀。新增输入 DTO 拒绝未知字段；owner_id、UUID 与服务端时间不可由请求指定。所有权检查复用当前账户/设备授权，不因知道 UUID 而越权。

RepositoryPublic 固定字段：`id, project_id, name, revision, created_at, updated_at`。现有副本响应增量包含 `repository_id, binding_revision`，其余字段保持兼容。

| 方法与路径 | 凭据 | 输入 / 输出与行为 |
| --- | --- | --- |
| GET /projects/{project_id}/repositories | 用户 | 返回该项目 RepositoryPublic 数组，按 created_at、id 稳定排序；空项目返回 [] |
| POST /projects/{project_id}/repositories | 用户 | `{name}`；201 返回 RepositoryPublic；只创建明确指定的新 UUID |
| PUT /repositories/{repository_id} | 用户 | `{name, revision}`；原子条件更新，成功 200 且 revision+1；过期期望值 409，不写入；同名合法提交也按一次成功更新处理 |
| PUT /copies/{copy_id}/repository | 用户 | `{repository_id: UUID或null, binding_revision}`；仅该副本项目所有者可改；返回更新后的完整 WorkingCopy |
| GET /agent/projects/{project_id}/repositories | 设备 | 返回该所有者指定项目的 RepositoryPublic 数组，只读；已撤销设备 401 |
| POST /agent/copies（扩展） | 设备 | 原 `{project_id, local_path}` 增加可选 repository_id；规则见下节 |

不存在或其他账户的项目/仓库/副本返回 404，不泄漏存在性；未认证/凭据类型不适用按现有认证入口返回拒绝。仓库属于同一账户的另一项目时，绑定返回 422；过期 revision 或已有目录绑定冲突返回 409。非法 UUID、空名称、超长名称及负 binding_revision 返回 422。错误消息和日志不得回显 Token 或有凭据的 remote。

### 用户关联操作的并发规则

- 先检查 copy 所有权、目标 Repository 同项目，以及期望 binding_revision。
- 有效期望值且目标发生变化（含关联、改绑、解绑）时，通过条件 UPDATE 原子修改 repository_id，并令 binding_revision+1；观察字段原样保留。
- 有效期望值且目标与当前相同：200 原样返回，不加版本。过期期望值即使目标相同也返回 409，避免以幂等为名掩盖冲突。
- 两个独立请求以同一基线提交不同目标：只能一个成功，另一个 409；不能读后直接无条件写。
- 并发观察上报仅更新观察字段，关联接口仅更新关联字段；双方不能用整行覆盖吞掉对方结果。遇到提交失败必须整体回滚。

### Agent 登记与重试规则

- 新 `(device_id, local_path)`：验证项目和可选仓库后创建；仓库不在同项目就拒绝，不创建孤立副本。
- 既有目录 + 同项目 + 未传 repository_id（含 null）：返回当前绑定，不解绑、不创建仓库，兼容旧 Agent。
- 既有目录 + 同项目 + 显式传入与当前一致的 repository_id：返回原 ID/sequence/binding_revision，不修改，支持响应丢失后的重试。
- 既有目录 + 不同项目，或显式传入不同 repository_id（包括原先未归类）：409。提示通过网页更正；设备不获重新分类权限。
- 并发首次登记：唯一约束兜底；相同参数重试最终读取同一 ID，不产生重复行；不同参数不能覆盖已成功的绑定。
- 原观察 API 路径、sequence 单调条件更新、撤销权限及旧 observation payload 继续有效。

## 5. Agent 与页面

### Agent

新增 `python -m research_agent repositories --project PROJECT_UUID`，输出仓库 UUID 和名称；支持 `link --project PROJECT_UUID --repository REPOSITORY_UUID --path PATH`。保留旧的 link 参数用法，未分类时明确提示“未归类，可在网页关联仓库”。仓库信息必须来自用户指定 UUID，不通过 scan 的 remote 自动选择。

新 Agent 显式指定仓库时必须核对服务器返回的 repository_id；旧服务器忽略新字段或返回不一致时非零退出，不能输出“绑定成功”。说明服务端可能已登记未分类副本，需升级服务端并在网页核对；不能因重试就篡改绑定。

本包不要求在 Agent 本地 SQLite 保存 repository_id：服务端是关联关系来源，现有 copies/outbox 可原样继续工作。若实现确有必要调整本地模式，必须提供保留 sequence、凭据和 outbox 的增量迁移，不能删除重建数据库。示例 UUID 为占位符，不连接用户真实工作目录做测试。

### 前端

项目详情展示“仓库”分组：显示每个仓库名称、可复制 UUID、关联副本（设备、路径、观察状态），空仓库可见；另显示“未归类”组，不能把它伪装成已创建仓库。提供创建、改名，以及副本关联/改绑/解绑入口，仅可选当前项目仓库。重名仓库用 UUID 短标识辅助区分。

关联修改明确告知只更改管理关系、不搬动本地文件。409 保留用户当前选择/名称输入，展示刷新后的当前值，要求明确重新提交；网络失败也保留输入。提交期间避免重复操作；刷新返回顺序不能让旧数据覆盖已成功写入的新 binding_revision/revision。复用 T01 的草稿保护经验，但不要重构其研究进展编辑器。

更新连接指引，给出 repositories 命令与带 --repository 的 link 命令。旧未归类副本仍可查看和上报；总副本数不能漏计或重复计数。保留 existing comparison 的缓存语义提示，不展示“此两机器已同步”等尚无证据的结论。

## 6. 迁移与兼容

新增 Alembic revision；当前 head 为 `b7f3a1c29e04`，执行时核对实际 head 并以其为父，不改写已发布 migration。

- 新表 + nullable repository_id + 非空 binding_revision 默认 0；旧项目/副本不自动生成 Repository，不按 remote/name 聚类。
- 从含真实形状测试数据的 T02 数据库升级后，所有旧 ID、project/device、sequence、观察、项目 revision/history、撤销标记保持原样；Repository 表初始为空。
- 新增约束和索引在 SQLite/PG 均生效，ORM 元数据与迁移模式一致。不得用 create_all 掩盖迁移缺失。
- 旧 Agent 无 repository_id 的登记与上报可用；已关联副本被旧 Agent 再登记时不被清空。旧本地状态/outbox 在新 Agent 下能继续上报并保留序号。
- downgrade 仅在自建临时库验证：删除新增关联/仓库会丢失这些新元数据，但必须保留旧项目、副本观察及 T01 历史；说明恢复需完整备份。正式数据不自动回退。
- 更新 README、architecture、status 中实际已实现部分及 OpenAPI/前端类型；本任务卡编写时不提前标记实现。

## 7. 验收矩阵

| 编号 | 场景 | 必须验证的结果 |
| --- | --- | --- |
| A01 | 一项目两仓库；两设备绑定同仓库 | UUID 关系和页面分组正确，副本各自保存观察 |
| A02 | 同名目录、同名仓库、相同 remote、不同 SSH/HTTPS 表述、无 remote | 均不自动合并/自动绑定；改变 remote 不改变 repository_id |
| A03 | 仓库创建/改名 | 字段校验、名称 trim、稳定 UUID、revision 冲突正确；不改变 T01 历史 |
| A04 | 未归类副本关联、改绑、解绑、同值重试 | binding_revision 规则正确；ID/sequence/观察保持不变 |
| A05 | 两独立连接同时改绑、观察与改绑交错 | 单基线不同目标只一个成功；观察序号和关联均不丢失，在 PG 实测 |
| A06 | 越权与设备角色 | 另一账户全部读写隔离；设备不能改仓库/关联；同账户跨项目仓库也不能绑定；撤销凭据拒绝 |
| A07 | 登记重试/并发/冲突 | 无重复副本；不改变已有绑定；无权限/非法请求不落库 |
| A08 | 旧 API/旧 Agent payload/旧本地 outbox | 正常登记与上报，已有绑定不被清空，序号继续递增 |
| A09 | 新 Agent 指定仓库遇到旧服务器 | 无确认就失败，不谎报绑定成功；登记/扫描仍只读 |
| A10 | 空库升级、T02 旧库升级、回退再升级 | SQLite 和 PG 实际执行；完整数据对比；不自动建仓库/合并；模式与元数据一致 |
| A11 | 页面创建改名、分组、关联冲突与网络失败 | 保留输入；慢刷新不覆盖新状态；未归类与空仓库可见；T01 草稿/历史回归不退化 |
| A12 | 约束与清理 | 非法引用被拒绝；原用户/项目关联的级联行为不退化，不留孤立副本 |
| A13 | 独立端到端 | 两个隔离 Agent 配置/设备绑定同一仓库，上报后网页分组正确；至少 Windows 与 Linux 各一次 CLI 冒烟 |

测试用一次性 Git 仓库、账户/设备与 RESEARCH_AGENT_HOME，不执行用户真实仓库的写命令。只读断言覆盖工作文件、HEAD、索引与引用未变化；保持现有 Git 命令白名单/禁用 hook 的策略。CI/工具不可用应明确失败或按已定义环境条件 skip，不吞异常伪造通过。

基础命令：`python -m pytest backend/tests agent/tests -q`、`npm --prefix frontend run build`、相关 Ruff 检查。PG 使用 T02 的专用 TEST_DATABASE_URL 与 TEST_SCHEMA_FROM_MIGRATIONS=1，核实真实 dialect；连接串不进入报告。本机 Docker 不重试；PG/容器验证在远端隔离项目中执行，保留其他服务。

没有平台环境或浏览器证据时标明未执行；不以 mock/SQLite/构建替代要求的 PG 或界面实测。既有用例数量只是参考（T02 第四轮 93 项），不得用硬凑数量代替风险覆盖。

## 8. 实施与交付顺序

建议四个可审查提交：①模型/迁移与约束回归；②授权 API/并发/兼容测试；③Agent/前端及交互验证；④文档和实现报告。每阶段先验证所改风险，最终跑完整约定检查；不要为每个文案调整重跑全部套件。

优先读取：backend/app/research_models.py、api/routes/research.py、core/db.py、alembic/versions/；agent/research_agent/cli.py、scanner.py；frontend/src/research/Workspace.tsx、api.ts；既有 research/history/scanner 测试。新增实体必须被 Alembic 与测试 metadata 正确注册。允许按职责提取小模块，不重写框架。

交付 `docs/handoff/reports/T03-implementation.md`，逐项映射 A01–A13，填写真实 base/head、模式/端口/数据库标识（无秘密）、命令/退出码、实际 UI 步骤和缺口；原始日志放 runtime。Codex 独立审计写 T03-review.md；实现方不自标 accepted、不整合、不推送、不自行开始 T04。

可转交的实施提示（启动条件满足后使用）：

```text
请在 D:\files\research-manager 工作，读取 AGENTS.md、docs/status.md、docs/handoff/START_HERE.zh-CN.md 和 TASK-03-repository-identity.zh-CN.md。先确认 T02 已 accepted 并整合 main，工作区干净；条件不满足只报告实际缺口，不修改实现。满足后从实际 main 建立 codex/task-03-repository-identity，按任务卡完成 Repository 身份、显式副本关联、迁移、旧 Agent 兼容、页面和 A01–A13 验证。只做 T03，保留只读边界，不做 GitHub 接入或自动同步。本机 Docker 不重试，PG/容器验收在远端隔离环境执行。分步提交并写 T03-implementation.md，给出实际 base/head 和未执行项，等待 Codex 审计；不自行合并或进入下一包。
```
