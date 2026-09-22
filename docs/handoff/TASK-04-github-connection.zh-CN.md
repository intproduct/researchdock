# T04 · 个人 GitHub 连接、凭据保护与显式仓库关联

编制日期：2026-09-22。状态：`planned`。本次授权为编写计划；不启动实现、不连接真实 GitHub 账户、不创建或提交真实令牌。

## 1. 目标、前提与范围决定

用户在网页连接个人 GitHub，验证账户后，把自己拥有的一个 GitHub 仓库明确关联到已有 Repository UUID。支持更换令牌、检查连接、断开连接和解除映射。云端只保存凭据密文与身份元数据，Agent 不接收 GitHub 令牌，源代码仍留在设备。

- 设计参考：当前 T03 分支 HEAD `eba6602`，代码审计对象 `80b2102`；实际 main 为 `62cb7f1`。T03 第三轮已关闭 R1–R4，整体仍为 blocked_environment；T02/T03 远端及剩余 UI 验证见对应报告。
- 正常启动条件：T03 accepted 并已整合 main，T02 遗留运行验收已补齐。若用户另行明确授权提前实施，在报告记录该例外、实际起点和遗留缺口，不自行把“写计划”解释为豁免。
- 实施分支 `codex/task-04-github-connection`，从届时符合条件的实际基线创建；记录 base/head。不要 reset 到上述参考 SHA。已有同名分支先核对，不覆盖。
- 首版假设：个人自用，每个本系统账户最多一个 GitHub 连接，只关联该 GitHub 用户自己拥有的 github.com 仓库，支持自己的私有仓库。组织仓库、外部协作者仓库、多 GitHub 账户及 GitHub Enterprise 留待明确需求后扩展。
- GitHub 账户与本系统账户是两个身份；连接 GitHub 不提供登录本系统、邀请成员或跨账户共享功能。

## 2. 固定采用的低成本方案

采用 **fine-grained personal access token（精细权限 PAT）**，手动在 GitHub 创建并在本系统专用表单输入。首版不同时实现 OAuth、GitHub App 或 classic PAT。

T04 仅指导授予指定仓库的 Metadata/read，设置有限有效期；不要求 Contents、Actions、Administration 等写权限。T05 读取分支/提交时另核实并增加所需只读权限。GitHub 官方说明此类令牌可限制资源所有者、仓库及权限，但对组织策略和协作者场景有限制；长期组织集成应重新评估 GitHub App。参见 [PAT 官方说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)。

本系统只发起白名单 GET。可以拒绝显然不属于目标令牌类型的输入，但不能仅凭前缀或 GET 成功声称“已验证令牌绝无写权限”。PAT 也能访问公开资源，**API 可访问范围不等于用户已选择纳入本系统的范围**；只处理用户逐个明确选择并确认的仓库，不扫描全账户列表。

组件复用：现有 FastAPI/SQLModel/Alembic、React/TanStack Query、httpx；凭据加密使用成熟的 `cryptography` Fernet/MultiFernet。直接依赖写入 backend/pyproject.toml，并按本仓库方式更新根目录 requirements.lock。无需 clone PyGithub、模板仓库或其他完整系统，也不引入队列、Redis、Vault 服务或通用插件框架。

## 3. 用户流程与退出标准

1. 打开“GitHub 连接”，按指引生成精细权限 PAT；输入令牌并提交。
2. 后端 GET `/user` 验证实际 GitHub 数字 ID/login，再加密保存；页面仅显示账户、连接检查时间与状态。
3. 在项目的某个 Repository 中点击“关联 GitHub”；输入 owner/name，解析后展示仓库名称、稳定 ID、可见性和链接；用户明确确认映射。
4. 用户可重新选择、解除映射、更换同账户令牌、检查连接或断开。断开不删除项目、副本、研究记录或已有映射，只停止使用凭据，并将映射标为连接已断开。
5. 过期、失效、限流或网络失败可见，旧身份/映射保留，不以一次错误推断仓库已删除。

