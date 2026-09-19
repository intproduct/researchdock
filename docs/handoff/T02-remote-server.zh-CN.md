# 远端 2核2GB 服务器准备与 T02 验收

适用：现有 2核2GB Linux 服务器；以下安装命令针对 Ubuntu 24.04 / 22.04。2026-09-19 起，按用户决定，后续 Docker 验证改在远端执行，本机继续编辑和审计代码。

这是一份操作说明，审计者尚未连接或配置用户服务器。截至 2026-09-20，用户已验证远端 Docker/Compose 和四个基础镜像拉取（准备阶段 1–4）；T02 第三轮审计仍有一项测试修复，见 [审计报告](reports/T02-review-round3.md)。修复提交完成且隔离代码复核后再做 5–8。不要上传半成品、根 .env、开发数据库、.venv 或 node_modules。

## 1. 在 Windows 连接服务器

准备云控制台提供的公网 IP、SSH 用户名和登录方式。用户名通常是 ubuntu 或 root，以实际控制台为准。以下 SERVER_IP / SSH_USER 都需替换。

```powershell
ssh SSH_USER@SERVER_IP
# 若控制台给的是密钥文件：
# ssh -i "C:\你的密钥路径\server.pem" SSH_USER@SERVER_IP
```

首次连接按云控制台或已知渠道核对主机指纹。密码交互输入，不需要发给 Agent。

安全组先允许你的来源 IP 访问实际 SSH 端口（默认 22）。本阶段通过 SSH 隧道访问网页，不需要开放 5432、8000、8080、18082 或 Docker API 端口。已有服务器无需重装系统。

## 2. 检查现有环境（在服务器终端）

```bash
cat /etc/os-release
uname -m
free -h
df -h /
swapon --show
command -v docker || true
```

确认操作系统、架构、剩余内存/磁盘。若不是 Ubuntu，不执行下一节 apt 安装命令，先把系统名称和版本发回，以便调整。amd64/x86_64 与此前验证环境相同；若是 ARM，先记录，不必为此重装。

若已有 Docker，先执行 `sudo docker version`、`sudo docker compose version`、`sudo docker ps`；能够正常工作则跳过安装。若服务器已有其他业务或容器，保留它们，使用后文独立项目名，勿直接卸载其 Docker/containerd 或执行全局 prune。

## 3. 安装并验证 Docker（仅适用于尚未安装 Docker 的 Ubuntu）

按 Docker 官方 apt 仓库方式安装。这里使用 sudo 执行 Docker，不需要把 SSH 用户加入拥有高权限的 docker 组。

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "${UBUNTU_CODENAME:-$VERSION_CODENAME}" "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
sudo docker run --rm hello-world
```

预期：能显示 Docker Server 和 Compose 版本，hello-world 成功退出。若已有冲突的软件包或安装报错，先返回错误；不要照搬卸载命令影响现有服务。

来源：[Docker Ubuntu 安装文档](https://docs.docker.com/engine/install/ubuntu/)。

## 4. 验证镜像下载，评估是否需要 swap

按顺序执行，不同时开四个下载任务：

```bash
sudo docker pull postgres:17-alpine
sudo docker pull python:3.14-slim
sudo docker pull node:24-alpine
sudo docker pull nginx:1.28-alpine
free -h
df -h /
```

这一步比只看 hello-world 更能发现 T02 遇到的镜像层下载问题。下载报错时保留失败镜像名与错误，不把网络问题直接判断为内存不足。

若 `swapon --show` 没有任何输出、根文件系统有充足剩余空间，可为构建峰值临时增加 2GB swap。仅在文件不存在时创建；已有 swap 则先跳过。

```bash
if [ -z "$(swapon --show --noheadings)" ] && [ ! -e /swapfile-research-test ]; then
  sudo dd if=/dev/zero of=/swapfile-research-test bs=1M count=2048 status=progress &&
  sudo chmod 600 /swapfile-research-test &&
  sudo mkswap /swapfile-research-test &&
  sudo swapon /swapfile-research-test
