# Remote Deploy Skill Guide

这个文件用于指导如何把当前 `Codex-Wrapper` 部署到远程机器，并在部署后验证系统确实正常工作。

适用场景：

- 把本地修改快速部署到远程主机
- 重建远程容器而不手工逐条敲命令
- 更新镜像、compose、环境变量
- 验证远程服务、OpenRouter、workspace、隔离与进程行为

本文默认：

- 远程主机可通过 SSH 访问
- 远程主机安装了 Docker 与 Docker Compose
- 你有权限执行远程 `docker load` / `docker compose up`
- 远程服务使用仓库里的 `deploy/remote/compose.yaml`

## 一、部署目标

远程部署应保证以下结果：

- 远程容器启动成功
- `/v1/models` 可访问
- 聊天 API 可调用
- 默认用户会话目录在 `/workspace/default/<chat_id>`
- 当前用户可在自己的会话目录里读写
- 其他用户目录不可见
- HTTP 文件服务可访问当前会话文件
- OpenRouter 配置在远端仍然有效
- 请求结束后无新的 zombie 进程残留

## 二、推荐部署方式

优先使用“本地构建镜像 + 通过 SSH 传到远端 + 远端 compose 重建”。

推荐原因：

- 可控
- 不依赖远端直接从 registry 拉镜像
- 能保证远端实际跑的是你本地当前代码对应的镜像

## 三、关键文件

远程部署相关文件：

- [compose.yaml](/Users/starsky/projects/Codex-Wrapper/deploy/remote/compose.yaml)
- [.env.example](/Users/starsky/projects/Codex-Wrapper/deploy/remote/.env.example)
- [deploy_remote_codex_wrapper.sh](/Users/starsky/projects/Codex-Wrapper/scripts/deploy_remote_codex_wrapper.sh)

如果是按用户单独实例部署，还要看：

- [compose.yaml](/Users/starsky/projects/Codex-Wrapper/deploy/user-isolated/compose.yaml)
- [.env.example](/Users/starsky/projects/Codex-Wrapper/deploy/user-isolated/.env.example)
- [deploy_remote_user_wrapper.sh](/Users/starsky/projects/Codex-Wrapper/scripts/deploy_remote_user_wrapper.sh)

## 四、部署前检查

部署前至少确认：

1. 本地代码已准备好
2. 本地镜像能成功 build
3. 远程 `.env` 里所需 secrets 已准备
4. 远程宿主的认证目录存在
5. 远程宿主的 workspace volume 或宿主路径存在

重点变量：

- `CODEX_APPROVAL_POLICY`
- `CODEX_DEFAULT_USER_ID`
- `CODEX_WORKDIR`
- `CODEX_ISOLATE_USER_WORKSPACE`
- `CODEX_SANDBOX_MODE`
- `CODEX_ALLOW_DANGER_FULL_ACCESS`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `CODEX_AUTH_DIR`

## 五、本地构建镜像

当前远端部署建议始终构建 `linux/amd64` 镜像。

示例：

```bash
docker buildx build --platform linux/amd64 -t codex-wrapper:sandbox-amd64 --load .
```

原因：

- 如果本地是 Apple Silicon，而远端是 x86_64，直接 `docker build` 可能产出错误架构
- 远端运行时会出现 `exec format error`

## 六、同步远程 compose

先把最新 `compose.yaml` 同步到远端部署目录。

示例：

```bash
ssh <remote> "mkdir -p ~/codex-wrapper-deploy && cat > ~/codex-wrapper-deploy/compose.yaml" < deploy/remote/compose.yaml
```

如果远端 `.env` 还没准备：

```bash
scp deploy/remote/.env.example <remote>:~/codex-wrapper-deploy/.env.example
```

然后在远端复制并编辑：

```bash
cp ~/codex-wrapper-deploy/.env.example ~/codex-wrapper-deploy/.env
```

## 七、把镜像传到远端

推荐通过 `docker save | ssh ... docker load`。

示例：