完成 T04 后能回答“哪个本地逻辑仓库对应哪个 GitHub 仓库，以及当前连接是否可用”。分支列表、提交 SHA/时间、远端观察缓存、手动刷新提交、Webhooks、轮询、自动导入留给 T05；跨设备比较留给 T06/T07。禁止 fetch/push/clone/checkout/reset、源码下载或上传、自动同步与 GitHub 仓库写入。

## 4. 不变量与身份模型

1. Repository UUID、Project revision/历史、WorkingCopy binding_revision/sequence/观察均不因 GitHub 连接或映射变化而改变。
2. GitHub user ID、repository ID 使用提供方返回的稳定数值身份；数据库可存规范十进制字符串，API 一律字符串，避免 JavaScript 大整数精度问题。login/full_name 只是可变化的显示值。
3. 名称、remote URL、路径和同一提交不是自动匹配依据。Fork 即使属于本人也有独立 provider repository ID，不自动合并。
4. 每个本系统账户最多一条持久连接；每个 Repository 至多一条当前 GitHub 映射。同一连接下同一 GitHub repository ID 不可重复映射到另一个 Repository；冲突返回 409，只在当前所有者范围判断。
5. 所有者从登录会话与 Project/Connection 推导，拒绝客户端 owner_id。设备 Token 不能使用任一连接/解析/映射入口。
6. 不存在和其他账户的连接/Repository 返回相同 404 状态及正文；授权完成前不得解密凭据或请求 GitHub。

建议新增两个独立模型，放入 github_models.py，避免继续扩大 research_models.py：

| 模型 | 主要字段与约束 |
| --- | --- |
| GitHubConnection | UUID id；owner_id FK→User CASCADE 且 UNIQUE；provider 固定 github；github_user_id、login；credential_ciphertext nullable；revision 初始 1；last_checked_at、last_check_result、retry_not_before；created_at/updated_at |
| RepositoryGitHubLink | repository_id PK/FK→Repository CASCADE；connection_id nullable FK→Connection RESTRICT；github_repository_id nullable；owner_login/repository_name/full_name/private 等白名单身份快照；binding_revision；verified_at |

Connection 保留元数据，credential_ciphertext=null 表示已断开。revision 只在令牌创建/替换、身份切换或断开时增加；检查结果更新不改变它，且须受发起时 revision 保护。不要将过期、无权限、暂时失败混成一个布尔“已连接”。返回 Public 模型只允许 id、login、用户 ID、revision、has_credential、检查结果/时间及可操作的错误码。

Link 用持久槽位防止 ABA：首次无记录的 GET 返回未关联/binding_revision=0；首次绑定插入版本 1；解除关联时保留行并清空目标/身份快照、增加版本，不能删行后重新从 0 开始。数据库 CHECK 确保空映射目标成组为空，唯一约束 `(connection_id, github_repository_id)` 阻止重复映射；在两数据库验证 null 行不互相冲突。

连接与 Repository 必须属同一本系统账户，此跨表规则由服务端在写事务内强制校验。ID 引用由 FK 保证；没有账户转移接口。删除用户要先清理其映射再删连接，保留原项目/副本级联行为，增加回归，避免 RESTRICT 破坏成员删除。

## 5. API 契约

统一前缀 `/api/v1`，新增独立 github router，沿用 CurrentUser；不修改 Agent 协议。以下是固定语义，响应均为白名单模型，字段校验、分页边界和 UTC 序列化沿用现有风格。

| 方法与路径 | 输入与成功行为 |
| --- | --- |
| GET /github/connections | 返回本账户连接列表，最多 1 条；纯本地读取，不调用 GitHub |
| POST /github/connections | `{token}`；仅不存在时创建，验证 `/user` 后 201；已有连接 409 |
| PUT /github/connections/{id}/credential | `{token, revision}`；先验证新凭据，再条件替换并增加 revision；失败旧密文保持不变 |
| POST /github/connections/{id}/check | `{revision}`；显式 GET `/user`，返回安全检查结果，绑定发起时 revision；无凭据时 409 |
| POST /github/connections/{id}/disconnect | `{revision}`；清空密文并增加 revision，200；已经断开且版本正确则 no-op；不请求 GitHub |
| POST /github/connections/{id}/resolve-repository | `{owner, name, revision}`；获取指定仓库身份预览，纯预览不写映射；返回 connection_revision 和 GitHub 仓库 ID |
| GET /repositories/{id}/github-link | 返回当前槽位、binding_revision、身份快照、连接可用状态；不隐式刷新远端 |
| PUT /repositories/{id}/github-link | 绑定：`{binding_revision, connection_id, connection_revision, owner, name, github_repository_id}`；解除：`{binding_revision, connection_id:null}`，互斥字段用 union/schema 校验；200 返回最新槽位 |

