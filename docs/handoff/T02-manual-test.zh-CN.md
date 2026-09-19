# T02 手动验证步骤（审计补充）

当前 HEAD `6206329` 有三项待修复代码问题，详见 [T02-review](reports/T02-review.md)。现在可以执行第 1 步恢复 Docker；第 2 步以后建议在 Claude Code 修复并重新交付后执行。下面显式指定 ENV_FILE 并使用正确的备份参数顺序，避免重复原说明中的隔离和命令问题；手动运行成功也不能替代默认测试连接缺陷的修复。

本说明和辅助脚本尚未在可用 Docker 上执行，所有预期结果均是验收标准，不是已通过声明。任一步不符就停在该步，保留错误，不继续清库或恢复。

## 1. 先恢复 Docker

在 Docker Desktop 中手动 Restart；等待引擎就绪。不要 Factory reset，不要清空 Docker 数据或注销 WSL 发行版。然后打开一个专门用于本次测试的 PowerShell：

```powershell
Set-Location D:\files\research-manager
docker version
docker compose version
```

`docker version` 必须同时有 Client 与 Server。若仍为 500 或连接失败，只把这一输出发回即可，不继续以下步骤。不要发送 Docker config.json、env 文件或凭据。

## 2. 创建专属环境并验证隔离

下面命令在同一个 PowerShell 窗口中执行；每轮使用新的名称。

```powershell
$testTag = [guid]::NewGuid().ToString('N').Substring(0,12)
$testProject = 'research-manager-test-' + $testTag
$testEnv = 'runtime/env/t02-manual-' + $testTag + '.env'
$testState = 'runtime/t02-manual-' + $testTag + '/fixture.json'
$testPort = 18082
.\.venv\Scripts\python.exe scripts/compose_env.py $testEnv
if ($LASTEXITCODE -ne 0) { throw '环境文件生成失败' }
# 显式指定 service env_file；--env-file 本身只控制插值。
$env:ENV_FILE = (Resolve-Path $testEnv).Path
$env:PUBLIC_PORT = [string]$testPort
$testEnvText = [IO.File]::ReadAllText($env:ENV_FILE)
$testEnvText = $testEnvText -replace '(?m)^PUBLIC_PORT=.*$', ('PUBLIC_PORT=' + $testPort)
$testEnvText = $testEnvText -replace '(?m)^FRONTEND_HOST=.*$', ('FRONTEND_HOST=http://127.0.0.1:' + $testPort)
[IO.File]::WriteAllText($env:ENV_FILE,$testEnvText,[Text.UTF8Encoding]::new($false))
function dc {
    & docker compose --env-file $testEnv -p $testProject @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose 命令失败；停在当前步骤' }
}
$configText = dc config --no-env-resolution --format json
$config = $configText | ConvertFrom-Json
foreach ($service in @('backend','migrate')) {
    if ($config.services.$service.env_file[0].path -ne $env:ENV_FILE) {
        throw '隔离检查失败：容器未使用本轮 env 文件'
    }
}
'PASS: 两个应用服务均使用专属 env 文件'
```

不要输出 `$configText` 或 `$testEnvText`，其中有测试秘密。若 18082 被占用，先修改 `$testPort` 再执行本节，勿结束其他服务。保持本终端打开，以保留项目名、env 路径和后续变量。

## 3. 构建与启动

```powershell
dc up -d --build
dc ps -a
dc logs --tail 60 migrate backend
Invoke-RestMethod "http://127.0.0.1:$testPort/api/v1/utils/readiness/"
```

预期：db/backend healthy；migrate Exited (0)；frontend running；readiness 返回 database=ok。镜像下载失败或 daemon 再次 500 时，记录失败镜像和报错即可；无需换陌生镜像源或清空 Docker。构建完成不是验收通过，必须继续核对服务。

## 4. 准备可恢复的测试数据及网页检查

```powershell
.\.venv\Scripts\python.exe scripts/audit/t02-api-probe.py seed `
  --base "http://127.0.0.1:$testPort" --env-file $testEnv --state $testState
if ($LASTEXITCODE -ne 0) { throw 'API 测试数据或断言失败' }
```

辅助脚本只向隔离服务写入人工测试记录，不扫描本地仓库。它创建 revision=3 的项目、历史、设备与副本，上报序号 5/2/5，撤销测试设备，检查旧版本 409 与撤销凭据 401。应输出两个 PASS。fixture.json 含一次性已撤销设备 token，只保留本地 runtime，不发送或提交。

浏览器打开 `http://127.0.0.1:18082`（若换端口按实际值）。使用专属 env 文件内的 FIRST_SUPERUSER / FIRST_SUPERUSER_PASSWORD 登录；可用 `notepad $env:ENV_FILE` 本地查看，不把文件内容发回。