```bash
docker save codex-wrapper:sandbox-amd64 | ssh <remote> 'sudo -n docker load'
```

这个步骤结束后，应在远端看到：

- `Loaded image: codex-wrapper:sandbox-amd64`

## 八、重建远端容器

示例：

```bash
ssh <remote> "cd ~/codex-wrapper-deploy && sudo -n docker compose -f compose.yaml up -d --force-recreate"
```

如果只是重启而不是重建，新的镜像和新环境变量可能不会真正生效。

所以涉及以下任一情况时，必须用 `--force-recreate`：

- 镜像更新
- `ENTRYPOINT` / `CMD` 更新
- 环境变量更新
- 卷挂载更新
- `security_opt` 更新

## 九、当前远端部署的关键要求

### 1. 需要 `seccomp=unconfined`

这是 Codex Linux sandbox / `bubblewrap` 在当前远端环境中工作的必要条件之一。

### 2. 需要 `apparmor=unconfined`

当前远端 Ubuntu 主机上，如果没有这个设置，`bubblewrap` 相关执行会失败。

### 3. 需要 init 进程回收子进程

当前推荐做法：

- 镜像里安装 `tini`
- 作为 `ENTRYPOINT`

这样请求结束后，Codex / `bwrap` 子进程能被回收，不留下新的 zombie。

## 十、快速 Patch 运行中容器

可以，而且这应该作为“快速验证 / 紧急热修”的标准手段写进流程。

适用场景：

- 只改 Python 代码、HTML、CSS、JS、模板、文案
- 想快速验证一个修复是否有效
- 不想每次都花时间重新 build 镜像

不适用场景：

- `Dockerfile` 改动
- 系统包变更
- Node / Python 依赖变更
- `ENTRYPOINT` / `CMD` 变更
- 镜像层内文件布局变更
- 需要长期保留的正式发布版本

### 推荐热修步骤

1. 把本地文件直接覆盖进运行中的容器
2. 重启容器
3. 做最小回归验证
4. 最后仍要把改动进入 Git，并在合适时机重做正式镜像

### 示例：覆盖单个文件

例如更新 `app/codex.py`：

```bash
ssh <remote> "sudo -n docker exec -u 0 -i codex-wrapper sh -lc 'cat > /app/app/codex.py'" < app/codex.py
ssh <remote> "sudo -n docker restart codex-wrapper"
```

例如更新前端 `chat.html`：

```bash
ssh <remote> "sudo -n docker exec -u 0 -i codex-wrapper sh -lc 'cat > /app/app/static/chat.html'" < app/static/chat.html
ssh <remote> "sudo -n docker restart codex-wrapper"
```

### 何时必须同时改 compose

如果改动涉及这些内容，仅热拷文件不够：

- 环境变量
- 挂载卷
- `security_opt`
- 端口
- 启动命令

这时应：

1. 先同步 `compose.yaml`
2. 必要时同步 `.env`
3. 执行：

```bash
docker compose up -d --force-recreate
```

### 何时必须重做镜像

这些情况不能只热 patch：

- 新增系统包，例如 `tini`
- 修改 `ENTRYPOINT`
- 修改 Python / Node 依赖
- 想让修复在下次容器重建后仍然存在

这时应走完整流程：

1. 本地 build 新镜像
2. `docker save | ssh ... docker load`
3. 远端 `docker compose up -d --force-recreate`

### 快速 Patch 后的最低验证

至少做：

1. `GET /v1/models`
2. 一个最小聊天请求
3. 如果改动涉及文件系统，再测一次创建文件
4. 如果改动涉及隔离，再测一次跨用户访问失败

### 风险说明

快速 patch 的本质是“热修运行中的容器”，不是正式发布。

风险：

- 容器一旦被重新创建，热修内容会丢
- 本地工作区、Git、远端运行状态可能短时间不一致
- 如果只 patch 了代码但没 patch compose / env，容易出现“看起来改了，其实配置没生效”

因此建议：