令牌输入使用 SecretStr 等屏蔽 repr 的类型，并设置合理长度上限（例如 4096）；owner/name 有长度与字符限制，拒绝完整 URL、斜杠、点路径、编码分隔符、query/fragment/userinfo。不要通过未审查字符串拼接形成任意 URL。

凭据更新默认要求 `/user` 返回同一 github_user_id；不同账户且仍有任一有效映射则 409。若用户已显式解除全部映射，可接受新身份并增加 connection revision，不能静默把旧映射转给新账户。

映射写入必须重新 GET 指定仓库，验证返回 repository ID 与确认值一致、owner.id 等于连接的 github_user_id、owner.type 为 User。不能信任浏览器预览或检查缓存。远端返回另一 ID/所有者时拒绝，提示重新解析；名称重用不能误绑定。重复相同目标且版本有效可 no-op；过期版本即使同目标仍 409。

断开不需要联网或解密，因此密钥损坏时用户仍可停止本系统使用凭据。页面明确标为“从本系统断开”；GitHub 端撤销由用户到 GitHub 设置执行，系统不给出“GitHub 已撤销”的虚假成功消息。旧 PAT 轮换后是否还在 GitHub 生效同样不能由本地替换推断。

## 6. 凭据存储、备份与脱敏

- 新增 `GITHUB_ENABLED=false` 默认关闭；关闭时其他 T01–T03 功能、迁移与启动不需要加密密钥。GitHub 变更/联网接口不可用时给固定功能未启用错误，已有本地映射可只读展示为功能关闭。
- 启用时必须提供独立 `GITHUB_TOKEN_ENCRYPTION_KEYS`，JSON 数组首项为新写密钥，其余仅解密旧数据。使用 Fernet 生成随机密钥；不复用 JWT SECRET_KEY、不从密码推导、不提交默认密钥。非法配置启动失败但错误不包含原值；无旧密钥/密文损坏时操作失败关闭，不能删除或明文回退。
- 加密载荷包含格式版本、connection UUID、应用 owner UUID、github_user_id 和 PAT；解密后核对上下文，防止将一个连接的密文复制到另一个连接后被误用。数据库/Public API 不保存明文、尾号、可逆“脱敏串”或原始上游响应。
- 浏览器只在提交表单时传入明文。令牌不进入 URL、local/sessionStorage、查询缓存、持久 mutation 状态或分析埋点；提交后无论成功失败均清空令牌输入与 mutation 中的秘密变量，失败需重新输入。名称/映射选择草稿的保留规则与秘密输入分开。
- HTTP Header、请求/响应日志、异常 repr、Pydantic/FastAPI 422 的 `input`/`ctx`、Sentry request body/breadcrumbs 均不得包含令牌或密钥。为敏感端点提供安全验证错误，必要时精确排除遥测采集；不得通过关闭全部异常检查来“通过”。使用伪令牌 sentinel 测错误路径泄漏。
- 部署使用隔离受控配置；远端浏览器输入须 HTTPS，或明确的 loopback + SSH 隧道，不通过明文公网传入 PAT。保持现有 Compose env_file 隔离，不给 frontend 注入密钥；示例只列空占位符，生成器不能覆盖已有环境文件。
- 密钥与数据库备份分开保护；仅备份密文不能恢复连接。旧备份可能含尚在 GitHub 生效的旧 PAT，断开/换令牌并不会擦除历史备份；恢复后核对连接有效性。
- 提供小型管理员重加密命令，读取受控 key ring，以 MultiFernet 将所有非空密文转为新首密钥。要求停止后端写入、先备份、支持只验证不写的 dry-run、失败整体回滚、输出仅计数；不要把密钥放命令参数中。验证新密钥可单独解密后才能移除旧 key，保留恢复旧备份所需的密钥。此命令不轮换 GitHub PAT、不调用 GitHub、不改变业务 revision。

