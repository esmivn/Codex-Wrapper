# Test Skill Guide

这个文件用于指导对当前 `Codex-Wrapper` 的关键能力做高价值测试，重点覆盖：

- 多用户隔离
- 该允许的读写必须成功
- 不该允许的读写必须失败
- 进程生命周期正确，不残留 zombie
- API、前端、会话、文件服务等关键回归

目标不是把所有测试都塞进一轮，而是确保每次改动后，至少把最关键的安全边界和用户路径验证一遍。

## 测试原则

- 优先验证“真实边界”，不要只看模型口头回答。
- 优先检查实际文件是否存在、实际路径是否可访问、实际进程是否退出。
- 对安全相关改动，要同时测“允许的行为”与“禁止的行为”。
- 对远端部署相关改动，要区分：
  - 本地单元测试是否通过
  - 远端运行中的容器是否真的生效
- 每次涉及 sandbox、workspace、`user_id`、`chat_id`、容器启动方式、PID 1、镜像构建的改动，都应至少跑一轮本指南。

## 一、用户隔离

### 1. 默认用户只能看到自己的 workspace

验证点：
- `default` 用户会话的工作目录应在 `/workspace/default/<chat_id>`
- `default` 的隔离 Codex 进程不应能读到 `/workspace/alice/...`
- `default` 的隔离 Codex 进程不应能读到 `/workspace/bob/...`

建议测试：
1. 在容器内手工创建：
   - `/workspace/alice/test.txt`
   - `/workspace/bob/test.txt`
2. 通过 `default` 用户会话发送请求，让 Codex 尝试读取这些路径。
3. 同时直接在隔离启动边界里执行探针命令验证：
   - `test -e /workspace/alice/test.txt && echo exists || echo missing`
   - `test -e /workspace/bob/test.txt && echo exists || echo missing`

期望结果：
- `default` 看不到 `alice` / `bob` 的文件
- 探针结果应为 `missing`

### 2. 非默认用户只能看到自己的 workspace

验证点：
- `alice` 用户会话的工作目录应在 `/workspace/alice/<chat_id>`
- `alice` 不应能读到 `/workspace/default/...`
- `alice` 不应能读到 `/workspace/bob/...`

建议测试：
1. 使用 `x_codex.user_id=alice` 且带 `chat_id`
2. 请求读取：
   - `/workspace/default/...`
   - `/workspace/bob/...`
3. 用隔离探针重复验证

期望结果：
- 全部失败或返回不存在

### 3. 未带 `chat_id` 的非默认用户请求应被拒绝

验证点：
- 当 `CODEX_ISOLATE_USER_WORKSPACE=1` 时，`user_id != default` 且没有 `chat_id` 的请求必须失败

期望结果：
- API 返回 `400`
- 错误信息明确指出需要 `chat_id`

## 二、允许的读写必须成功

### 1. 默认用户在自己会话目录内可写

建议测试：
1. 发送请求：
   - 创建 `123.txt`
   - 写入 `123`
   - 返回完整路径
2. 检查：
   - 文件实际存在
   - 大小正确
   - 内容正确
   - HTTP 文件服务可访问

期望结果：
- 文件创建成功
- 浏览器链接可打开

### 2. 非默认用户在自己会话目录内可写

建议测试：
1. 使用 `user_id=alice`、`chat_id=<some-chat>`
2. 创建例如 `hello.txt`
3. 检查：
   - `/workspace/alice/<chat_id>/hello.txt` 存在
   - 内容正确
   - 对应 `/workspace/alice/<chat_id>/hello.txt` 的 HTTP 路由可访问

### 3. 上传文件后 Codex 能看到并使用

验证点：
- 前端上传到当前会话的文件，Codex 在后端工作目录里应能直接看到

建议测试：
1. 上传一个文本文件或图片
2. 再请求 Codex 读取或描述该文件
3. 检查实际文件是否写到当前用户当前会话目录

期望结果：
- 文件保存成功
- Codex 能访问并使用

## 三、不允许的读写必须失败

### 1. 不应能写其他用户 workspace

建议测试：
- `default` 尝试写 `/workspace/alice/evil.txt`
- `alice` 尝试写 `/workspace/default/evil.txt`

期望结果：
- 写入失败
- 实际文件不存在

### 2. 不应能删除或修改系统文件

建议测试：
- 在当前 Codex 实际执行边界中尝试：
  - `rm -f /bin/pip`
  - `touch /etc/should-not-write`
  - `echo x > /usr/bin/anything`

期望结果：
- 返回只读文件系统、权限错误或路径不存在
- 原文件仍存在

### 3. 不应能读取未挂载的其他用户目录

建议测试：
- 在当前用户隔离进程内执行：
  - `ls /workspace/alice`
  - `cat /workspace/alice/test.txt`

期望结果：
- 报不存在或无法访问

## 四、进程生命周期与 zombie

### 1. 用户发消息时应启动新的 Codex 进程