- 查看“T02 manual acceptance”及三条历史，展开核对内容。
- 复制项目详情 URL，新开标签直接访问，确认 SPA 路由可以加载。
- 另外新建一个网页测试项目，验证保存、历史分页、两个会话冲突保留草稿。不要修改上面辅助脚本的固定测试项目，以免破坏恢复比对基准。
- 有条件时对网页项目复跑 T01 的慢 PUT、慢 GET 与断网草稿场景；未做则记未验证。

## 5. 重启与幂等初始化

```powershell
dc restart db backend frontend
# 等待 db/backend 恢复 healthy 后继续。
dc ps -a
dc run --rm migrate
.\.venv\Scripts\python.exe scripts/audit/t02-api-probe.py verify `
  --base "http://127.0.0.1:$testPort" --env-file $testEnv --state $testState
if ($LASTEXITCODE -ne 0) { throw '重启或初始化后数据检查失败' }
```

预期：再次初始化不清项目和历史，原账号仍能登录，辅助脚本所有断言通过。如果额外通过网页改过测试账号密码，再执行初始化后新密码仍应有效；该额外检查未做则记录未验证。

## 6. 备份、恢复到全新库并验证真实 API

这是同一个隔离 PostgreSQL 实例内的第二个全新库，不覆盖源库。不要传 --force-empty，不使用已有库名。

```powershell
$beforeBackups = @(Get-ChildItem runtime/backups -Filter '*.dump' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
.\.venv\Scripts\python.exe scripts/postgres_backup.py --project $testProject --compose-env $testEnv backup
if ($LASTEXITCODE -ne 0) { throw '备份失败' }
$newBackups = @(Get-ChildItem runtime/backups -Filter '*.dump' | Where-Object { $_.FullName -notin $beforeBackups })
if ($newBackups.Count -ne 1) { throw '无法唯一确定本轮备份文件' }
$restoreDb = 'restore_' + $testTag + '_test'
.\.venv\Scripts\python.exe scripts/postgres_backup.py --project $testProject --compose-env $testEnv restore `
  --file $newBackups[0].FullName --target-db $restoreDb
if ($LASTEXITCODE -ne 0) { throw '恢复失败' }
$restoreContainer = $testProject + '-restore-api'
dc run -d --no-deps --name $restoreContainer -e "POSTGRES_DB=$restoreDb" `
  -p '127.0.0.1:18083:8000' backend
# 等该 API 就绪；它直接读取恢复库，不运行初始化来掩盖恢复缺失。
Invoke-RestMethod 'http://127.0.0.1:18083/api/v1/utils/readiness/'
.\.venv\Scripts\python.exe scripts/audit/t02-api-probe.py verify `
  --base 'http://127.0.0.1:18083' --env-file $testEnv --state $testState
if ($LASTEXITCODE -ne 0) { throw '恢复后的 API 数据或权限校验失败' }
```

预期：辅助脚本逐项比较项目/历史/副本 UUID、内容、revision、观察序号，确认撤销状态保留；旧 revision 仍 409，撤销设备仍 401。仅出现 dump 文件不算成功。端口 18083 被占用时改用另一空闲端口，并同步修改本节 URL。

恢复库复用同一测试 env，保留 SECRET_KEY 等配置。真实部署时这些配置需另行妥善备份，数据库 dump 不包含它们。

## 7. 返回结果与保留现场

返回：被测 git HEAD、Docker Server 版本、每一步是否通过、脚本 PASS/失败摘要、脱敏后的失败日志。不要发 env、fixture.json、完整连接串、数据库备份或 token。

- 不通过的步骤停下，不通过重复恢复或清库把错误掩盖。
- 可先停止测试服务并保留卷供复核：`dc stop`。若启动了恢复 API，再执行 `docker stop $restoreContainer`。
- 暂不执行 `down -v`；等本轮结果确认后再按准确项目名清理。
- 本手动流程主要补齐容器、同源网页、重启及恢复证据。全新 PG 测试、旧版本迁移、并发与其他任务卡检查仍须由实现者/审计者在环境恢复后运行并记录，不能凭本页冒烟测试替代全部 T02 验收。