本节是该系统的设计约束；所选加密组件能力依据 [Fernet/MultiFernet 官方文档](https://cryptography.io/en/latest/fernet/)，安装使用适配本项目 Python 的稳定发行版，不使用文档页可能展示的开发版。

## 7. GitHub 请求边界与错误语义

仅允许后端访问 `https://api.github.com`，本包只需要 GET `/user` 和 GET `/repos/{owner}/{repo}`。测试以注入 httpx transport 模拟，不通过运行时可随意配置的 base URL 放宽生产限制。保持 TLS 校验，默认不隐式继承环境代理（确需代理另走明确受控部署配置）。

固定 Accept `application/vnd.github+json`、Authorization Bearer 与 `X-GitHub-Api-Version: 2026-03-10`；版本已按 2026-09-22 官方文档核对。`/user` 可用精细 PAT 且不需要额外账户权限；`/repos/{owner}/{repo}` 的私有仓库身份读取需要 Metadata/read。[用户接口](https://docs.github.com/en/rest/users/users#get-the-authenticated-user)、[仓库接口](https://docs.github.com/en/rest/repos/repos#get-a-repository)、[API 版本](https://docs.github.com/en/rest/about-the-rest-api/api-versions)。

- 不自动跟随重定向，不读取响应中的 arbitrary URL。遇到仓库改名导致 301/302/307/308，返回安全的“请更新仓库定位后重新验证”，保留旧映射；T04 不承诺自动发现新名称。重新输入并确认相同 provider ID 后可更新显示元数据，不变更本地 UUID。T05 再设计按稳定 ID 刷新。
- 路径严格校验/编码；展示链接由固定 `https://github.com/` 与验证后的 owner/name 构造，不直接使用上游不受限 html_url。
- 连接 5 秒、读 10 秒、单操作总预算 20 秒，响应体上限 1 MiB，具体实现同时约束 HTTPX 分阶段超时和总时限。服务端不做无界重试，不为 GET 接入后台调度。[HTTPX 超时说明](https://www.python-httpx.org/advanced/timeouts/)。
- GitHub 401 → 本应用 422 `github_credentials_invalid`（不冒充本系统登录失效）；403 非限流 → 422 `github_access_denied`；404 → 422 `github_repository_unavailable`，不能说仓库一定删除；网络/5xx/非法 JSON/超限响应 → 502/504 的固定上游错误。不能转发原始上游正文、headers 或异常字符串。
- 403/429 具有明确限流证据时 → 429 `github_rate_limited`，记录安全的 retry_not_before 并返回可读的等待时间；遵循 Retry-After 或 reset，在到期前拒绝该连接的再次联网操作，无效/缺失头采用有界冷却。`retry_not_before` 与连接版本关联，旧凭据请求不能污染新连接。[GitHub 限流与重试](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)。
- 检查 `/user` 成功只说明该账户凭据可用，不说明所有映射仓库可访问；私库权限收回须在实际仓库请求时体现。上次成功时间与本次失败状态分别显示，失败不清空身份快照。

## 8. 并发与事务要求

外部 HTTP 不持有长数据库写锁：先获取已授权对象及版本，调用上游，再开启短写事务重新验证当前版本/所有权/是否已断开。最终条件更新必须数据库原子执行，不能只做 Python 的读后比较。

- 同 revision 的两次凭据替换最多一项成功；另一项 409，不能覆盖胜者。
- disconnect 与在途 check/resolve/bind/rotate 交错：disconnect 已提交后，旧请求不能重新存入令牌、写入映射或将状态改回可用；HTTP 发出后不能承诺撤回，必须拒绝采用其过时结果。
- 绑定与轮换/断开须对 connection 的状态和 revision 在最终事务内串行校验；可用短行锁/条件更新。SQLite 与 PG 选兼容方式并实测，不只依赖两个独立 SELECT。
- Link 首次并发插入、重复 GitHub ID、解绑再绑定、过期基线返回 409 且不丢现有映射。DB 异常先 rollback，再安全返回；不能将所有 IntegrityError 当同一种成功。
- 健康检查结果也携带发起时 connection revision，晚到失败不能把已换新令牌标为失效；GET 不隐式保存刷新结果。

## 9. 前端交互

新增单独的 GitHub 连接页面/面板与 Repository 映射组件，避免把所有新代码继续堆入 Workspace.tsx。共享 API 类型与错误码放入研究 API 层；T03 仓库分组继续可用。

展示连接账户、上次检查结果、检查/替换令牌/断开入口；展示未关联、已关联、连接已断开、验证失败和限流状态。映射确认显示本地项目/仓库、目标 GitHub 身份及“只建立管理关联”，不出现“已同步”。

映射编辑状态以 Repository UUID 为键，connection revision 与 link binding_revision 分开；409 保留 owner/name/选择草稿，显示新基线，用户明确采用后重试。刷新失败时禁止假定已获得新版本。已成功结果写入或保护查询缓存，旧请求晚到不能覆盖。切换对象/项目、关闭重开、请求在途时关闭后编辑另一对象，都不能让旧回调修改新草稿。

秘密字段按 §6 清空；其他可恢复草稿按本节保留。提交期间避免重复动作，对会丢失草稿的关闭/切换给明确行为；覆盖真实双会话、失败与延迟响应，不能用 tsc/build 代替 UI 验收。

## 10. 实施顺序与文件范围

| 子阶段 | 内容与独立验证 | 建议提交 |
| --- | --- | --- |
| T04.1 | 模型/迁移、Public schema、Fernet 配置与密文封装、禁用兼容 | schema + encrypted credentials |
| T04.2 | 受限 GitHub client、连接创建/检查/令牌轮换/断开、脱敏 | connection lifecycle |
| T04.3 | 显式预览/映射/解绑、双版本事务、账户隔离 | repository mapping |
| T04.4 | 连接页面与映射 UI、冲突/网络/延迟保护 | frontend flows |
| T04.5 | PG/真实 GitHub 验证、重加密/恢复说明、完整回归及报告 | acceptance evidence |

子阶段仍属于同一个 T04，不新建五个任务分支，不自动进入 T05。每段先跑相关测试，交付前跑一次完整回归；无新改动不重复全量检查。重点成本在凭据与并发验证，不能以页面已经显示账户作为交付完成。

建议位置：backend/app/github_models.py、services/github_client.py、services/github_credentials.py、api/routes/github.py；core/config.py、api/main.py、core/db.py 的最小接入；新增 Alembic revision；backend/tests 下相应测试；frontend/src/research 下独立组件；scripts 下离线重加密工具；.env.example、requirements.lock、部署/使用说明与 status。模块目录不存在时按现有包结构建立，避免引入通用框架。

迁移从实施时真实 Alembic head 出发（当前 T03 为 c4d8e2f15a07），不修改旧 revision、不在 GET/create_all 中建表。升级旧库后不自动生成连接/映射，完整保留 T01–T03 数据；downgrade 只在一次性库验证，删除 T04 元数据的损失明确记录。

## 11. 验收矩阵

| 编号 | 必须验证 |
| --- | --- |
| A01 禁用与配置 | 默认关闭不影响旧启动；启用缺/错密钥安全失败；示例/Compose/frontend 不泄密且配置隔离不退化 |
| A02 身份验证 | `/user` 成功、401/403/非法响应；账号 ID 由服务器确定；失败不留半条连接，不信前缀或前端身份 |
| A03 凭据保护 | 数据库仅密文；API/OpenAPI 示例/422/日志/Sentry/浏览器缓存不含 sentinel；错 key、篡改、跨行复制拒绝 |
| A04 生命周期 | 换令牌失败保留旧值；并发替换只一胜；断开清密文保留元数据；重新连接与换账户规则正确 |
| A05 显式映射 | 预览不落库；绑定重新核验；重复 provider ID 受约束；同名/重命名/重建/fork 不误认；ID 精度不丢失 |
| A06 所有权 | 两个普通账户及设备凭据分别测全部入口；不可见对象同 404 正文；越权请求不解密/不联网、不修改数据 |
| A07 映射版本 | 首次并发插入、更新/解绑冲突、解绑再绑定不回退 revision；同值有效 no-op，过期仍 409 |
| A08 在途竞态 | PG 与 SQLite 实测：断开/换令牌交错 check/resolve/bind，旧结果不能复活连接、覆盖状态或落入映射 |
| A09 上游边界 | 超时/5xx/404/403限流/429/坏JSON/大响应；重定向和恶意路径拒绝；冷却期间零外呼；所有外呼均白名单 GET |
| A10 迁移与清理 | SQLite/PG 空库及含 T03 数据升级/回退/再升级；旧数据逐字段保真；删除用户/项目不留孤立映射、不被 FK 阻塞 |
| A11 真实浏览器 | 创建连接、解析确认、解绑、替换/断开；两会话冲突、请求失败、延迟旧响应、切换对象、关闭重开；令牌清空与非秘密草稿保护分别验证 |
| A12 真实 GitHub | 自己的一公开及一临时私有仓库；Metadata/read PAT；实际身份匹配；私库权限/令牌撤销后失败且快照保留；记录 SHA/时间/去秘密结果 |
| A13 恢复与只读回归 | key ring 重加密 dry-run/成功/失败回滚/新 key 独立解密；备份恢复保留连接可解密性；T01–T03、Agent 只读行为与未配置 GitHub 用户不退化 |

单元/API 测试默认禁止真实网络，以注入 transport 构造结果；真实 GitHub 验收独立且显式启动，真实 PAT 从交互或受控配置读取，不写命令参数、仓库、报告或聊天。模拟测试通过不等于 A12 通过；私库访问验证不可仅用公开仓库代替。

基础命令沿用 AGENTS：隔离 pytest backend/tests agent/tests、前端 build、增量 Ruff，新增 UI 测试按实际框架执行并记录。PG 用专用 TEST_DATABASE_URL + TEST_SCHEMA_FROM_MIGRATIONS=1；本机 Docker 不重试，远端验收使用独立 Compose 项目并保护已有服务。缺少远端、GitHub 测试资源或必要 UI 证据时明确 blocked_environment，不伪造 accepted。

## 12. 交付与转交文本

交付代码、迁移、配置示例、密钥轮换/恢复及 GitHub 手工验收说明、`reports/T04-implementation.md`。更新 README/architecture/status 为实际实现；记录 base/head、每项验收命令/结果/未执行项，模型 token、缓存与费用计量不可取得则写 unknown。不修改已有独立审计结论，不自行整合或推送。

给 Claude Code / Kimi（在启动条件满足或用户另有明确例外后使用）：

```text
请在 D:\files\research-manager 工作，读取 AGENTS.md、docs/status.md、docs/handoff/START_HERE.zh-CN.md 和 TASK-04-github-connection.zh-CN.md。先核对 T03 已 accepted 并整合、T02 运行缺口已关闭及工作区状态；若有用户明确授权例外，记录原意、实际基线与未验收项，不擅自豁免。按条件从实际基线创建/接续 codex/task-04-github-connection，仅实现 T04：个人 github.com 精细 PAT、加密凭据生命周期和显式仓库映射；首版仅本人仓库、每用户一连接。不做 OAuth/App、组织接入、T05 分支提交观察或任何 Git 写入。按 T04.1–T04.5 分步提交，验证 A01–A13。秘密不入日志/响应/仓库；本机 Docker 不重试。写 T04-implementation.md 和实际证据，未执行项如实标明；等待 Codex 审计，不合并、不推送、不进入 T05。
```

给 Codex：按 REVIEW_PROTOCOL 审计 T04，特别复核错误响应/遥测脱敏、密文上下文、凭据轮换与断开竞态、映射身份及账户隔离、慢响应 UI，以及 PG 和真实 GitHub 证据。报告放在本项目 docs/handoff/reports 下。