建议测试：
1. 发一个会执行 `sleep 5` 的请求
2. 请求进行中检查容器进程：
   - `bwrap`
   - `node /usr/bin/codex`
   - `codex`

期望结果：
- 请求进行中能看到这条新进程链

### 2. 请求结束后进程应退出

建议测试：
1. 等请求完成
2. 再次检查 `ps`

期望结果：
- 活动 `codex` / `bwrap` 进程消失

### 3. 不应留下新的 zombie 进程

验证点：
- 请求结束后不应新增 `bwrap <defunct>` 或 `codex <defunct>`

期望结果：
- `ps` 中无新的 defunct 项

### 4. 超时请求应被杀掉

建议测试：
1. 发送故意超时的请求
2. 检查返回码与错误消息
3. 请求结束后检查进程是否已退出

期望结果：
- API 返回超时错误
- 子进程不残留

## 五、API 回归

### 1. `/v1/chat/completions`

至少覆盖：
- 非流式请求
- 流式请求
- 带 `chat_id`
- 带 `user_id`
- OpenRouter 模型
- 默认 fallback 模型

验证点：
- 返回结构合法
- debug headers 正确：
  - `X-Codex-Requested-Model`
  - `X-Codex-Resolved-Model`
  - `X-Codex-Resolved-Label`
  - `X-Codex-Resolved-Provider`
  - `X-Codex-Fallback-Applied`

### 2. `/v1/responses`

至少覆盖：
- 非流式
- 流式
- 输出事件顺序

### 3. `/v1/models`

验证点：
- 服务重启后仍正常返回
- OpenRouter key 存在时模型列表完整
- 默认模型正确

### 4. session API

至少覆盖：
- `GET /v1/chat/sessions/{chat_id}`
- `GET /v1/chat/sessions`
- `DELETE /v1/chat/sessions/{chat_id}`
- `POST /v1/chat/sessions/{chat_id}/files`

验证点：
- 只操作当前用户当前会话目录
- 删除时会删掉对应会话目录下的文件

## 六、文件服务回归

### 1. 生成文件可被 HTTP 访问

建议测试：
- 让 Codex 生成 `html`、`txt`、图片等文件
- 访问 `/workspace/<user_id>/<chat_id>/<path>`

期望结果：
- 可直接访问
- 路由不会越权

### 2. 路径穿越必须失败

建议测试：
- 访问带 `../` 的路径
- 访问隐藏目录

期望结果：
- 400 或 404

## 七、前端回归

### 1. 最近会话

验证点：
- 只显示最近 6 条
- 标题优先显示首条用户消息摘要
- 删除按钮有效

### 2. 模型选择

验证点：
- `localStorage` 记住上次模型
- 可搜索模型
- 切换模型不影响历史消息上的模型标签

### 3. assistant 渲染

验证点：
- assistant 标签包含历史模型名
- HTML 片段能正确渲染
- 暗黑模式切换即时生效
- iframe 预览跟随容器尺寸调整

### 4. 文件上传

验证点：
- 上传后列表刷新
- 文件实际进入当前会话目录
- Codex 能使用上传文件

## 八、Skills 回归

### 1. 共享只读 skill 对所有用户可见

验证点：
- 共享 skill 放在宿主机共享目录后，`default`、`alice` 等不同用户都能调用
- `Codex` 实际能识别该 skill，而不是 wrapper 伪造结果

建议测试：
1. 在宿主机共享 skills 目录创建：
   - `<system-skills-host>/<skill-name>/SKILL.md`
2. 通过不同 `user_id` 分别调用：
   - `$shared-skill-test`
3. 再在会话里执行：
   - `/skills`

期望结果：
- 不同用户都能成功调用共享 skill
- `/skills` 中能看到该 skill

### 2. 用户私有 skill 仅当前用户可见

验证点：
- `default` 只能看到自己的 user skill
- `alice` 只能看到自己的 user skill
- 其他用户不能调用、不能在 `/skills` 里看到

建议测试：
1. 在宿主机用户目录创建：
   - `<user-skills-host>/default/default-skill-test/SKILL.md`
   - `<user-skills-host>/alice/alice-skill-test/SKILL.md`
2. `default` 调用：
   - `$default-skill-test`
   - `$alice-skill-test`
3. `alice` 调用：
   - `$alice-skill-test`
   - `$default-skill-test`

期望结果：
- 各自只能成功调用自己的私有 skill
- 调用其他用户 skill 时应失败并明确表示该 skill 不可用

### 3. 用户私有 skill 跨 chat_id 可复用

验证点：
- 同一个 `user_id` 在不同 `chat_id` 下都能看到同一份用户私有 skill

建议测试：
1. `default` 在 `chat-a` 调用 `$default-skill-test`
2. `default` 在 `chat-b` 再次调用 `$default-skill-test`

期望结果：
- 两个不同会话都成功
- 不需要每个会话单独复制一份 skill

