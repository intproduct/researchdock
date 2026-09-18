# 开发状态 · 2026-09-19

## 当前交付

v0.1 本地可运行的最小完整流程：登录 → 创建项目 → 配对设备 → 登记 Git 根目录 → 只读观察并上报 → 网页查看副本 → 保存研究进展。前后端和 Agent 独立，开发 SQLite、部署 PostgreSQL。

实现细节和边界见 architecture.md；使用方法见根目录 README.md。研究规划参考原项目 docs/cloud-research-management-plan.zh-CN.md 与 cloud-research-components.zh-CN.md；未搬入原知识库数据和代码。

## 验证记录

- Windows / Python 3.14：后端及 Agent 共 66 项测试通过。真实临时 Git 仓库覆盖领先、落后、分叉、未提交工作、浅克隆、游离 HEAD；API 覆盖账户隔离、设备撤销、重复及倒序上报、修订冲突。
- 浏览器完成登录、创建示例项目、保存研究进展，修订从 1 更新为 2。
- 实际运行的 API、真实 Git 仓库、Agent 本地队列联调成功；网页同时显示“提交一致”和“有未提交工作”。
- TypeScript 和 Vite 生产构建通过；新增页面的 Biome 检查通过。
- SQLite Alembic 升级 → 回退 → 升级通过；Compose 配置解析通过。
- npm audit：0 项已知漏洞。开发依赖 js-yaml 通过 override 固定为 4.3.2；后续升级生成器时复核该 override。
- 模板测试依赖有 2 条弃用警告，未隐藏。

## 未验收与下一步

1. Docker daemon 在当前电脑未启动；真实 PostgreSQL、容器启动、HTTPS、云端部署及备份恢复待验收。不得宣称已经部署到云端。
2. GitHub App/OAuth、远端刷新、跨设备祖先关系比较尚未实现。当前关系仅相对于本机缓存的 upstream，不是不同机器的直接对比。
3. 没有自动同步、合并或上传代码。下一阶段先做同步计划与人工可审查的差异，再考虑受控写入。
4. 项目当前进展是带修订检查的可编辑文本，不是完整研究历史。补充来源版本、研究日志和证据链模型。
5. Agent 凭据目前保存在用户目录 SQLite；原生凭据保险库、签名分发、自动升级、网络超时退避可随后补充。
6. 非 Git 目录导入、DVC、MLflow、Zotero 为后续独立接入项。

根目录 .env、credentials.local.txt、开发数据库和 runtime 下的验收记录都不提交。示例项目用于展示验收结果，验收设备在交付前撤销。首次 Git 提交不配置任何远端。
