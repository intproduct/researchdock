# 云端科研管理：可复用组件与选型记录

核查日期：2026-09-18。配套 [架构与开发计划](./cloud-research-management-plan.zh-CN.md)。

以下依据官方仓库、官方文档和可访问的发布记录。能力属于上游说明；接入成本和优先级属于本项目的工程判断。尚未安装或完成这些组件的端到端验证，也未锁定生产版本。许可证为所访问版本的声明，正式集成需保留该版本的许可证及第三方通知。

## 1. 推荐组合

最小 MVP：FastAPI 全栈模板 + 系统 Git/GitHub + PostgreSQL + 本地 Agent + restic。后台任务采用现成队列，优先验证 PostgreSQL 队列 Procrastinate。对象存储使用已有服务或按需接 SeaweedFS。

科研增强包：DVC、Pyzotero、Docling、pgvector，以及按实验类型选择的 MLflow。每个集成通过适配器开放，用户不启用时不增加运行服务。

## 2. 候选对照

| 组件及官方仓库 | 已核实能力 / 主许可证 | 具体借用方式 | 判断与边界 |
| --- | --- | --- | --- |
| [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) | FastAPI、React、PostgreSQL、认证、测试、Compose；MIT | 从锁定 commit 初始化新应用，保留前后端和测试骨架 | **P0 推荐**；项目/设备/同步和细粒度授权仍需开发；现版前端默认由 API 同域提供 |
| [Procrastinate](https://github.com/procrastinate-org/procrastinate) | PostgreSQL Python 任务队列、重试、任务锁；MIT | 后台 fetch、索引、摄入和导出任务；服务端内部使用 | **P0 PoC**；减少 Redis 服务，但上游正在招募维护者；验证重试与 Worker 崩溃恢复 |
| [restic](https://github.com/restic/restic) | 跨平台、加密、去重、多个存储后端；BSD-2-Clause | 独立备份任务；对数据库一致性快照和 Git/文件备份 | **P0 推荐**；不把运行中的数据库目录直接当作一致备份 |
| [DVC](https://github.com/treeverse/dvc) | Git 中保存数据版本信息，内容置于远程存储，支持流水线；Apache-2.0 | 本地 CLI/适配器管理数据与结果，云端展示 manifest | **P1 推荐**；不是自动双向文件合并器，不管理所有研究业务对象 |
| [MLflow](https://github.com/mlflow/mlflow) | 实验/运行追踪及产物，支持自托管；Apache-2.0 | 作为独立服务接入 run ID、参数、指标、产物 | **P1 按需**；适合计算实验；权限模式、artifact 访问要单独验证 |
| [Pyzotero](https://github.com/urschrei/pyzotero) | Zotero Web/本地 API Python 客户端；Blue Oak Model License 1.0.0 | 后端或本地 Agent 只读连接书目与条目 ID | **P1 推荐**；附件访问、同步版本与速率限制需处理 |
| [Docling](https://github.com/docling-project/docling) | 多格式解析、PDF 布局/表格/公式、OCR、本地运行；MIT | 隔离 Worker 中生成提取文本、页码及结构化结果 | **P1 对比试验**；代码许可不代表每个模型权重同许可，公式质量需真实样本验证 |
| [pgvector](https://github.com/pgvector/pgvector) | PostgreSQL 向量相似度检索；PostgreSQL License | 存储项目限定的向量索引 | **P1 可选**；不替代原件、关键词检索或权限控制 |
| [SeaweedFS](https://github.com/seaweedfs/seaweedfs) | 分布式文件/对象存储及 S3 接口；Apache-2.0 | 要求全自托管时提供对象存储服务 | **按部署需要**；先验证 multipart、签名 URL、DVC/MLflow 兼容性及恢复，不将“S3 兼容”等同全部 API 一致 |
| [Gitea](https://github.com/go-gitea/gitea) | Git 托管、PR、issue、LFS/CI 等；MIT | 自托管 Git 需求出现后部署，通过 API/Git 接入 | **可选**；已有 GitHub 时首期可省；无需 fork UI/修改内核 |
| [DataLad](https://github.com/datalad/datalad) | Git + git-annex 管理代码、数据、容器；MIT/Expat | 数据分散、嵌套数据集、按需取回场景的 DVC 替代试验 | **条件候选**；增加 git-annex 安装和心智负担；同一数据目录不要叠加两套权威版本管理 |
| [Syncthing](https://github.com/syncthing/syncthing) | 连续跨机器文件同步；MPL-2.0 | 独立投递箱或普通资料目录的可选传输工具 | **限制用途**；不承担 Git 分支、活数据库和项目身份管理 |
| [Snakemake](https://github.com/snakemake/snakemake) | 科学工作流执行系统；MIT | 后续已有科学流水线的执行适配 | **P2**；避免自己开发依赖 DAG 引擎 |
| [JupyterHub](https://github.com/jupyterhub/jupyterhub) | 多用户 Notebook 服务；BSD 修订版 | 真有浏览器计算需求时独立部署并链接 | **P2**；额外需要用户环境、资源隔离和运维 |
| [eLabFTW](https://github.com/elabftw/elabftw) | 电子实验记录、资源、设备预约、权限与 REST API；AGPL-3.0 | 若用户重心是湿实验，作为主记录系统或独立集成 | **场景替代**；当前跨机器 Git 版本问题仍需专门 Agent |
| [OSF](https://github.com/CenterForOpenScience/osf.io) | 开放科学平台的代码；Apache-2.0 | 借鉴科研项目组织，评估未来成果发布集成 | **参考优先**；整站定制与维护成本预计高于薄管理层，此为工程判断，未做部署基准 |

## 3. 会改变选型的最新核查结果

### MinIO 不作为新项目的默认开源存储

官方 GitHub 仓库显示于 2026-04-25 归档，README 明示不再维护。旧社区代码为 AGPLv3；README 推荐的 AIStor Free/Enterprise 是另外的产品与许可路径，不能据此称为同一开源组件的持续维护版本。建议新项目优先选现有托管 S3 服务，或验证 SeaweedFS。来源：[MinIO 官方仓库](https://github.com/minio/minio)。

### DVC 当前仓库位于 treeverse

本次访问到的官方项目为 `treeverse/dvc`，不要依赖旧组织名推断维护归属。可访问发布页显示 3.67.1；正式开发应重新检查兼容性并锁定版本，不使用浮动 latest。来源：[DVC 仓库](https://github.com/treeverse/dvc)、[发布记录](https://github.com/treeverse/dvc/releases)。

### FastAPI 模板已有较新的前端和部署结构

本次 README 使用 React/Vite/Tailwind/shadcn，提供 Docker Compose 自托管；生产前端默认由 FastAPI 提供静态内容。提交页可见 2026-09-01 的更新。这意味着可借模板快速启动，但独立前端部署、设备 Agent 和研究模型仍属我们的工作。来源：[模板 README](https://github.com/fastapi/full-stack-fastapi-template)、[提交记录](https://github.com/fastapi/full-stack-fastapi-template/commits/master/)。

### 自托管 Git 不必立即部署

Gitea 使用 MIT，可在真正需要私有 Git 托管时加入。另一候选 Forgejo 的主源代码位于 Codeberg，其 v9 起转为 GPLv3+，不应沿用早期 MIT 信息。首期保留已有 GitHub 可减少一套需维护的服务。来源：[Gitea](https://github.com/go-gitea/gitea)、[Forgejo 官方许可说明](https://forgejo.org/2024-08-gpl/)。

### 较小队列组件需评估维护风险

Procrastinate 功能适配“小团队已有 PostgreSQL、希望减少服务数”的场景，但官方 README 正在招募维护者。暂定为 PoC 选项；通过 `JobBackend` 适配器接入，替换时不影响科研业务模型。来源：[Procrastinate README](https://github.com/procrastinate-org/procrastinate)。

## 4. 三种总体路线比较

| 路线 | 最快获得什么 | 主要缺口 | 本次建议 |
| --- | --- | --- | --- |
| 直接使用 GitHub/Gitea + Zotero + MLflow 等现成工具 | 各单项能力可立即使用 | 跨设备副本、全局项目身份与研究接续仍分散 | 可先形成过渡工作方式 |
| 改造 eLabFTW/OSF 等整套系统 | 成熟的科研记录或平台功能 | 仍须做本地 Agent/Git 对账，还要维护大系统 fork | 仅当实际需求明显贴合时采用 |
| 薄 Web 管理层 + 组件适配器 | 统一解决项目、设备、版本和状态 | 需要设计可靠协议与少量核心业务 | **推荐**，可分阶段交付且减少上游分叉 |

该比较是基于功能适配与运维复杂度的判断，不是跑分。用户若以湿实验设备/试剂记录为主，应重新提高 eLabFTW 权重；若以跨机构成果公开与注册为主，应提高 OSF 权重；若以分布式科学数据集为主，应提高 DataLad 权重。

## 5. 每个主要组件的验证任务

| 组件 | 小样任务 | 通过标准 |
| --- | --- | --- |
| FastAPI 模板 | 新建隔离开发环境，独立构建前端/API，增加一个 Project 模型 | 登录、迁移、生成客户端、浏览器用例与 Compose 重建通过 |
| Git/GitHub | 两台设备制造领先、落后、分叉、dirty、浅克隆 | 比较与真实 Git 结果一致；未知不伪装一致 |
| Procrastinate | 同一任务重复投递，执行中终止 Worker，按业务键锁定 | 无重复业务副作用；可恢复并有可观察失败 |
| DVC | 用一个真实大文件和多个小文件在两台机器 push/pull | 哈希一致、按需取回、失败可重试、存储成本可测 |
| SeaweedFS | 大文件上传中断、签名 URL、DVC 读写、备份恢复 | 覆盖实际使用的 S3 子集；权限和引用完整性正确 |
| Docling | 10 篇授权样本文献，含多栏、公式、扫描件和表格 | 原件完整；页码可回查；记录公式/顺序/表格错误率及单篇成本 |
| Zotero/Pyzotero | 个人/群组库小样，增量同步和删除条目标记 | ID 不重复，版本正确，附件权限与限流可处理 |
| MLflow | 一个数值实验记录参数、指标、图与数据/代码标识 | 项目中可跳到 run，产物权限正确，快照可回收 |
| restic | 用备份恢复到全新目录和数据库 | 关键文件哈希、Git refs、数据库记录与来源引用通过核对 |

以上工作由正式开发阶段执行；本轮仅完成文档与源码层面的调研。

## 6. 集成约定

- 用 Git/API/CLI 协议接入成熟产品，尽量不 fork 其业务内核。
- 模板型复用记录原始 commit，保留许可；服务型复用使用独立容器；库型复用固定版本。
- 上游 repo 状态、许可证、镜像来源与安全更新在锁定版本时再次核查；不以 star 数代替质量判断。
- 核心数据不依附 UI 或单一供应商 ID；所有外部标识通过映射表关联项目 UUID。
- 外部 API 的身份凭据、重试、速率限制、webhook 去重和断连状态统一封装。
- LLM 和文档提取器作为可替换能力，不决定项目身份，也不直接执行破坏性同步。

## 7. 补充的官方接口依据

- [Git rev-list](https://git-scm.com/docs/git-rev-list)：提交可达性及左右差异计数。
- [Git merge-base](https://git-scm.com/docs/git-merge-base)：共同祖先与祖先关系。
- [GitHub App 安装令牌](https://docs.github.com/en/rest/apps/apps)：限定仓库和权限的服务端访问。
- [Zotero Web API v3](https://www.zotero.org/support/dev/web_api/v3/basics)：书目、版本、条件请求和限流。
- [DataLad 安装说明](https://handbook.datalad.org/en/latest/intro/installation.html)：Git/git-annex 依赖和 Windows 安装路径。
- [MLflow 自托管](https://github.com/mlflow/mlflow/blob/master/docs/docs/self-hosting/index.mdx)：追踪服务、元数据与产物存储的分工。
- [Pyzotero 许可](https://github.com/urschrei/pyzotero/blob/main/LICENSE.md)、[pgvector 许可](https://github.com/pgvector/pgvector/blob/master/LICENSE)：核对具体许可证，而非根据语言生态猜测。

本次确认的是这些官方页面提供的能力和声明；未据此宣称所有组件已经适配本项目，也未将主分支或“Latest”标签当作稳定的生产版本锁。