### 4. 用户应能创建或更新自己的 skill

验证点：
- Codex 在当前用户权限下可写 user skill 目录
- 新建或更新结果真实落到宿主机

建议测试：
1. 让 Codex 创建：
   - `<user-skill-root>/<skill-name>/SKILL.md`
2. 宿主机直接检查该文件是否存在
3. 再调用该 skill

期望结果：
- 文件落在宿主机用户 skill 目录
- 该用户后续能调用该 skill

### 5. 共享 skill 必须只读

验证点：
- Codex 不能修改共享 skill 文件
- 宿主机原文件不变

建议测试：
1. 让 Codex 尝试覆盖：
   - `/etc/codex/skills/<skill-name>/SKILL.md`
2. 直接检查宿主机共享 skill 文件内容

期望结果：
- 修改失败
- 宿主机原始文件未变化

### 6. 非法 skill 格式应被修正或拒绝

验证点：
- 缺 front matter 的 `SKILL.md` 不应悄悄变成“持久化了但不可加载”的坏状态
- 当前实现应自动补齐 front matter 并回写宿主机

建议测试：
1. 手工放一个缺 front matter 的：
   - `<user-skills-host>/<user_id>/<skill-name>/SKILL.md`
2. 触发一次该用户的 Codex 请求
3. 检查宿主机文件是否已补齐：
   - `name`
   - `description`
   - `---` front matter
4. 再调用该 skill

期望结果：
- 文件被自动修正或被明确拒绝
- 不会出现“文件存在但 Codex 永远看不到”的半坏状态

### 7. skills 持久化到宿主机并在容器重建后仍生效

验证点：
- shared/user skills 都不应随着容器删除或 `force-recreate` 丢失
- 重建后不仅文件还在，而且 Codex 仍能加载它们

建议测试：
1. 记录重建前可用的 skill：
   - shared skill
   - user skill
   - 用户新建的 skill
2. 执行远端：
   - `docker compose up -d --force-recreate`
3. 检查宿主机 skill 文件仍存在
4. 再调用这些 skill

期望结果：
- 宿主机文件仍在
- 重建后技能仍可调用

### 8. `/skills` 与显式 `$skill-name` 行为一致

验证点：
- `/skills` 列出的 skill 与实际可调用 skill 一致
- 不应出现“列出来但不能用”或“能用但列不出来”的明显偏差

期望结果：
- `/skills` 可作为当前会话技能可见性的审计依据

## 九、OpenRouter 与模型路由

### 1. OpenRouter 模型可见

验证点：
- 配置 `OPENROUTER_API_KEY` 后，`/v1/models` 包含 OpenRouter 模型

### 2. OpenRouter 实际调用成功

建议测试：
- `qwen/qwen3.6-plus`
- `google/gemma-4-31b-it`

验证点：
- 调用返回 200
- debug header 显示：
  - `X-Codex-Resolved-Provider: openrouter`
  - `X-Codex-Fallback-Applied: false`

### 3. 无 OpenRouter key 时 fallback 正确

验证点：
- 默认模型回退到预期值
- 不会报 provider 配置错误

## 十、部署与镜像回归

### 1. 新镜像启动后行为不回退

验证点：
- 新镜像不能只在热更新容器里有效
- 重建容器后：
  - 隔离仍有效
  - 默认用户写文件仍有效
  - OpenRouter 仍有效

### 2. PID 1 行为正确

验证点：
- 容器内 PID 1 应是 init 进程链，而不是裸应用进程
- 例如 `docker-init` / `tini` 在前面

### 3. 远端配置持久化

验证点：
- 远端 `.env`、compose、认证目录与 volume 配置在容器重建后仍生效

## 十一、推荐最小回归集

如果每次改动后时间有限，至少做这 12 项：

1. `pytest` 跑权限与 workspace 相关单测
2. `/v1/models` 返回正常
3. `default` 用户创建文件成功
4. `default` 看不到 `/workspace/alice/test.txt`
5. `alice` 看不到 `/workspace/default/...`
6. 共享 skill 可调用
7. 当前用户私有 skill 可调用
8. 其他用户私有 skill 不可调用
9. 宿主机 skill 文件存在且格式正确
10. OpenRouter 模型调用成功
11. 请求结束后无活动 `codex` / `bwrap` 残留
12. 无新增 zombie 进程

## 十二、推荐记录格式

每次做远端验证，建议记录：

- 镜像 tag / digest
- 容器启动时间
- 关键环境变量：
  - `CODEX_WORKDIR`
  - `CODEX_DEFAULT_USER_ID`
  - `CODEX_ISOLATE_USER_WORKSPACE`
  - `CODEX_SANDBOX_MODE`
- 成功用例
- 失败用例
- 进程检查结果
- 是否留下 zombie
- skills 挂载宿主路径
- skills 重建前后是否仍可调用

这样后续才能判断问题是代码回退、镜像回退，还是部署配置没带上。
