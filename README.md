# Research Manager · 科研项目工作空间

把不同机器上的研究项目、副本位置、Git 状态与研究进展汇总到网页。v0.1 提供独立前端、后端和只读本地 Agent；文件继续保存在原机器。

## 已实现

- 账户登录、管理员管理用户；项目和设备按账户隔离。
- 项目创建、搜索、阶段筛选、当前进展和下一步；修订校验防止旧编辑覆盖新内容。
- 每台设备独立配对和撤销；明确登记 Git 根目录。
- 分支、提交、未提交修改、未跟踪文件数量、观察时间与设备在线状态。
- 对本地缓存 upstream 的领先、落后、分叉判断；浅克隆、游离 HEAD 等显示待确认。
- Agent 断网保留最新观察并重试；服务端拒绝重复或倒序覆盖。

**尚未实现**：GitHub 实时接入、不同设备间直接历史比较、自动同步/合并、文件备份、非 Git 目录、实验和文献集成、完整研究日志。这一版不上传文件正文，不执行 fetch/push。

## 本机启动（Windows PowerShell）

需要 Python 3.14、Node.js 24+ 和 Git。首次安装需要联网；无需手动 clone 任何参考仓库。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend -e ./agent
npm.cmd --prefix frontend ci
.\.venv\Scripts\python.exe scripts/setup_local.py
.\.venv\Scripts\python.exe scripts/dev.py
```

打开 http://localhost:5173 。初始账户和随机密码在 `credentials.local.txt`，仅保存在本地且已被 Git 忽略。初始化不会覆盖已有 `.env`；已有账户的密码也不会被重复初始化重置。API 文档：http://127.0.0.1:8000/docs 。Ctrl+C 关闭开发服务。

Linux/macOS 将上述解释器替换为 `.venv/bin/python`，npm 命令替换为 `npm`。本机默认 SQLite；数据库通过 Alembic 迁移创建。

## 连接另一台机器

另一台机器只需要 Python 3.11+ 和 Git，可以复制此仓库的 `agent` 目录后安装；不要求安装后端或前端。项目 ID 在网页详情页复制。

```text
python -m pip install ./agent
python -m research_agent login --server https://YOUR_SERVER --email YOUR_EMAIL
python -m research_agent projects
python -m research_agent link --project PROJECT_ID --path "YOUR_REPOSITORY_PATH"
python -m research_agent scan --watch 30
```

本机联调可使用 `--server http://localhost:5173`。密码交互输入；设备凭据保存在用户目录 `.research-manager/agent.db`。可用 `RESEARCH_AGENT_HOME` 指定独立配置目录。网页撤销设备后，其凭据立即失效。断网队列只保留每个副本的最新观察，不是历史日志或备份。

## 云服务器部署准备

已提供 `compose.yaml`、Nginx 和前后端 Dockerfile。容器栈使用 PostgreSQL 17，启动时先迁移并初始化账户，网页默认只绑定服务器回环地址 `127.0.0.1:8080`。

1. 通过初始化脚本生成安全的 `.env`；设置 `FRONTEND_HOST=https://你的域名`，添加随机的 `POSTGRES_PASSWORD`（建议仅字母数字，避免 URL 转义问题）。
2. 执行 `docker compose up -d --build`。
3. 在服务器已有反向代理配置 HTTPS，将域名转发到 `127.0.0.1:8080`。远程 Agent 强制 HTTPS。

本机 Docker daemon 未运行，因此目前尚未完成真实容器和 PostgreSQL 联调。上线前需补齐该验证以及域名、TLS、备份恢复演练。SQLite 开发数据不会自动迁移到 PostgreSQL。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests agent/tests -q
npm.cmd --prefix frontend run build
```

目录：`frontend/` 网页，`backend/` API 与迁移，`agent/` 独立客户端，`deploy/` 容器部署，`scripts/` 本机启动工具。接续开发先读 `docs/status.md` 和 `docs/architecture.md`。`requirements.lock` 固定当前 Python 依赖版本，`frontend/package-lock.json` 固定前端依赖。

## Git 与复用来源

这是独立项目；使用 FastAPI 官方 MIT 全栈模板作为认证及界面基础，来源和固定提交见 `THIRD_PARTY_NOTICES.md`。未复制参考知识库项目的实现代码。

本地 Git 仓库建立后无需联网即可提交。远端仓库创建好后再执行：

```text
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

`.env`、本地密码、数据库、依赖目录与运行时状态均不入库。
