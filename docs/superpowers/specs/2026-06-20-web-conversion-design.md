# Aham Voice Web 化改造设计（v2）

> 日期：2026-06-20
> 状态：设计已批准，待出实施计划
> 改造来源：[github.com/li599198347-svg/aham-voice](https://github.com/li599198347-svg/aham-voice) v0.1.0（macOS 桌面版）
> 新仓库：`aham-voice-web`（fork 自原项目，独立演进）
> 历史版本：v1（见 `-v1-deprecated.md`）因 Mac 路线决策变更作废

## 一、改造目标

原项目是一个 macOS 单机桌面录音转写应用（pywebview + 单进程单用户 + 绑 127.0.0.1）。本次改造 **fork 出新仓库 `aham-voice-web`**，做成 **Linux + Windows 的 Docker Web 应用**。

### 三平台分工（核心决策）

| 平台 | 用什么 | GPU | 由谁维护 |
|---|---|---|---|
| **Mac** | **原 repo**（pywebview 桌面版） | MPS ✅ | 原项目，本次不碰 |
| **Linux** | **新仓库 Docker 镜像** | CUDA ✅（gpu 镜像）/ CPU | 本次改造 |
| **Windows** | **新仓库 Docker 镜像**（同一个） | CPU only | 本次改造 |

**为什么 Mac 用原 repo：** Mac 原生跑能用 MPS GPU 加速，而所有 Mac 上的 Linux 容器方案（Docker/Podman/apple/container/libkrun）都无法让 PyTorch MPS 工作（MPS 需要原生 macOS Metal 调用，Linux guest 访问不到 Apple GPU）。Mac 有现成的、能跑 MPS 的桌面版，没必要重复造轮子。

**为什么 Windows 接受 CPU only：** Windows 上原生装 FunASR 全栈（torch/funasr/CUDA 版本匹配）很折腾，而 Docker 把这些麻烦全消灭。反正 WSL2 GPU 透传也折腾且不稳、Windows ARM64 还跑不了 PyTorch，直接宣布"Windows = CPU 推理"，省掉一切 GPU 适配。慢一点但能跑、稳定、零配置——对工具更重要。

**Linux + Windows 共用同一个 Docker 镜像**，这是容器化的核心价值兑现。文档一套，命令一套。

### 改造前后对比

| 维度 | 原项目（Mac 桌面） | 新项目（Linux/Windows Web） |
|---|---|---|
| 形态 | pywebview 原生窗口 | 浏览器访问 |
| 部署 | `.app` bundle + `.dmg` | Docker 镜像（cpu + gpu 双变体） |
| 启动 | 双击 .app | `docker compose up -d` |
| 服务管理 | 关窗即退出 | `restart: unless-stopped` 崩溃自拉起 |
| 平台 | 仅 macOS Apple Silicon | Linux（x64/arm64）+ Windows（x64，Docker Desktop） |
| GPU | MPS | Linux: CUDA 或 CPU / Windows: CPU only |
| 绑定 | 127.0.0.1，仅本机 | 0.0.0.0，局域网可达（手机/平板） |
| 访问控制 | 无（裸奔） | 单密码门（cookie token） |
| 模型分发 | 打进 .app bundle（~4GB） | volume 挂载，首次自动下载 |
| 配置 | 运行时 env | `.env` 文件 |
| 后端代码 | 单文件 4139 行 | 12 个模块（中等粒度） |
| ffmpeg | dylib 重定位 + ad-hoc 签名 | `apt install ffmpeg`（一行） |

### 不变的部分（核心业务逻辑，从原项目搬来）

以下在改造中**逻辑不动**，保留原项目的工程精华：

- FunASR 管线（Paraformer + FSMN-VAD + CT-Punc + CAM++）
- 5 个本地模型（VAD / Punc / Paraformer / CAM++ / emotion2vec）
- 进程级模型锁（`_asr_lock` 串行化，防 FunASR 并发状态腐败）
- 中断恢复机制（`recover_interrupted_tasks` / `recover_queued_recordings`）
- 语义段合并（backchannel 过滤、未说完尾巴续接）
- 热词双轨系统（多维打分、ASR 热词可说性过滤、双轨包、生命周期维护）
- 声纹多采样匹配（top-5 中位数、margin 判定、三档作用域、说话人合并）
- DeepSeek 会议纪要（分块 map-reduce、会议类型模板、反行动项 prompt）
- 情绪分析（emotion2vec 声学层 + DeepSeek 语义层双层对冲）
- 自然语言改写纪要（版本化）
- DeepSeek 请求指数退避重试
- SQLite 数据库（schema 精简后，删多用户表）

## 二、架构

### 进程模型

```
开发者：构建两套镜像（多架构）
  Dockerfile.cpu   → aham-voice-web:latest   (linux/amd64 + linux/arm64)
  Dockerfile.gpu   → aham-voice-web:gpu       (linux/amd64，带 CUDA)

用户：docker compose up -d
  - .env 配置（密码、端口、模型路径、绑定地址）
  - docker-compose.yml 选 latest 或 gpu 镜像
  - volumes: models(首次自动下载) + data(SQLite+录音)
  - restart: unless-stopped（崩了自动拉起）
  - 浏览器/手机访问 http://<host>:8765

平台对应：
  Linux x64 服务器   → latest 或 gpu
  Linux arm64 服务器 → latest
  Windows + Docker Desktop → latest（CPU only）
```

### 后端模块结构（中等粒度，~12 文件）

原 `backend/app/main.py`（4139 行单文件）拆分为：

```
backend/app/
├── main.py          # FastAPI app 工厂、startup、静态托管、路由注册（~200 行）
├── config.py        # 路径常量、env 读取、DeepSeek 配置读写
├── db.py            # db() 连接、ensure_schema、迁移、中断恢复、cleanup_loop
├── security.py      # 【新】单密码门：token、middleware、登录接口
├── state.py         # 模块级共享状态：_asr_lock / _asr_model / _speaker_verifier / _emotion_model
├── deepseek.py      # _deepseek_post_with_retry + 三个 LLM 调用封装
├── asr.py           # FunASR 加载、转写、语义段合并（含 transcribe_recording 枢纽）
├── hotwords.py      # 热词打分、双轨包、ASR 热词过滤
├── voiceprint.py    # 声纹匹配、说话人合并、CAM++ 验证
├── emotion.py       # emotion2vec + DeepSeek 情绪分析
├── summary.py       # 会议纪要、自然语言改写、模板
└── routes/
    ├── __init__.py  # 挂载所有 router
    ├── recordings.py
    ├── hotwords.py
    ├── voiceprints.py
    ├── settings.py
    └── auth.py      # 单密码登录
```

### 模块间依赖关系（关键：避免循环依赖）

`transcribe_recording` 是枢纽函数，同时调用 hotwords/voiceprint/state。拆分原则：

```
state.py        ← 无依赖（被所有人 import）
config.py       ← 无依赖
db.py           ← config
deepseek.py     ← config
hotwords.py     ← db, config
voiceprint.py   ← db, config, state
emotion.py      ← db, config, state, deepseek
summary.py      ← db, config, deepseek
asr.py          ← db, config, state, hotwords, voiceprint   ← 枢纽，单向依赖
routes/*        ← 上述业务模块
main.py         ← 所有 routes + db + security
security.py     ← config, state
```

单向依赖，无循环。`asr.py` 作为枢纽单向 import hotwords/voiceprint，反过来不成立。

### 删除项（从原项目 fork 后删除）

- `app_launcher.py` 整个文件（pywebview、随机端口、`_DesktopApi.save_file`）—— 新项目无桌面形态
- `packaging/macos/` 整个目录（build_app.sh、Info.plist、icon、make_icon.py、README-install.txt）—— Mac 桌面打包，新项目不服务 Mac
- 多用户死代码（见第七节）

## 三、安全：单密码门（security.py）

### 需求

局域网可访问（绑 0.0.0.0）后，同网络任何人都能访问 `/api/recordings`、`PATCH /api/settings`（可改 DeepSeek base_url 劫持请求）。需要一个轻量访问控制。

### 机制设计

```
1. 启动时从 .env 读 AHAMVOICE_ACCESS_PASSWORD
   - 为空 → 不启用密码门（向后兼容裸奔）
   - 非空 → 启用密码门

2. 密码门启用时：
   - 服务启动生成一个随机 session token（secrets.token_urlsafe）
     存在内存里（一个 set，重启即失效）
   - 所有 /api/* 请求必须带 Cookie: aham_token=<token>
   - 未带或 token 无效 → 401
   - POST /api/auth/login 接受 {password}，对上则 Set-Cookie

3. 例外白名单（不需要 token）：
   - /api/auth/login   （登录本身）
   - /api/health       （给 docker healthcheck / 监控探活用）
   - 静态资源          （index.html、assets，否则登录页都打不开）
```

### 关键取舍

1. **Cookie 而非 Authorization Header**：浏览器原生支持，前端 fetch 加 `credentials: 'include'` 即可，手机浏览器兼容好。
2. **token 存内存不存数据库**：重启频率低，重启重新登录可接受。存 DB 要加表（与"清理多用户表"冲突）。
3. **密码明文比对，不做哈希**：单密码门不是用户密码库，密码在 `.env` 也是明文，哈希只是表演。`hmac.compare_digest` 防时序攻击足矣。
4. **不设过期时间**：单机自用，登录一次一直有效。重置靠重启或改密码。
5. **Starlette middleware 统一拦截**，而非每个路由 `Depends`：原版每个路由都 `Depends(current_user)`，改 100 个路由签名不如一个 middleware 检查白名单 + cookie。

### 前端配合

- 新增 `pages/Login.tsx`：密码框 + 提交 → `POST /api/auth/login`
- `router.tsx` 加 `/login` 路由
- `api/client.ts`：fetch 加 `credentials: 'include'`；收到 401 → 跳 `/login`

## 四、部署：Docker

### 镜像变体

```
Dockerfile.cpu   → aham-voice-web:latest
  基镜像：python:3.12-slim（debian）
  torch CPU 版
  适用：Linux 无 GPU / Windows（Docker Desktop，CPU only）/ Linux arm64
  多架构：linux/amd64 + linux/arm64（docker buildx）

Dockerfile.gpu   → aham-voice-web:gpu
  基镜像：nvidia/cuda:12.x-runtime-ubuntu22.04
  torch + CUDA
  适用：Linux + NVIDIA GPU
  需要 nvidia-container-toolkit，docker run --gpus all
  仅 linux/amd64
```

两套镜像是物理必然：torch 的 CPU 版和 CUDA 版是不同 wheel 包，二进制不兼容。

> Windows 用户注意：只能用 `:latest`（CPU 推理）。`docker compose up` 即可，无需特殊配置。

### Volume 挂载

```yaml
# docker-compose.yml
services:
  ahamvoice:
    image: aham-voice-web:latest      # Linux 无 GPU / Windows；或 :gpu（Linux NVIDIA）
    ports: ["8765:8765"]
    volumes:
      - ./models:/models              # 4GB 模型，首次自动下载
      - ./data:/data                  # SQLite + 录音文件（用户数据）
    env_file: .env
    restart: unless-stopped           # ← 崩了自动拉起
    # gpu 镜像额外加：deploy.resources.devices / --gpus all
```

挂载点：
- `/models`：5 个模型，容器启动检测缺失则从 ModelScope 下载，进度写日志
- `/data`：SQLite 数据库、录音文件、导出文件（对应原 `BASE` 目录）

容器内路径与 env 对应关系（docker-compose.yml 的 env_file 指向 `.env`）：
- volume `./models:/models` ↔ `AHAMVOICE_MODELS_DIR=/models`
- volume `./data:/data` ↔ `AHAMVOICE_HOME=/data`

### ffmpeg 处理

Dockerfile 里 `apt-get install -y ffmpeg`，依赖由基镜像解决，无需重定位。原版那段 200 行的 dylib 重定位 + ad-hoc 签名代码**整段删除**——这是 Docker 化最大的净收益（且新项目不服务 Mac，完全不需要它）。

### 首次启动模型自动下载

容器启动时（`startup` 事件）检测 `/models` 下 5 个模型目录是否存在，缺哪个下哪个。用 modelscope 或 funasr 自带下载。下载进度写 stdout，用户 `docker logs -f` 可见。4GB 模型首次下载 10-30 分钟。

### 日常管理

```bash
docker compose up -d        # 启动
docker compose logs -f      # 看日志
docker compose restart      # 重启
docker compose down         # 停止
```

Linux/Windows 命令完全一致。

## 五、配置：.env 文件

所有可调项集中在 `.env`，开发/部署都生效：

```bash
# .env.example
AHAMVOICE_HOST=0.0.0.0
AHAMVOICE_PORT=8765
AHAMVOICE_ACCESS_PASSWORD=             # 空=裸奔；非空=启用密码门
AHAMVOICE_HOME=/data                   # 数据目录（SQLite + 录音）
AHAMVOICE_MODELS_DIR=/models           # 模型目录

# DeepSeek（纪要/情绪用，运行时也可在设置页改）
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro

# ASR 性能（保留原版所有 env 开关）
AHAMVOICE_ASR_DEVICE=cpu               # 容器内只能 cpu 或 cuda；无 mps（MPS 需原生 macOS）
AHAMVOICE_ASR_THREADS=
AHAMVOICE_BATCH_SIZE_S=300
# ... 其余 AHAMVOICE_* 开关原样保留

# 各镜像变体可用 device：
#   :latest（cpu） → cpu
#   :gpu          → cuda
```

## 六、前端改造点

原前端 `frontend-src/` 整体保留。3 处必须改：

1. **`api/client.ts` 加 `credentials: 'include'`**：fetch 默认不带 cookie，密码门需要。
2. **新增登录页 `/login` + 路由守卫**：`pages/Login.tsx`、`router.tsx` 加路由、全局 401 拦截跳转。
3. **下载逻辑去 webview 化**：原前端若有调 `window.pywebview.api.save_file()` 的地方，改成原生 `<a download>` 或 `fetch().blob()`。Web 浏览器原生支持。

其余 UI（录音列表、详情页、说话人面板、纪要编辑器、热词管理、声纹管理）全部不动。

## 七、多用户死代码清理

原 `main.py` 保留了上千行被旁路的多用户设施，全部删除：

**数据库表：**
- `users`、`sessions`、`teams`、`role_mappings`、`audit`（全部删除）

**函数：**
- `current_user`（固定返回 local-admin 即可，不再读 users 表）
- `require_admin`、`managed_team_ids`、`recording_where`、`recording_filter_where`（权限范围逻辑）
- `can_access_recording` 中的角色判断（简化为只校验存在性）
- `_guard_admin_change`、`normalize_user` 的多用户字段
- `hash_password` / `verify_password` / `session_expiry` / `create_session`（密码门有自己的简单 token）
- 旧的 `/api/auth/login`（查 users 表 + 校验密码哈希）/ `/api/auth/logout` / `/api/auth/change-password`（被新单密码门替代；路由路径 `POST /api/auth/login` 由新 `routes/auth.py` 复用，但实现完全不同：只比对单个 access password）

**保留：**
- `LOCAL_USER_ID = "local-admin"` 单用户标识
- 所有录音、纪要、热词、声纹的 owner_id 字段统一填 local-admin（schema 列可保留，不再做权限过滤）

## 八、迁移顺序（实施计划核心）

按依赖关系排序，每步跑一次 `py_compile` + 冒烟测试：

```
第 0 步：fork 仓库
  - 从原 repo fork 出 aham-voice-web
  - 删 app_launcher.py、packaging/macos/ 整个目录
  - 验证：仓库干净，git 历史清晰

第 1 步：删死代码（先减负）
  - 删 users/sessions/teams/role_mappings/audit 表及相关函数
  - main.py 从 4139 行降到 ~3000 行
  - 验证：py_compile + 启动不报错

第 2 步：抽 config.py + state.py（无业务依赖，最安全）
  - config.py: 路径常量、env 读取、DeepSeek 配置
  - state.py: _asr_lock、模型实例单例
  - main.py 全局变量改成 import
  - 验证：转写一个录音跑通

第 3 步：抽 db.py
  - db()、ensure_schema（精简版）、recover_*、cleanup_loop
  - 验证：启动建表正常 + 中断恢复测试

第 4 步：抽领域模块（asr/hotwords/voiceprint/emotion/summary/deepseek）
  - 每个模块独立抽，抽完跑一次
  - 注意 asr 是枢纽，单向依赖 hotwords/voiceprint
  - 验证：每个领域抽完跑相关 API

第 5 步：抽 routes/
  - @app.post 改成 APIRouter，main.py include_router
  - 验证：所有 API 路由冒烟测试

第 6 步：加 security.py（密码门）
  - middleware + /api/auth/login + /api/health
  - 前端加登录页 + credentials
  - 验证：未登录 401、登录后正常

第 7 步：Docker 化
  - Dockerfile.cpu + Dockerfile.gpu + docker-compose.yml + .env.example
  - 模型自动下载逻辑（startup 检测 + modelscope 下载）
  - 验证：docker build + compose up + 浏览器访问（Linux）
  - 额外验证：Windows Docker Desktop 能跑 :latest（CPU）

第 8 步：更新 README（含 Linux/Windows 双平台部署说明）
```

## 九、开发模式

开发统一在宿主机直跑（Linux/macOS 开发机通用），改后端即生效：

```bash
# 方式 A（推荐，贴近部署形态）：构建前端 + 后端直跑
cd frontend-src && npm install && npm run build    # 产出 ../frontend/dist
cd .. && python -m uvicorn backend.app.main:app --port 8765 --reload
# 浏览器开 http://localhost:8765（后端托管 dist，前后端同源，无需 CORS）

# 方式 B（改前端热更新）：Vite dev server + 后端直跑
cd frontend-src && npm install && npm run dev      # Vite 跑 5173
# 另一个终端
python -m uvicorn backend.app.main:app --port 8765 --reload
# 浏览器开 http://localhost:5173（Vite vite.config.ts 已配 /api 代理到 8765）
```

部署走 Docker（见第四节）。`.env` 在开发/部署下都生效。

> 注：开发者若在 Mac 上开发，本地直跑可以用 mps，但产物（Docker 镜像）部署到 Linux/Windows 只能 cpu/cuda。

## 十、风险与边界

1. **Windows CPU only**：Windows 用户走 Docker 只能 CPU 推理，转写比 GPU 慢。这是已确认接受的取舍（换来零配置 + 稳定）。文档明确标注。
2. **拆分循环依赖**：`transcribe_recording` 同时调 hotwords/voiceprint/state。靠 state.py 提供共享 + asr.py 单向 import 解决。实施计划会明确每步的 import 方向。
3. **模型首次下载耗时**：4GB 模型首次下载 10-30 分钟（取决于网速）。日志要有进度提示，避免用户以为卡死。Windows 用户若墙网，下载可能更慢或失败——文档提示可用代理。
4. **密码门非高安全**：单密码门只能挡随机路人，挡不住针对性攻击。HTTP 明文（无 TLS）下密码可被同网嗅探。文档提示"高安全场景请加反向代理 + TLS"。
5. **Docker Desktop 依赖**：Windows 用户必须先装 Docker Desktop（含 WSL2 后端），这本身有安装门槛和资源占用。文档需前置说明。
6. **两个仓库的同步问题**：原 repo（Mac 桌面）和新仓库（Linux/Windows Web）独立演进。若原项目修了 ASR/纪要的 bug，新仓库需手动 cherry-pick。缓解：核心业务逻辑文件（asr/hotwords/voiceprint/emotion/summary）尽量保持文件级一致，便于比对同步。
7. **数据迁移**：原版（Mac 桌面）数据在 `~/Library/Application Support/AhamVoice/`。新仓库用户从零开始，无迁移需求（Mac 用户继续用原 repo，数据不动）。