fi
swapon --show
free -h
```

这是临时配置，未修改 fstab，重启主机后不会自动启用。若文件系统不支持 swapfile 或命令失败，不反复创建，返回报错。swap 只能缓冲峰值，不替代内存；容器 OOM/长期换页时再考虑升级 4GB。[Docker 资源约束说明](https://docs.docker.com/engine/containers/resource_constraints/)

完成本节后可先把系统版本、内存/磁盘概况、Docker 版本及四个镜像是否成功发回。不要发送密码、私钥或 Docker config.json。

## 5. 修复交付后，从 Windows 上传明确的代码版本

不用先建立 GitHub 仓库。下面只打包已提交且被 Git 跟踪的文件，不带开发环境和凭据。当前有未提交修复，必须等交付完成后执行。

在本机新开 PowerShell，保留原 SSH 终端：

```powershell
Set-Location D:\files\research-manager
git status --short
# 有未交付的代码变更时，先让 Claude Code 完成提交，不要打包旧 HEAD。
if (git status --porcelain) { throw '工作区还有未提交内容，请先完成修复交付' }
$reviewSha = (git rev-parse HEAD).Trim()
New-Item -ItemType Directory -Path runtime/remote-transfer -Force | Out-Null
git archive --format=tar.gz --output=runtime/remote-transfer/research-manager-review.tar.gz HEAD
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
[IO.File]::WriteAllText((Join-Path (Get-Location) 'runtime/remote-transfer/REVIEW_COMMIT.txt'),$reviewSha,[Text.UTF8Encoding]::new($false))
scp runtime/remote-transfer/research-manager-review.tar.gz runtime/remote-transfer/REVIEW_COMMIT.txt SSH_USER@SERVER_IP:~/
```

使用密钥时给 scp 添加同样的 `-i` 参数；自定义 SSH 端口时 ssh 用 `-p`，scp 用 `-P`。

回到服务器，解压到新目录，不覆盖其他版本：

```bash
release_dir=$(mktemp -d "$HOME/research-manager-test.XXXXXX")
tar -xzf "$HOME/research-manager-review.tar.gz" -C "$release_dir"
cp "$HOME/REVIEW_COMMIT.txt" "$release_dir/REVIEW_COMMIT.txt"
cd "$release_dir"
printf 'Release directory: %s\n' "$PWD"
cat REVIEW_COMMIT.txt
```

## 6. 创建隔离配置，串行构建和启动

所有命令在同一个服务器终端、刚才的 release 目录内执行。环境文件在服务器生成，不上传本机 .env。即使生成器已修复，仍显式指定 ENV_FILE，并用 sudo env 传给 Compose，避免 sudo 丢弃该变量。

```bash
test_tag=$(date -u +%Y%m%d%H%M%S)-$$
test_project="research-manager-test-$test_tag"
test_env="runtime/env/remote-$test_tag.env"
python3 scripts/compose_env.py "$test_env"
# 测试网页固定为服务器回环 18082；同源浏览器流量经 SSH 隧道进入。
python3 - "$test_env" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1])
values=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))
values['PUBLIC_PORT']='18082'
values['FRONTEND_HOST']='http://127.0.0.1:18082'
p.write_text('\n'.join(f'{k}={v}' for k,v in values.items())+'\n')
PY

dc() {
  sudo env ENV_FILE="$PWD/$test_env" COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file "$test_env" -p "$test_project" "$@"
}
dc config --no-env-resolution --format json | python3 -c 'import json,sys; c=json.load(sys.stdin); print({k:c["services"][k]["env_file"] for k in ("backend","migrate")})'
```

确认两个服务 env_file 均为本轮 runtime/env 下文件，不是根 .env。若不符即停，不启动服务。不要打印完整 Compose config，因为其中有秘密。

```bash
dc build backend
dc build migrate
dc build frontend
dc up -d --no-build
dc ps -a
dc logs --tail 60 migrate backend
curl --fail http://127.0.0.1:18082/api/v1/utils/readiness/
```

前一个构建失败就停止，不继续下一条。backend/migrate 共用 Dockerfile，后一构建可复用缓存；不假定两个服务镜像名称相同。预期 db/backend healthy、migrate Exited(0)、frontend running，readiness 返回 database=ok。

Ubuntu 自带 Python 只用于本节标准库工具，不需要在主机安装 Python 3.14 或 Node；应用和测试依赖运行在镜像内。

## 7. 本机浏览器通过 SSH 隧道访问远端

本机 PowerShell 新开一个窗口，保持命令运行：

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 18082:127.0.0.1:18082 -L 18083:127.0.0.1:18083 SSH_USER@SERVER_IP
```