- 把热修当作验证手段，不当作最终交付
- 热修确认有效后，尽快把改动提交并重建正式镜像

## 十一、部署后必须验证的内容

至少做下面这些检查。

### 1. 容器配置是否真的生效

检查：

```bash
docker inspect codex-wrapper --format 'Image={{.Image}} Init={{.HostConfig.Init}} Entrypoint={{json .Config.Entrypoint}} Cmd={{json .Config.Cmd}}'
```

重点看：

- 是否是预期镜像
- `Entrypoint` 是否包含 `tini`

### 2. PID 1 是否正确

检查：

```bash
docker exec codex-wrapper ps -p 1 -o pid,comm,args=
```

期望：

- PID 1 是 `docker-init` / `tini` 链
- 不是裸 `uvicorn`

### 3. `/v1/models` 是否正常

检查：

```bash
curl -sS http://<host>:8020/v1/models
```

期望：

- 返回 200
- OpenRouter key 存在时模型列表应完整

### 4. 默认用户写文件是否成功

建议请求：

- 创建一个 `123.txt`
- 写入 `123`

期望：

- 文件实际出现在 `/workspace/default/<chat_id>/123.txt`
- 可通过 HTTP 访问

### 5. 用户隔离是否仍然成立

建议：

1. 在容器内手工创建 `/workspace/alice/test.txt`
2. 用 `default` 的隔离进程检查：

```bash
test -e /workspace/alice/test.txt && echo exists || echo missing
```

期望：

- `missing`

### 6. 请求结束后是否留 zombie

建议：

1. 发一个会 `sleep 5` 的请求
2. 请求中检查活动进程
3. 请求结束后再次检查：

```bash
ps -eo pid,ppid,stat,comm,args | grep -E "bwrap|codex" | grep -v grep
```

期望：

- 请求中能看到活动进程
- 请求后这些活动进程消失
- 不出现新的 `<defunct>`

## 十二、推荐部署后回归清单

每次部署后至少执行：

1. `/v1/models`
2. 默认用户创建文件
3. HTTP 打开该文件
4. `default` 看不到 `alice`
5. OpenRouter 模型调用一次
6. 请求结束后无新增 zombie

## 十三、常见问题

### 1. 远端容器启动了，但跑的还是旧代码

常见原因：

- 镜像还没 `docker load` 完，就先 `compose up`
- 只是 `restart`，没有 `force-recreate`

修复：

1. 先确认 `docker load` 完成
2. 再执行：

```bash
docker compose up -d --force-recreate
```

### 2. Apple Silicon 本地构建后远端报 `exec format error`

原因：

- 本地构建出了 ARM 镜像，远端是 x86_64

修复：

```bash
docker buildx build --platform linux/amd64 ...
```

### 3. 隔离功能没生效

检查：

- `CODEX_ISOLATE_USER_WORKSPACE=1` 是否真的在远端容器里
- 当前跑的镜像是否是最新
- 请求是否携带了正确的 `user_id`
- 非默认用户是否带了 `chat_id`

### 4. 默认用户明明该能写，却写失败

优先排查：

- 外层 per-user `bwrap` 已启用，但内层 Codex sandbox 仍在错误嵌套
- 当前代码是否已包含“外层隔离时内层改为 `danger-full-access`”的修正

### 5. `init: true` 看起来写了，但 PID 1 仍不对

不要只信 compose 文件，要看实际运行结果：

```bash
docker inspect ...
docker exec ... ps -p 1 ...
```

如果还不稳定，优先把 `tini` 直接放进镜像的 `ENTRYPOINT`。

## 十四、建议记录

每次远端部署最好记录：

- 本地镜像 tag / digest
- 远端容器重建时间
- `docker inspect` 输出摘要
- `/v1/models` 验证结果
- 默认用户文件写入结果
- 隔离探针结果
- zombie 检查结果

这样后续出问题时，能快速区分是：

- 镜像版本问题
- compose 没更新
- `.env` 没带上
- 远端主机限制变化
