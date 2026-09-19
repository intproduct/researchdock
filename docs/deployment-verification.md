# T02 · PostgreSQL / Compose 验证操作说明

本文件给出可重复的本机/CI 验证步骤。默认 SQLite 开发方式不变；以下步骤全部使用**隔离**的测试库、镜像、卷和端口，不读取或覆盖日常开发的 `.env`、`research.db` 或 Docker 卷。

## 0. 环境前提

- Docker Engine + Compose 可用（本包在 Docker Desktop 29.3.1 / Compose v5.1.1 / linux-amd64 上验证）。
- 若 Docker Hub 镜像拉取失败，可临时改用镜像加速器（如 `docker.m.daocloud.io/library/postgres:17-alpine`），再由 `docker tag` 回官方名。镜像名变更属环境操作，不改产品代码。
- 不要在防火墙/系统服务上为测试放权；网页只绑定 `127.0.0.1`。

## 1. 隔离配置（不碰日常 .env）

```powershell
.\.venv\Scripts\python.exe scripts\compose_env.py runtime\env\t02.env
```

生成带随机 `SECRET_KEY`、`POSTGRES_PASSWORD`、`FIRST_SUPERUSER_PASSWORD` 的 `runtime/env/t02.env`（已 git 忽略）。`compose.yaml` 用 `ENV_FILE` 指向它，故测试栈与开发库完全隔离。

## 2. 构建并启动整套栈（迁移 + 初始化 + 后端 + 前端）

```powershell
docker compose --env-file runtime\env\t02.env -p rm-t02-<唯一后缀> up -d --build
docker compose --env-file runtime\env\t02.env -p rm-t02-<唯一后缀> ps
docker compose --env-file runtime\env\t02.env -p rm-t02-<唯一后缀> logs migrate
```

验收点：`migrate` 一次性完成 `alembic upgrade head`（从空库到 T01 含历史表，不依赖 `create_all`）；`backend` 只有 `migrate` 成功才启动，且其健康检查 `/api/v1/utils/readiness/` 真实连库后才标记 healthy；`frontend` 通过 Nginx 同源转发 `/api`。

## 3. 网页/API 可用性

- 打开 `http://127.0.0.1:8080`（或 `PUBLIC_PORT`），登录、创建项目、保存进展、翻历史，确认 SPA 路由（如直接访问 `/projects/<id>`）也能加载。
- 直接访问 `http://127.0.0.1:8080/api/v1/utils/readiness/` 应返回 `{"database":"ok"}`。
- 重启保留数据：

```powershell
docker compose --env-file runtime\env\t02.env -p rm-t02-<唯一后缀> restart backend frontend
```

重启后项目、历史、设备仍在；已有账户密码不被重置（`initial_data` 只幂等创建）。

## 4. 备份与恢复

```powershell
.\.venv\Scripts\python.exe scripts\postgres_backup.py backup --project rm-t02-<唯一后缀> --compose-env runtime\env\t02.env
.\.venv\Scripts\python.exe scripts\postgres_backup.py restore --project rm-t02-<唯一后缀> --compose-env runtime\env\t02.env `
  --file runtime\backups\<刚生成的>.dump --target-db research_restore_test
```

验收点：备份落在 `runtime/backups/`（不入 Git）；恢复只接受名字明显是测试库的目标（`*_test`/`test_*`/`test`），非空目标默认拒绝；恢复后逐项核对 UUID、内容、revision、history、观察序号，且旧 revision 提交仍返回 409；恢复保留 `SECRET_KEY` 等配置要求，密钥不进日志/报告。

## 5. 测试库防误删

- `backend/tests/conftest.py` 只在 `TEST_DATABASE_URL` 指向名字明显是测试库（`*_test` 等）时才允许 `drop/recreate`；普通 `DATABASE_URL` 和用户 `.env` 永不作为 drop/create 目标。
- 指定了 PostgreSQL 却连不上会**失败**，不会退回 SQLite。

## 6. 清理（只清隔离栈）

```powershell
docker compose --env-file runtime\env\t02.env -p rm-t02-<唯一后缀> down -v
```

`-v` 只删除本项目自己的卷（`rm-t02-<唯一后缀>_postgres-data`），不影响开发数据。`down -v` 不属于恢复工具；恢复脚本默认拒绝覆盖已有业务库。