然后在本机浏览器打开 `http://127.0.0.1:18082`。这时浏览器访问的是远端容器。若本机端口被占用，可改左侧本机端口，右侧保持服务器端口不变。

登录账号/密码在服务器 `$test_env` 的 FIRST_SUPERUSER 和 FIRST_SUPERUSER_PASSWORD 中，可自行查看；不要把文件或凭据贴到对话。无需为这次验收配置域名、证书或公网应用端口。真正日常跨机器公网使用的 HTTPS 另属上线验收。

## 8. 远端数据、重启与恢复验收

先在服务器 release 目录运行 API 助手生成固定测试项目：

```bash
test_state="runtime/remote-$test_tag/fixture.json"
python3 scripts/audit/t02-api-probe.py seed --base http://127.0.0.1:18082 --env-file "$test_env" --state "$test_state"
```

预期输出 PASS，包含 revision=3、历史、副本 sequence=5、已撤销设备及 409/401。fixture 文件包含测试 token，保留本地 runtime，不发送或提交。

浏览器查看固定测试项目和历史；另建一个网页项目用于编辑、翻页、直接访问详情 URL 和冲突测试。不要修改助手固定项目，以便恢复时准确比较。

```bash
dc restart db backend frontend
# 等待 db/backend 恢复 healthy 后执行后续命令。
dc ps -a
dc run --rm migrate
python3 scripts/audit/t02-api-probe.py verify --base http://127.0.0.1:18082 --env-file "$test_env" --state "$test_state"
```

备份命令（全局参数放在子命令前）：

```bash
sudo env ENV_FILE="$PWD/$test_env" python3 scripts/postgres_backup.py --project "$test_project" --compose-env "$test_env" backup
```

按命令打印的路径设置变量，必须选刚产生的备份，勿猜旧文件。恢复到全新测试库，不使用 --force-empty：

```bash
backup_file='runtime/backups/替换为刚生成的文件名.dump'
restore_db="restore_$(date -u +%Y%m%d%H%M%S)_$$_test"
sudo env ENV_FILE="$PWD/$test_env" python3 scripts/postgres_backup.py --project "$test_project" --compose-env "$test_env" restore --file "$backup_file" --target-db "$restore_db"
restore_container="$test_project-restore-api"
dc run -d --no-deps --name "$restore_container" -e "POSTGRES_DB=$restore_db" -p 127.0.0.1:18083:8000 backend
# 等恢复 API 就绪，再运行比对。
curl --fail http://127.0.0.1:18083/api/v1/utils/readiness/
python3 scripts/audit/t02-api-probe.py verify --base http://127.0.0.1:18083 --env-file "$test_env" --state "$test_state"
```

预期：源与恢复项目/历史/副本 ID、内容、修订和序号一致；旧 revision 409，撤销设备 401。恢复 API 直接连接恢复库，不先初始化来掩盖备份缺失。保留同一 SECRET_KEY 等配置，数据库 dump 本身不包含它们。

2GB 上验证恢复 API 时会临时多一个后端进程，若内存紧，可先 `dc stop backend frontend`，再启动恢复 API；数据库保持运行，源数据不受影响。全部验证仍顺序执行。

观察资源：

```bash
sudo docker stats --no-stream
free -h
df -h /
sudo journalctl -k --since '30 minutes ago' --no-pager | grep -Ei 'out of memory|oom|killed process' || true
```

如有 OOM、反复容器重启或持续大量换页，再评估升级 4GB。访问慢也可能是网络或镜像下载问题，需看实际证据。

保留现场，先只停止本轮服务：`dc stop`；若启动恢复 API，再 `sudo docker stop "$restore_container"`。不执行全局 prune 或未经核对的 down -v。测试 env、密钥和数据库备份都不入 Git。

将 REVIEW_COMMIT.txt 的 SHA、Docker 版本、各步骤 PASS/失败、脱敏后的错误与资源摘要发回。真实 PostgreSQL 测试、旧版本迁移和并发矩阵仍须按 T02 任务卡补齐，以上手动流程不替代完整任务验收。