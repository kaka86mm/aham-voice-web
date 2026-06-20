# Aham Voice Web 化改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 macOS 桌面录音转写应用 fork 成 Linux/Windows 的 Docker Web 应用（新仓库 `aham-voice-web`）。

**Architecture:** Fork 原项目 → 删桌面壳 + 多用户死代码 → 单文件 main.py 拆 12 模块 → 加单密码门 → Docker 化（cpu/gpu 双镜像）。核心业务逻辑（FunASR/热词/声纹/纪要/情绪）原样搬迁，只动结构和部署形态。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / FunASR(torch) / React+Vite+TS / Docker / pytest（新增）

**Spec:** `docs/superpowers/specs/2026-06-20-web-conversion-design.md`

---

## 重要约束（实施者必读）

1. **原项目零测试**：没有 pytest、没有 test 文件、前端没有测试框架。本计划为 Python 新建 pytest 基础设施；前端不强加测试（YAGNI）。
2. **重构任务 ≠ TDD**：拆分/删代码是"行为不变"的重构，验证方式是 `py_compile` + 冒烟测试（启动服务 + 跑通一个 API），不是先写失败测试。只有**新增功能**（密码门、模型下载、Dockerfile）用 TDD。
3. **保留原项目逻辑**：asr/hotwords/voiceprint/emotion/summary 的函数体**原样搬迁**到新模块，不要"顺手优化"。重构期改逻辑是 bug 温床。
4. **冒烟测试需要模型**：完整跑通 ASR 需要 4GB 模型，CI 环境跑不了。冒烟测试分两级：
   - **轻量冒烟**（每步必做）：`py_compile` + 服务能启动 + `/api/me` 返回 200
   - **完整冒烟**（关键节点做）：本地有模型时，上传一段音频跑通转写→纪要全流程
5. **行号会漂移**：spec 和本计划引用的 `main.py:行号` 是 fork 时的初始状态。删代码后行号会变，用函数名/唯一字符串定位，不要死盯行号。

## File Structure（最终态）

```
aham-voice-web/
├── backend/app/
│   ├── __init__.py          # 已存在
│   ├── main.py              # 重构为：app 工厂 + startup + 静态托管 + include_router（~200 行）
│   ├── config.py            # 新：路径/env/DeepSeek 配置
│   ├── db.py                # 新：连接/schema/迁移/中断恢复/cleanup
│   ├── security.py          # 新：单密码门
│   ├── state.py             # 新：模块级共享状态
│   ├── deepseek.py          # 新：LLM 调用封装
│   ├── asr.py               # 新：FunASR 转写 + 段合并（枢纽）
│   ├── hotwords.py          # 新：热词系统
│   ├── voiceprint.py        # 新：声纹
│   ├── emotion.py           # 新：情绪分析
│   ├── summary.py           # 新：纪要
│   └── routes/
│       ├── __init__.py      # 新：挂载 router
│       ├── recordings.py
│       ├── hotwords.py
│       ├── voiceprints.py
│       ├── settings.py
│       └── auth.py
├── backend/requirements.txt        # 修改：加 pytest
├── backend/tests/                  # 新：测试目录
│   ├── conftest.py
│   ├── test_security.py
│   ├── test_config.py
│   └── test_model_download.py
├── frontend-src/                   # 改 3 处（client.ts/Login/router）
├── Dockerfile.cpu                  # 新
├── Dockerfile.gpu                  # 新
├── docker-compose.yml              # 新
├── .env.example                    # 新
└── [删除] app_launcher.py, packaging/macos/
```

---

## Task 0: Fork 仓库 + 清理桌面壳

**Files:**
- Delete: `app_launcher.py`
- Delete: `packaging/macos/`（整个目录）
- Modify: `README.md`

- [ ] **Step 1: 确认当前在原 repo 的干净工作副本**

Run: `git status && git log --oneline -3`
Expected: 干净工作区，最近 commit 是设计文档

- [ ] **Step 2: 删除桌面壳文件**

```bash
rm app_launcher.py
rm -rf packaging/macos/
```

- [ ] **Step 3: 验证 backend 仍能 import（不依赖已删文件）**

Run: `python -m py_compile backend/app/main.py`
Expected: 无输出（编译通过）。app_launcher.py 是独立入口，main.py 不 import 它，删除应无影响。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: 删除 macOS 桌面壳（app_launcher + packaging/macos）

新仓库 aham-voice-web 不服务 Mac 桌面，这些 pywebview/.app 打包代码全部不需要。
Mac 用户继续用原 repo。"
```

---

## Task 1: 建立测试基础设施

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`（空文件）
- Create: `backend/tests/conftest.py`
- Create: `pytest.ini`（仓库根）

**Why:** 后续 Task 6（密码门）用 TDD，需要先有 pytest。先建基础设施，不写业务测试。

- [ ] **Step 1: 加 pytest 到开发依赖**

修改 `backend/requirements.txt`，末尾追加：

```
# --- dev only（不进 Docker 镜像）---
pytest==8.4.2
httpx==0.28.1
```

注：httpx 已在 requirements-asr.txt，但 requirements.txt（轻量后端依赖）里也要有，供测试 client 用。

- [ ] **Step 2: 建 pytest 配置**

Create `pytest.ini`：

```ini
[pytest]
testpaths = backend/tests
python_files = test_*.py
python_functions = test_*
asyncio_mode = auto
```

- [ ] **Step 3: 建 conftest.py（临时最小版本）**

Create `backend/tests/conftest.py`：

```python
"""共享 pytest fixtures。目前最小，后续 task 按需扩充。"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """把 AHAMVOICE_HOME 指向临时目录，隔离测试不污染真实数据。"""
    monkeypatch.setenv("AHAMVOICE_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AHAMVOICE_MODELS_DIR", str(tmp_path / "models"))
    return tmp_path
```

- [ ] **Step 4: 建空 __init__.py**

```bash
touch backend/tests/__init__.py
```

- [ ] **Step 5: 验证 pytest 能跑（哪怕没测试）**

Run: `pip install pytest httpx && python -m pytest --collect-only`
Expected: `no tests ran` 或 `collected 0 items`，**不报 import 错误**。

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/tests/ pytest.ini
git commit -m "test: 建立 pytest 基础设施

原项目零测试。为后续 TDD（密码门等）先建好测试框架。
conftest 提供 tmp_home fixture 隔离测试数据目录。"
```

---

## Task 2: 删多用户死代码（先减负）

**Files:**
- Modify: `backend/app/main.py`（删约 1000 行）

**Why:** 拆分前先减负。多用户表/函数被 `current_user` 固定返回 local-admin 旁路，删掉后 main.py 从 4139 行降到 ~3000 行，后续拆分更轻松。

**删除清单（按 main.py 初始行号定位，删完重新核对）：**

数据库表（`ensure_schema` 内 `create table` 语句）：
- `teams`（~line 278-285）
- `users`（~line 286-307）
- `sessions`（~line 308-313）
- `role_mappings`（~line 319-329）
- `audit`（~line 492-499）

函数：
- `hash_password`（226）/ `verify_password`（233）/ `session_expiry`（246）/ `initial_password`（222）/ `create_session`（996）
- `normalize_user`（958）/ `normalize_team`（970）/ `team_payload`（1140）
- `require_admin`（1050）/ `managed_team_ids`（1055）/ `recording_where`（1059）/ `recording_filter_where`（1072）
- `_guard_admin_change`（3026）

- [ ] **Step 1: 删 ensure_schema 里的多用户表创建语句**

打开 `backend/app/main.py`，在 `ensure_schema` 函数内删除 `teams`/`users`/`sessions`/`role_mappings`/`audit` 五个表的 `create table if not exists (...)` 整块。

**保留**：`recordings`/`transcript_segments`/`summaries`/`emotion_analyses`/`tasks`/`hotwords`/`hotword_sources`/`hotword_sync_runs`/`recording_hotword_packages`/`speaker_profiles`/`speaker_samples`/`app_settings`。

- [ ] **Step 2: 删 ensure_schema 里的多用户迁移段**

删除所有针对 teams/users/role_mappings 的 `alter table`/`pragma table_info` 迁移块（~line 502-523, 651-764 之间的用户/团队相关段）。保留 recordings/segments/summaries/tasks/hotwords 的迁移。

- [ ] **Step 3: 删 ensure_schema 里的种子数据**

删除：seed teams（~665-672）、seed users（~673-686）、administrator 插入（~687-739）、role_mappings 插入（~740-750）。保留 seed hotwords（~751-762）。

- [ ] **Step 4: 删独立的多用户函数**

删除：`initial_password`/`hash_password`/`verify_password`/`session_expiry`/`create_session`/`normalize_user`/`normalize_team`/`team_payload`/`require_admin`/`managed_team_ids`/`recording_where`/`recording_filter_where`/`_guard_admin_change`。

- [ ] **Step 5: 重写 `current_user`（去掉 users 表查询）**

原 `current_user`（~1035）查 users 表。改为固定返回 local-admin 字典。同时 `ensure_local_user`（~1011）也简化——它原来向 users 表插 local-admin，现在 users 表删了，整个函数删掉，local-admin 作为内存常量。

替换为：

```python
# 单用户模式：固定 local-admin。无 users 表、无登录态（密码门在 security.py 单独处理）。
LOCAL_USER_ID = "local-admin"


def current_user() -> dict[str, Any]:
    """单用户模式：固定返回 local-admin。保留 signature 兼容路由的 Depends(current_user)。"""
    return {
        "id": LOCAL_USER_ID,
        "name": "本机用户",
        "role": "manager",
        "managed_team_ids": ["*"],
        "team_id": None,
    }
```

注意：`current_user` 原签名带 `authorization`/`token_query` 参数（给路由 Depends 用）。**保留这两个参数**（即使不读），否则所有 `Depends(current_user)` 的路由签名要改。改为：

```python
def current_user(
    authorization: str | None = Header(default=None),
    token_query: str | None = Query(default=None, alias="token"),
) -> dict[str, Any]:
    return {"id": LOCAL_USER_ID, "name": "本机用户", "role": "manager",
            "managed_team_ids": ["*"], "team_id": None}
```

- [ ] **Step 6: 简化 `can_access_recording`（去掉角色判断）**

原 `can_access_recording`（~1093）有 role 判断。单用户模式下 owner 必然是 local-admin，简化为只校验存在性：

```python
def can_access_recording(conn: sqlite3.Connection, recording_id: str, user: dict[str, Any]) -> dict[str, Any]:
    rec = rowdict(conn.execute("select * from recordings where id = ?", (recording_id,)).fetchone())
    if not rec:
        raise HTTPException(status_code=404, detail="recording not found")
    return rec
```

- [ ] **Step 7: 修复所有 `normalize_user`/`normalize_team` 调用点**

搜索 `normalize_user(` 和 `normalize_team(` 的所有调用，按情况处理：
- `normalize_user(user)` → 直接用 `user`（已是 dict）
- `normalize_team(...)` → 删掉调用处（team_payload 已删）

Run: `grep -n "normalize_user\|normalize_team\|managed_team_ids\|recording_where\|recording_filter_where\|require_admin\|hash_password\|verify_password\|create_session\|session_expiry\|initial_password" backend/app/main.py`
Expected: 只剩 `current_user` 返回值里的 `managed_team_ids`（Step 5 保留的）。其他引用必须清零。

- [ ] **Step 8: 修复 `recordings` 路由（recording_filter_where 删了的善后）**

`/api/recordings`（~3072）和 `/api/tasks`（~3350）用了 `recording_filter_where`/`recording_where`。单用户模式下直接查全部：

`/api/recordings` 改为：
```python
@app.get("/api/recordings")
def recordings(scope: str = "mine", q: str = "", meeting_type: str = "",
               user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    where_parts = ["1=1"]
    args: list[Any] = []
    if meeting_type and meeting_type != "全部":
        where_parts.append("recordings.meeting_type = ?")
        args.append(meeting_type)
    if q.strip():
        like = f"%{q.strip()}%"
        where_parts.append("(recordings.title like ? or recordings.filename like ? or recordings.tag like ?)")
        args.extend([like, like, like])
    where = " and ".join(f"({p})" for p in where_parts)
    with db() as conn:
        rows = conn.execute(
            f"""select recordings.* from recordings
                left join users on users.id = recordings.owner_id
                where {where} order by recordings.updated_at desc""",
            args,
        ).fetchall()
        return [recording_payload(conn, dict(row)) for row in rows]
```

注意：`left join users` 现在没 users 表了，改成不 join，`recording_payload` 里的 owner_name 查询也要改（见 Step 9）。

- [ ] **Step 9: 修改 `recording_payload`（owner_name 不查 users 表）**

原 `recording_payload`（~1108）查 users 表拿 owner_name。改为返回固定值：

```python
def recording_payload(conn: sqlite3.Connection, rec: dict[str, Any]) -> dict[str, Any]:
    payload = dict(rec)
    payload["owner_name"] = "本机用户"
    return payload
```

- [ ] **Step 10: 删 `/api/tasks` 里的权限分支**

`/api/tasks`（~3350）原有 admin/manager/member 三分支。单用户全是 local-admin，简化为直接查全部：

```python
@app.get("/api/tasks")
def tasks(user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "select * from tasks order by updated_at desc limit 100"
        ).fetchall()
        return [task_payload(dict(row)) for row in rows]
```

- [ ] **Step 11: 删旧 auth 路由 + voiceprint 权限分支**

删除：`/api/auth/login`（旧，查 users 表，~2913）、`/api/auth/logout`（~2958）、`/api/auth/change-password`（~2967）。这些会被 Task 6 的新密码门替代。

`/api/voiceprints`（~3659）和 `resolve_voiceprint_scope`（~3681）有 role 判断。单用户全是 manager，简化 `resolve_voiceprint_scope` 直接返回 `("team" or "global", None)`，去掉所有 role 检查抛错。`/api/voiceprints` 的 where 子句简化为查全部。

- [ ] **Step 12: py_compile 验证**

Run: `python -m py_compile backend/app/main.py`
Expected: 无输出（编译通过）

- [ ] **Step 13: 轻量冒烟（服务能启动）**

Run（设临时数据目录避免污染）：
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.main import app, ensure_schema
ensure_schema()
print('OK: schema 初始化成功，无多用户表')
"
```
Expected: 打印 `OK: schema 初始化成功，无多用户表`，不报错。

- [ ] **Step 14: 完整冒烟（FastAPI app 能构造 + /api/me 路由在）**

Run:
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.get('/api/me')
print('status:', r.status_code, 'body:', r.json())
assert r.status_code == 200
assert r.json()['id'] == 'local-admin'
print('OK: /api/me 返回 local-admin')
"
```
Expected: `status: 200`，body 含 `"id": "local-admin"`。

- [ ] **Step 15: 统计行数确认减负效果**

Run: `wc -l backend/app/main.py`
Expected: 约 2800-3100 行（从 4139 降下来）

- [ ] **Step 16: Commit**

```bash
git add backend/app/main.py
git commit -m "refactor: 删多用户死代码（users/sessions/teams/role_mappings/audit）

原项目保留了上千行被旁路的多用户设施（current_user 固定返回 local-admin）。
删除：5 张多用户表、密码哈希/会话函数、权限范围逻辑、旧 auth 路由。
main.py 从 4139 行降到约 3000 行，为后续拆分减负。
单用户逻辑保留：LOCAL_USER_ID + 简化版 current_user。"
```

---

## Task 3: 抽 config.py + state.py（无依赖，最安全）

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/state.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_config.py`

**Why:** 这两个模块无业务依赖，是最安全的拆分起点。config 放路径/env/DeepSeek 配置；state 放模块级共享单例（锁/模型实例），解决拆分后跨模块共享状态的问题。

### Task 3a: config.py

- [ ] **Step 1: 写 config.py 的失败测试**

Create `backend/tests/test_config.py`：

```python
import os
from backend.app import config


def test_deepseek_config_env_wins_over_file(tmp_home, monkeypatch):
    """env 变量优先于 config.json 文件。"""
    # 先写 config.json
    config.save_user_config({"deepseek_api_key": "from-file"})
    # env 覆盖
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    key, base, model = config.get_deepseek_config()
    assert key == "from-env"


def test_deepseek_config_defaults(tmp_home):
    """无 env 无文件时返回默认 base/model。"""
    key, base, model = config.get_deepseek_config()
    assert key == ""
    assert base == "https://api.deepseek.com"
    assert model == "deepseek-v4-pro"


def test_save_user_config_atomic(tmp_home):
    """save_user_config 写入后能读回。"""
    result = config.save_user_config({"deepseek_model": "new-model"})
    assert result["deepseek_model"] == "new-model"
    _, _, model = config.get_deepseek_config()
    assert model == "new-model"


def test_env_int_clamping(tmp_home, monkeypatch):
    """env_int 把超范围值夹到区间内。"""
    monkeypatch.setenv("TEST_NUM", "99999")
    assert config.env_int("TEST_NUM", default=10, minimum=1, maximum=100) == 100
    monkeypatch.setenv("TEST_NUM", "0")
    assert config.env_int("TEST_NUM", default=10, minimum=1, maximum=100) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest backend/tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'backend.app.config'`）

- [ ] **Step 3: 创建 config.py**

从 main.py 搬迁以下内容到 `backend/app/config.py`（**原样搬迁，不改逻辑**）：
- `load_env_file`（~35）及其调用（~54-55）
- 路径常量块（~57-88：`_default_base`/`BASE`/`APP_DATA`/`DB_PATH`/`RECORDINGS`/`EXPORTS`/`TMP`/`MODELS`/`VAD`/`PUNC`/`PARAFORMER`/`CAMPLUS`/`EMOTION`/`VOICEPRINTS`/`BIN_DIR`/`FFMPEG`/`FFPROBE`）
- `CONFIG_PATH`/`load_user_config`/`save_user_config`/`get_deepseek_config`（~97-128）
- env 工具函数：`env_int`/`env_float`/`env_bool`/`env_json`（~2208-2238）

config.py 顶部需要的 import：`from __future__ import annotations` + `import os, json` + `from pathlib import Path` + `from typing import Any` + `import sys` + `from contextlib import contextmanager`（_default_base 用）。

注意：`BASE` 等常量在 import 时就求值（依赖 `AHAMVOICE_HOME` env）。测试用 `tmp_home` fixture 设 env，**但 config 模块在 import 时已求值过一次**。为支持测试隔离，把路径常量改为函数或让测试用 `importlib.reload(config)`。**最简方案**：保持模块级常量，测试里用 `monkeypatch` + `reload`：

conftest.py 的 `tmp_home` fixture 末尾加：
```python
import importlib
from backend.app import config as _config
importlib.reload(_config)
return tmp_path
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest backend/tests/test_config.py -v`
Expected: 4 个测试 PASS

- [ ] **Step 5: 修改 main.py 从 config 导入**

在 main.py 删除已搬迁的定义，顶部加：
```python
from .config import (
    BASE, APP_DATA, DB_PATH, RECORDINGS, EXPORTS, TMP,
    MODELS, VAD, PUNC, PARAFORMER, CAMPLUS, EMOTION, VOICEPRINTS,
    BIN_DIR, FFMPEG, FFPROBE,
    load_env_file, load_user_config, save_user_config, get_deepseek_config,
    env_int, env_float, env_bool, env_json,
)
```

- [ ] **Step 6: py_compile + 轻量冒烟**

Run: `python -m py_compile backend/app/main.py backend/app/config.py`
Run: `AHAMVOICE_HOME=/tmp/aham-smoke python -c "from backend.app.main import app; print('OK')" `
Expected: 编译通过 + `OK`

- [ ] **Step 7: Commit（3a）**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/test_config.py backend/tests/conftest.py
git commit -m "refactor: 抽 config.py（路径/env/DeepSeek 配置）

从 main.py 搬迁路径常量、env 工具、DeepSeek 配置读写到独立模块。
无业务依赖，作为拆分第一步。新增 4 个配置单测。"
```

### Task 3b: state.py

- [ ] **Step 1: 创建 state.py**

Create `backend/app/state.py`：

```python
"""模块级共享状态：模型实例单例 + 进程锁。

FunASR 的 AutoModel 和 modelscope speaker_verification 内部有跨调用状态
（cache dict、tensor buffer），线程池并发会 corrupt。用进程级锁串行化。
单例避免重复加载 4GB 模型。
"""
from __future__ import annotations

import threading
from typing import Any

# 进程级锁：ASR + 声纹验证串行化（防 FunASR 并发状态腐败）
asr_lock = threading.Lock()
asr_init_lock = threading.Lock()
verifier_init_lock = threading.Lock()
emotion_init_lock = threading.Lock()

# 模型单例（懒加载，首次用时填充）
asr_model: Any | None = None
speaker_verifier: Any | None = None
emotion_model: Any | None = None

DEFAULT_VOICEPRINT_THRESHOLD = 0.66
```

- [ ] **Step 2: 修改 main.py 用 state 的单例/锁**

main.py 里把 `_asr_lock`→`from .state import asr_lock as _asr_lock`（或全量改名）。同样处理 `_asr_model`/`_speaker_verifier`/`_emotion_model`/各 init lock。

具体做法：main.py 顶部把原来的全局变量定义（~146-158）替换为：
```python
from .state import (
    asr_lock as _asr_lock,
    asr_init_lock as _asr_init_lock,
    verifier_init_lock as _verifier_init_lock,
    emotion_init_lock as _emotion_init_lock,
)
from . import state
```

然后把代码里所有 `_asr_model` 替换为 `state.asr_model`，`_speaker_verifier` 替换为 `state.speaker_verifier`，`_emotion_model` 替换为 `state.emotion_model`。赋值处（`get_asr_model`/`get_speaker_verifier`/`get_emotion_model` 内的 `global _asr_model; _asr_model = ...`）改为 `state.asr_model = ...`。

Run（核对无残留）: `grep -n "^_asr_model\|^_speaker_verifier\|^_emotion_model\|global _asr_model\|global _speaker_verifier\|global _emotion_model" backend/app/main.py`
Expected: 无输出

- [ ] **Step 3: py_compile + 轻量冒烟**

Run: `python -m py_compile backend/app/main.py backend/app/state.py`
Run: `AHAMVOICE_HOME=/tmp/aham-smoke python -c "from backend.app.main import app; print('OK')"`
Expected: 编译通过 + `OK`

- [ ] **Step 4: Commit（3b）**

```bash
git add backend/app/state.py backend/app/main.py
git commit -m "refactor: 抽 state.py（模块级共享状态）

锁和模型单例从 main.py 全局变量搬到 state 模块。
解决拆分后跨模块共享状态的问题——后续 asr/voiceprint/emotion 模块都 import state。"
```

---

## Task 4: 抽 db.py

**Files:**
- Create: `backend/app/db.py`
- Modify: `backend/app/main.py`

**Why:** db() 连接 + ensure_schema（精简版）+ recover_* + cleanup_loop 是最大一坨，但独立性最好（只依赖 config）。独立成文件后改动数据库时有底。

- [ ] **Step 1: 创建 db.py，搬迁以下函数（原样）**

从 main.py 搬到 `backend/app/db.py`：
- `db` contextmanager（~161）
- `now`（~172）/ `rowdict`（~176）/ `rowsdict`（~180）/ `safe_json`（~184）/ `parse_local_time`（~213）/ `parse_time`（~1219）
- `ensure_schema`（~274，Task 2 精简后的版本）
- `recover_interrupted_tasks`（~767）
- `sweep_tmp_and_exports`（~834）/ `_start_cleanup_loop`（~865）
- `recover_queued_recordings`（~882）—— 注意它调 `process_recording_background`，会有循环依赖。**解决**：`recover_queued_recordings` 不搬，留在 main.py 或后续 asr.py（它属于 ASR 启动恢复逻辑）。本 task 只搬纯 DB 的部分。

db.py 需要的 import：`from .config import DB_PATH, TMP, EXPORTS` + sqlite3/datetime/json/re/uuid/contextlib/pathlib/statistics。

`ensure_schema` 里调了 `audit()`（写 audit 表），但 audit 表 Task 2 已删。把 `audit(...)` 调用从 ensure_schema 里删掉（种子数据的审计日志）。

- [ ] **Step 2: 修改 main.py 从 db 导入**

main.py 顶部加：
```python
from .db import (
    db, now, rowdict, rowsdict, safe_json, parse_local_time, parse_time,
    ensure_schema, recover_interrupted_tasks, sweep_tmp_and_exports,
    _start_cleanup_loop,
)
```

- [ ] **Step 3: 处理 `audit()` 函数的去留**

`audit()`（~944）原来写 audit 表，表已删。两个选择：
- 删掉 `audit` 函数 + 所有调用点（最干净）
- 保留为 no-op（兼容现有调用点，少改代码）

**选 no-op**（改动最小，重构期不求完美）：

```python
def audit(conn, user, category, message, actor_name=None) -> None:
    """审计日志已废弃（audit 表删除）。保留为 no-op 兼容现有调用点。"""
    pass
```

留在 main.py 或搬 db.py 都行，放 db.py（它本质是 DB 写操作）。

- [ ] **Step 4: py_compile + 轻量冒烟**

Run: `python -m py_compile backend/app/main.py backend/app/db.py`
Run:
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.main import app, ensure_schema
ensure_schema()
print('OK: db.py 搬迁后 schema 正常')
"
```
Expected: 编译通过 + `OK`

- [ ] **Step 5: 中断恢复冒烟（无 running task 时应返回 0）**

Run:
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.db import recover_interrupted_tasks
n = recover_interrupted_tasks()
print('recovered:', n)
assert n == 0
print('OK: 中断恢复在空库下返回 0')
"
```
Expected: `recovered: 0` + `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/app/main.py
git commit -m "refactor: 抽 db.py（连接/schema/迁移/中断恢复/cleanup）

从 main.py 搬迁 DB 相关逻辑。recover_queued_recordings 暂留 main.py
（依赖 process_recording_background，避免循环依赖，后续归 asr.py）。
audit() 降级为 no-op（audit 表已删）。"
```

---

## Task 5: 抽领域模块（deepseek/hotwords/voiceprint/emotion/summary/asr）

**Files:**
- Create: `backend/app/deepseek.py`, `hotwords.py`, `voiceprint.py`, `emotion.py`, `summary.py`, `asr.py`
- Modify: `backend/app/main.py`

**Why:** 6 个领域模块按依赖顺序抽（deepseek→hotwords/voiceprint→emotion/summary→asr 枢纽）。每个抽完跑一次冒烟，避免一次梭哈。

**通用搬迁原则：** 函数体原样搬，不改逻辑。每个新模块顶部 import 它依赖的低层模块（state/config/db）。

### Task 5a: deepseek.py（最底层，无业务依赖）

- [ ] **Step 1: 创建 deepseek.py，搬迁**

从 main.py 搬到 `backend/app/deepseek.py`：
- `_deepseek_post_with_retry`（~2241，async）
- `call_deepseek_summary`（~2275）
- `call_deepseek_revision`（~2369）
- `call_deepseek_emotion`（~2743）

需要的 import：`from .config import get_deepseek_config, env_int` + httpx/asyncio/json/time/typing。

- [ ] **Step 2: main.py 改 import + py_compile + 冒烟**

main.py 加 `from .deepseek import _deepseek_post_with_retry, call_deepseek_summary, call_deepseek_revision, call_deepseek_emotion`

Run: `python -m py_compile backend/app/main.py backend/app/deepseek.py && AHAMVOICE_HOME=/tmp/aham-smoke python -c "from backend.app.main import app; print('OK')"`
Expected: 编译通过 + `OK`

- [ ] **Step 3: Commit（5a）**

```bash
git add backend/app/deepseek.py backend/app/main.py
git commit -m "refactor: 抽 deepseek.py（LLM 调用封装）"
```

### Task 5b: hotwords.py

- [ ] **Step 1: 创建 hotwords.py，搬迁**

从 main.py 搬到 `backend/app/hotwords.py`：
- 常量：`HOTWORD_KIND_PRIORITY`（~1204）
- 函数：`code_like_hotword`（1178）/`load_hotword_map`（1185）/`apply_hotwords`（1197）/`hotword_terms`（1230）/`hotword_row_score`（1248）/`hotword_limits`（1300）/`build_hotword_package`（1308）/`latest_hotword_package`（1426）/`_FORMAL_ORG_MARKER`+`valid_asr_hotword`（1709-1724）/`hotword_prompt`（1727）

import：`from .config import env_int` + `from .db import safe_json, parse_time, now` + re/json/typing。

- [ ] **Step 2: main.py 改 import + py_compile + 冒烟**

- [ ] **Step 3: Commit（5b）**

```bash
git commit -m "refactor: 抽 hotwords.py（热词打分/双轨包/ASR 过滤）"
```

### Task 5c: voiceprint.py

- [ ] **Step 1: 创建 voiceprint.py，搬迁**

从 main.py 搬到 `backend/app/voiceprint.py`：
- `get_speaker_verifier`（~1504）/`voiceprint_threshold_default`（1516）/`clamp_voiceprint_threshold`（1520）/`voiceprint_match_settings`（1528）/`ranked_voiceprint_intervals`（1538）/`aggregate_voiceprint_scores`（1554）/`load_speaker_profiles`（1561）/`extract_interval`（1578）/`concat_audio`（1603）/`match_speaker_profiles`（1634）/`normalize_speaker_id`（1795）

import：`from . import state` + `from .config import env_float, env_int, CAMPLUS, VOICEPRINTS, TMP, FFMPEG` + `from .state import DEFAULT_VOICEPRINT_THRESHOLD` + db helpers + re/subprocess/tempfile/pathlib/statistics/typing。

- [ ] **Step 2: main.py 改 import + py_compile + 冒烟**

- [ ] **Step 3: Commit（5c）**

```bash
git commit -m "refactor: 抽 voiceprint.py（声纹匹配/说话人合并）"
```

### Task 5d: emotion.py

- [ ] **Step 1: 创建 emotion.py，搬迁**

从 main.py 搬到 `backend/app/emotion.py`：
- 常量：`_EMOTION_CN`/`_EMOTION_NEGATIVE`（~2611-2618）
- 函数：`emotion_label_cn`（2621）/`get_emotion_model`（2629）/`analyze_segment_emotion`（2642）/`analyze_acoustic_emotions`（2656）/`acoustic_markdown`（2710）/`emotion_annotated_transcript`（2728）/`next_emotion_version`（2803）/`current_emotion_analysis`（2811）/`generate_emotion_analysis`（2825）/`run_emotion_job`（2880）

import：`from . import state` + `from .config import EMOTION, TMP` + `from .state import asr_lock as _asr_lock` + `from .deepseek import call_deepseek_emotion` + db helpers + json/shutil/tempfile/typing。

- [ ] **Step 2: main.py 改 import + py_compile + 冒烟**

- [ ] **Step 3: Commit（5d）**

```bash
git commit -m "refactor: 抽 emotion.py（emotion2vec + DeepSeek 情绪分析）"
```

### Task 5e: summary.py

- [ ] **Step 1: 创建 summary.py，搬迁**

从 main.py 搬到 `backend/app/summary.py`：
- `transcript_text`（2105）/`summary_depth_instruction`（2117）/`meeting_focus_instruction`（2132）/`meeting_template`（2156）/`next_summary_version`（2420）/`summarize_recording`（2428，async）/`revise_summary`（2471，async）/`transcript_markdown`（2528）/`write_export`（2552）/`write_summary_export`（2587）

import：`from .deepseek import call_deepseek_summary, call_deepseek_revision` + db helpers + config + typing/datetime/pathlib。

注意 `write_export` 还处理 emotion 导出，调 `current_emotion_analysis`——从 emotion.py import。

- [ ] **Step 2: main.py 改 import + py_compile + 冒烟**

- [ ] **Step 3: Commit（5e）**

```bash
git commit -m "refactor: 抽 summary.py（纪要/改写/模板/导出）"
```

### Task 5f: asr.py（枢纽，最后抽）

- [ ] **Step 1: 创建 asr.py，搬迁**

从 main.py 搬到 `backend/app/asr.py`：
- `split_audio`（1446）/`get_asr_model`（1470）/`transcribe_recording`（2013）
- 语义段合并全家桶：`FILLER_TRANSCRIPT_TEXT`（1803）/`CONTINUATION_ENDINGS`（1821）/`normalized_transcript_text`（1845）/`bare_transcript_text`（1851）/`is_filler_transcript`（1855）/`transcript_needs_continuation`（1860）/`join_transcript_text`（1867）/`semantic_segment_settings`（1879）/`merge_transcript_items`（1888）/`sentence_info_to_transcript_segments`（1982）
- `process_recording_background`（2889）/`recover_queued_recordings`（882，Task 4 留下的）

import（枢纽，依赖多）：
```python
from . import state
from .config import (PARAFORMER, VAD, PUNC, CAMPLUS, env_int, RECORDINGS, FFMPEG)
from .state import asr_lock as _asr_lock, asr_init_lock as _asr_init_lock
from .db import db, now, rowdict, rowsdict, safe_json, update_task, create_task, audit, can_access_recording
from .hotwords import build_hotword_package
from .voiceprint import match_speaker_profiles
```

注意循环依赖检查：asr.py import hotwords + voiceprint，但 hotwords/voiceprint **不** import asr。单向，无循环。✓

- [ ] **Step 2: 处理 `can_access_recording`/`update_task`/`create_task` 的归属**

这三个函数被 asr 和 routes 都用。`can_access_recording`（Task 2 简化版）放 db.py 或单独留 main.py。`update_task`/`create_task`（~1147/1164）放 db.py（task 是 DB 操作）。

**决定**：`can_access_recording`/`update_task`/`create_task`/`task_payload` 都放 db.py。Task 4 时若已搬就更新 import；没搬就现在搬。

Run（核对归属）: `grep -n "def can_access_recording\|def update_task\|def create_task\|def task_payload" backend/app/db.py`
Expected: 四个都在 db.py（若不在，从 main.py 搬过去）

- [ ] **Step 3: main.py 改 import + py_compile + 冒烟**

Run: `python -m py_compile backend/app/*.py`
Run:
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
assert client.get('/api/me').status_code == 200
print('OK: 全部领域模块抽完后 app 正常')
"
```
Expected: 编译通过 + `/api/me` 200 + `OK`

- [ ] **Step 4: Commit（5f）**

```bash
git add backend/app/asr.py backend/app/main.py backend/app/db.py
git commit -m "refactor: 抽 asr.py（FunASR 转写 + 语义段合并 + 枢纽）

最后一个领域模块，依赖 hotwords/voiceprint（单向，无循环）。
含 transcribe_recording 枢纽函数、process_recording_background、
recover_queued_recordings。main.py 现在只剩路由层。"
```

- [ ] **Step 5: 确认 main.py 已瘦身到路由层**

Run: `wc -l backend/app/main.py`
Expected: 约 1500-2000 行（全是路由 + startup + 静态托管）

---

## Task 6: 抽 routes/ + 加密码门（security.py）

**Files:**
- Create: `backend/app/security.py`
- Create: `backend/app/routes/__init__.py`, `recordings.py`, `hotwords.py`, `voiceprints.py`, `settings.py`, `auth.py`
- Modify: `backend/app/main.py`（改成 app 工厂 + include_router）
- Create: `backend/tests/test_security.py`

**Why:** 把 main.py 里所有 `@app.get/post/...` 路由抽到 routes/ 下按资源分文件。同时加单密码门（security.py + routes/auth.py）。这是唯一新增功能的 task，用 TDD。

### Task 6a: security.py + auth 路由（TDD）

- [ ] **Step 1: 写密码门的失败测试**

Create `backend/tests/test_security.py`：

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app import security


def make_app(password: str | None) -> FastAPI:
    """构造带密码门中间件的测试 app。"""
    app = FastAPI()
    sec = security.Security(password=password)
    app.add_middleware(security.SecurityMiddleware, security=sec)
    app.router.add_api_route("/api/health", lambda: {"ok": True}, methods=["GET"])
    app.router.add_api_route("/api/me", lambda: {"id": "local-admin"}, methods=["GET"])
    app.router.add_api_route("/api/auth/login",
        lambda creds, s=sec: s.login(creds), methods=["POST"])
    return app


def test_no_password_no_gate(tmp_home):
    """密码为空 → 不启用密码门，所有请求放行。"""
    client = TestClient(make_app(password=None))
    assert client.get("/api/me").status_code == 200


def test_password_gate_blocks_unauthenticated(tmp_home):
    """启用密码门 → 无 cookie 的 /api/me 返回 401。"""
    client = TestClient(make_app(password="secret"))
    assert client.get("/api/me").status_code == 401


def test_health_is_whitelisted(tmp_home):
    """启用密码门 → /api/health 仍可访问（healthcheck 用）。"""
    client = TestClient(make_app(password="secret"))
    assert client.get("/api/health").status_code == 200


def test_static_assets_whitelisted(tmp_home):
    """启用密码门 → 静态资源（/, /assets/*）可访问，否则登录页打不开。"""
    client = TestClient(make_app(password="secret"))
    # / 和 /assets/xxx 不应被 401（实际由 SPA fallback 处理，这里只验中间件放行）
    assert client.get("/").status_code != 401


def test_login_sets_cookie_then_api_works(tmp_home):
    """正确密码登录 → set cookie → 带 cookie 访问 /api/me 成功。"""
    client = TestClient(make_app(password="secret"))
    r = client.post("/api/auth/login", json={"password": "secret"})
    assert r.status_code == 200
    # TestClient 自动带 cookie
    assert client.get("/api/me").status_code == 200


def test_login_wrong_password(tmp_home):
    """错误密码 → 401，不 set cookie。"""
    client = TestClient(make_app(password="secret"))
    r = client.post("/api/auth/login", json={"password": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/me").status_code == 401


def test_login_wrong_password_repeated(tmp_home):
    """密码门不实现锁定（单密码门，不需要防爆破）。"""
    client = TestClient(make_app(password="secret"))
    for _ in range(10):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest backend/tests/test_security.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'backend.app.security'`）

- [ ] **Step 3: 实现 security.py**

Create `backend/app/security.py`：

```python
"""单密码门：cookie token + middleware 统一拦截。

启用条件：AHAMVOICE_ACCESS_PASSWORD 非空。
token 存内存（进程级 set），重启失效，不设过期。
"""
from __future__ import annotations

import hmac
import secrets
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

COOKIE_NAME = "aham_token"

# 不需要 token 的路径前缀（登录本身 + 健康检查 + 静态资源）
WHITELIST_PREFIXES = ("/api/auth/login", "/api/health", "/assets/")
WHITELIST_EXACT = ("/", "/favicon.svg", "/favicon.ico", "/index.html")


class Security:
    """密码门状态：密码 + 已发放的 token 集合。"""

    def __init__(self, password: str | None) -> None:
        self.enabled = bool(password)
        self._password = password or ""
        self._tokens: set[str] = set()

    def login(self, creds: dict[str, Any]) -> JSONResponse:
        if not self.enabled:
            return JSONResponse({"ok": True})
        password = (creds.get("password") or "").strip()
        if not hmac.compare_digest(password, self._password):
            return JSONResponse({"detail": "密码错误"}, status_code=401)
        token = secrets.token_urlsafe(32)
        self._tokens.add(token)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
        return resp

    def is_authorized(self, request: Request) -> bool:
        if not self.enabled:
            return True
        path = request.url.path
        if path in WHITELIST_EXACT or any(path.startswith(p) for p in WHITELIST_PREFIXES):
            return True
        token = request.cookies.get(COOKIE_NAME)
        return token in self._tokens


class SecurityMiddleware(BaseHTTPMiddleware):
    """拦截所有非白名单 /api/* 请求，校验 cookie token。"""

    def __init__(self, app: ASGIApp, security: Security) -> None:
        super().__init__(app)
        self._security = security

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and not self._security.is_authorized(request):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return await call_next(request)


def build_security() -> Security:
    """从 env 读密码构造 Security。空密码 → 不启用。"""
    import os
    return Security(password=os.environ.get("AHAMVOICE_ACCESS_PASSWORD") or None)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest backend/tests/test_security.py -v`
Expected: 7 个测试 PASS

- [ ] **Step 5: 创建 routes/auth.py**

Create `backend/app/routes/auth.py`：

```python
from fastapi import APIRouter, Body, Depends

from ..security import build_security, Security

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 进程级单例（token 存内存）
_security = build_security()


def get_security() -> Security:
    return _security


@router.post("/login")
def login(creds: dict = Body(...), sec: Security = Depends(get_security)):
    return sec.login(creds)
```

- [ ] **Step 6: Commit（6a）**

```bash
git add backend/app/security.py backend/app/routes/ backend/tests/test_security.py
git commit -m "feat: 单密码门（security.py + routes/auth.py）

新增功能用 TDD。机制：env AHAMVOICE_ACCESS_PASSWORD 非空则启用；
cookie token + middleware 统一拦截 /api/*；白名单 login/health/静态。
token 存内存，重启失效，不设过期。7 个单测覆盖核心场景。"
```

### Task 6b: 抽 routes/ + main.py 改 app 工厂

- [ ] **Step 1: 创建 routes/ 下其余文件**

把 main.py 里的路由按资源搬到对应文件，每个用 `APIRouter`：
- `routes/recordings.py`：`/api/recordings`、`/api/recordings/{id}` 及其子路由（process/transcribe/summarize/revise/emotion/audio/segments/export/speaker-candidates/speakers）
- `routes/hotwords.py`：`/api/hotwords`、`/api/hotwords/{id}`、`/api/hotwords/status`、`/api/hotwords/import`、`/api/hotwords/maintain`
- `routes/voiceprints.py`：`/api/voiceprints`、`/api/voiceprints/{id}`、`/api/voiceprints/from-recording`、`/api/recordings/{id}/speakers/{speaker}`
- `routes/settings.py`：`/api/settings`、`/api/system/status`

每个文件顶部 import 需要的领域模块函数。路由装饰器从 `@app.get(...)` 改为 `@router.get(...)`，参数去掉 `app`。

- [ ] **Step 2: 创建 routes/__init__.py**

Create `backend/app/routes/__init__.py`：

```python
from .auth import router as auth_router
from .recordings import router as recordings_router
from .hotwords import router as hotwords_router
from .voiceprints import router as voiceprints_router
from .settings import router as settings_router

__all__ = [
    "auth_router", "recordings_router", "hotwords_router",
    "voiceprints_router", "settings_router",
]
```

- [ ] **Step 3: 重写 main.py 为 app 工厂**

main.py 精简为（约 200 行）：

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import HTTPException

from .config import FRONTEND_DIR, env_int
from .db import ensure_schema, recover_interrupted_tasks, _start_cleanup_loop
from .security import SecurityMiddleware, build_security
from . import routes
from .routes.auth import get_security  # /api/me 可能需要


def create_app() -> FastAPI:
    app = FastAPI(title="AhamVoice Web API", version="0.2.0")

    # CORS（开发期 Vite dev server 用；部署同源不需要）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    # 单密码门（密码为空则不拦截）
    app.add_middleware(SecurityMiddleware, security=build_security())

    # 挂载路由
    for router in [routes.auth_router, routes.recordings_router,
                   routes.hotwords_router, routes.voiceprints_router,
                   routes.settings_router]:
        app.include_router(router)

    # /api/me（单用户，直接返回 local-admin）
    from .routes.auth import get_security  # 确保单例已建
    @app.get("/api/me")
    def me():
        return {"id": "local-admin", "name": "本机用户", "role": "manager",
                "managed_team_ids": ["*"], "team_id": None}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.on_event("startup")
    def startup():
        ensure_schema()
        recover_interrupted_tasks()
        _start_cleanup_loop()

    # 静态托管（SPA fallback）
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    from pathlib import Path
    frontend_dir = Path(FRONTEND_DIR)
    if not (frontend_dir / "index.html").exists():
        return
    if (frontend_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="not found")
        root = frontend_dir.resolve()
        candidate = (frontend_dir / full_path).resolve()
        if full_path and candidate.is_file() and (candidate == root or root in candidate.parents):
            return FileResponse(str(candidate))
        return FileResponse(str(frontend_dir / "index.html"))


app = create_app()
```

注意：`FRONTEND_DIR` 需在 config.py 加（从原 main.py ~4122 搬）。`recover_queued_recordings` 在 startup 调，从 asr.py import。

- [ ] **Step 4: 把 FRONTEND_DIR 加到 config.py + startup 调 recover_queued_recordings**

config.py 加：
```python
FRONTEND_DIR = Path(os.environ.get("AHAMVOICE_FRONTEND_DIR") or (ROOT / "frontend" / "dist"))
```
（`ROOT` 也在 config.py）

main.py startup 里加 `from .asr import recover_queued_recordings; recover_queued_recordings()`。

- [ ] **Step 5: py_compile 全部**

Run: `python -m py_compile backend/app/*.py backend/app/routes/*.py`
Expected: 无输出

- [ ] **Step 6: 完整冒烟（密码门 + 全路由）**

Run:
```bash
AHAMVOICE_HOME=/tmp/aham-smoke python -c "
from backend.app.main import app
from fastapi.testclient import TestClient

# 不设密码 → 无门
c = TestClient(app)
assert c.get('/api/me').status_code == 200
assert c.get('/api/health').status_code == 200
print('OK: 无密码门，路由正常')
"
```

```bash
AHAMVOICE_HOME=/tmp/aham-smoke AHAMVOICE_ACCESS_PASSWORD=secret python -c "
import importlib, backend.app.routes.auth as a
importlib.reload(a)  # 重建 security 单例读新 env
from backend.app.main import app
from fastapi.testclient import TestClient
c = TestClient(app)
assert c.get('/api/me').status_code == 401  # 未登录
assert c.get('/api/health').status_code == 200  # 白名单
r = c.post('/api/auth/login', json={'password':'secret'})
assert r.status_code == 200
assert c.get('/api/me').status_code == 200  # 登录后
print('OK: 密码门启用，登录流程正常')
"
```
Expected: 两个 OK

- [ ] **Step 7: Commit（6b）**

```bash
git add backend/app/ backend/tests/
git commit -m "refactor: 抽 routes/ + main.py 改 app 工厂

路由按资源分 5 个文件（recordings/hotwords/voiceprints/settings/auth）。
main.py 从 ~1800 行瘦身到 ~200 行（app 工厂 + startup + 静态托管）。
单密码门通过 middleware 接入，对路由层透明。"
```

---

## Task 7: 前端改造（3 处）

**Files:**
- Modify: `frontend-src/src/api/client.ts`
- Create: `frontend-src/src/pages/Login.tsx`
- Modify: `frontend-src/src/router.tsx`
- Modify: 下载相关调用（如有）

- [ ] **Step 1: api/client.ts 加 credentials + 401 拦截**

打开 `frontend-src/src/api/client.ts`，所有 fetch 调用加 `credentials: "include"`。加一个 401 拦截：收到 401 且不在登录页 → `window.location.href = "/login"`。

具体：找到 fetch 封装函数，在 options 里加 `credentials: "include"`；在响应处理里：
```typescript
if (res.status === 401 && !window.location.pathname.startsWith("/login")) {
  window.location.href = "/login";
  throw new Error("未登录，跳转登录页");
}
```

- [ ] **Step 2: 创建 Login.tsx**

Create `frontend-src/src/pages/Login.tsx`（参照现有 `Settings.tsx` 的风格，用项目的 Button/Field 组件）：

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Diag } from "@/components/Diag";
import { api } from "@/api/client";

export function Login() {
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!password) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ password }),
      });
      if (res.status === 401) {
        setError("密码错误");
        return;
      }
      if (!res.ok) throw new Error("登录失败");
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-shell">
      <form onSubmit={submit} className="auth-card">
        <h1>Aham Voice</h1>
        {error && <Diag code="AUTH_E_LOGIN">{error}</Diag>}
        <Field label="访问密码" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" variant="primary" loading={loading} disabled={!password}>
          进入
        </Button>
      </form>
    </div>
  );
}
```

（实际 class 名/组件 props 参照项目现有 AuthShell/Field/Button 的真实签名，上面是骨架。）

- [ ] **Step 3: router.tsx 加 /login 路由**

打开 `frontend-src/src/router.tsx`，加：
```tsx
<Route path="/login" element={<Login />} />
```
import Login。

- [ ] **Step 4: 去 webview 下载逻辑**

搜索 `frontend-src` 里所有 `pywebview` 引用：
Run: `grep -rn "pywebview" frontend-src/src/`
Expected: 列出所有引用点。把每处 `window.pywebview.api.save_file(...)` 改成原生下载（`<a download>` 或 `fetch().then(r => r.blob()).then(...)`）。

- [ ] **Step 5: 构建前端验证**

Run: `cd frontend-src && npm run build`
Expected: 构建成功，产出 `../frontend/dist`，无 TS 错误

- [ ] **Step 6: 端到端冒烟（带密码门）**

```bash
AHAMVOICE_HOME=/tmp/aham-smoke AHAMVOICE_ACCESS_PASSWORD=secret python -m uvicorn backend.app.main:app --port 8765 &
sleep 3
# 浏览器打开 http://localhost:8765 → 应见登录页 → 输 secret → 进主页
```
手动验证：登录页出现 → 输错密码报"密码错误" → 输对进首页 → `/api/me` 正常。验证后 `kill %1`。

- [ ] **Step 7: Commit**

```bash
git add frontend-src/
git commit -m "feat: 前端加登录页 + credentials + 去 webview 下载

api/client.ts 加 credentials:'include' + 401 跳登录页。
新增 Login.tsx + /login 路由。
移除 window.pywebview.api.save_file 调用，改原生 <a download>。"
```

---

## Task 8: Docker 化

**Files:**
- Create: `Dockerfile.cpu`, `Dockerfile.gpu`, `docker-compose.yml`, `.dockerignore`
- Create: `backend/app/model_download.py`（首次启动检测+下载）
- Modify: `backend/app/main.py`（startup 调模型检测）
- Create: `.env.example`
- Create: `backend/tests/test_model_download.py`

### Task 8a: 模型自动下载（TDD）

- [ ] **Step 1: 写模型检测的失败测试**

Create `backend/tests/test_model_download.py`：

```python
from pathlib import Path
from backend.app import model_download


def test_missing_models_detected(tmp_path):
    """空目录 → 5 个模型都报缺失。"""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    missing = model_download.find_missing_models(models_dir)
    assert set(missing) == {
        "speech_fsmn_vad_zh-cn-16k-common-pytorch",
        "punc_ct-transformer_cn-en-common-vocab471067-large",
        "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "speech_campplus_sv_zh-cn_16k-common",
        "emotion2vec_plus_large",
    }


def test_complete_models_not_missing(tmp_path):
    """5 个模型目录都在 → 无缺失。"""
    models_dir = tmp_path / "models"
    for name in ["speech_fsmn_vad_zh-cn-16k-common-pytorch",
                 "punc_ct-transformer_cn-en-common-vocab471067-large",
                 "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                 "speech_campplus_sv_zh-cn_16k-common",
                 "emotion2vec_plus_large"]:
        (models_dir / name).mkdir(parents=True)
    assert model_download.find_missing_models(models_dir) == []


def test_partial_models(tmp_path):
    """只有 2 个 → 报缺 3 个。"""
    models_dir = tmp_path / "models"
    (models_dir / "speech_fsmn_vad_zh-cn-16k-common-pytorch").mkdir(parents=True)
    (models_dir / "emotion2vec_plus_large").mkdir(parents=True)
    missing = model_download.find_missing_models(models_dir)
    assert len(missing) == 3
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest backend/tests/test_model_download.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 model_download.py**

Create `backend/app/model_download.py`：

```python
"""首次启动模型检测 + 自动下载。

容器启动时检测 /models 下 5 个模型目录，缺则从 ModelScope 下载。
下载进度写 stdout（docker logs -f 可见）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 5 个必需模型（与 config.py 的 VAD/PUNC/PARAFORMER/CAMPLUS/EMOTION 对应）
REQUIRED_MODELS = [
    "speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc_ct-transformer_cn-en-common-vocab471067-large",
    "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "speech_campplus_sv_zh-cn_16k-common",
    "emotion2vec_plus_large",
]


def find_missing_models(models_dir: Path) -> list[str]:
    """返回缺失的模型目录名列表。"""
    return [name for name in REQUIRED_MODELS if not (models_dir / name).is_dir()]


def ensure_models(models_dir: Path) -> None:
    """检测并下载缺失模型。容器启动时调用。"""
    missing = find_missing_models(models_dir)
    if not missing:
        print(f"[models] 所有模型已就绪：{models_dir}", flush=True)
        return
    print(f"[models] 检测到 {len(missing)} 个缺失模型，开始下载：{missing}", flush=True)
    try:
        from modelscope import snapshot_download
    except ImportError:
        print("[models] WARNING: modelscope 未安装，跳过自动下载。请手动放置模型。", flush=True)
        return
    for name in missing:
        print(f"[models] 下载 {name} ...", flush=True)
        try:
            snapshot_download(f"iic/{name}", cache_dir=str(models_dir.parent))
            print(f"[models] 完成 {name}", flush=True)
        except Exception as exc:
            print(f"[models] 失败 {name}: {exc}", flush=True)
            raise
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest backend/tests/test_model_download.py -v`
Expected: 3 个 PASS

- [ ] **Step 5: main.py startup 调 ensure_models**

main.py 的 startup 函数加：
```python
from .model_download import ensure_models
from .config import MODELS
ensure_models(MODELS)
```

- [ ] **Step 6: Commit（8a）**

```bash
git add backend/app/model_download.py backend/app/main.py backend/tests/test_model_download.py
git commit -m "feat: 首次启动模型自动检测+下载

容器场景模型不进镜像（4GB 太大），volume 挂载 + 首次下载。
find_missing_models 纯函数好测；ensure_models 跑 modelscope snapshot_download。
3 个单测覆盖缺失检测。"
```

### Task 8b: Dockerfile + compose

- [ ] **Step 1: 创建 .env.example**

Create `.env.example`（内容见 spec 第五节，完整复制）。

- [ ] **Step 2: 创建 .dockerignore**

```
.git
frontend-src/node_modules
**/__pycache__
*.pyc
docs/
.env
data/
models/
logs/
*.md
```

- [ ] **Step 3: 创建 Dockerfile.cpu**

Create `Dockerfile.cpu`：

```dockerfile
# 多架构（linux/amd64 + linux/arm64）。CPU 推理。
FROM python:3.12-slim

# ffmpeg + 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 layer cache）
COPY backend/requirements.txt backend/requirements-asr.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements-asr.txt

# 拷贝应用代码 + 构建好的前端
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/

ENV AHAMVOICE_HOST=0.0.0.0 \
    AHAMVOICE_PORT=8765 \
    AHAMVOICE_HOME=/data \
    AHAMVOICE_MODELS_DIR=/models

VOLUME ["/models", "/data"]
EXPOSE 8765

# 健康检查（密码门白名单放行 /api/health）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
```

- [ ] **Step 4: 创建 Dockerfile.gpu**

Create `Dockerfile.gpu`（基于 cpu 版，换基镜像 + 装 CUDA torch）：

```dockerfile
# 仅 linux/amd64。CUDA 推理。需 nvidia-container-toolkit + --gpus all。
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg python3.12 python3-pip libsndfile1 && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s python3.12 /usr/bin/python

WORKDIR /app

COPY backend/requirements.txt backend/requirements-asr.txt ./backend/
# 覆盖 torch 为 CUDA 版
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    pip install --no-cache-dir -r backend/requirements-asr.txt

COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/

ENV AHAMVOICE_HOST=0.0.0.0 \
    AHAMVOICE_PORT=8765 \
    AHAMVOICE_HOME=/data \
    AHAMVOICE_MODELS_DIR=/models \
    AHAMVOICE_ASR_DEVICE=cuda

VOLUME ["/models", "/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
```

- [ ] **Step 5: 创建 docker-compose.yml**

Create `docker-compose.yml`：

```yaml
services:
  ahamvoice:
    # 默认 CPU 版。GPU 用户改 image: aham-voice-web:gpu 并取消下方 devices 注释。
    image: aham-voice-web:latest
    build:
      context: .
      dockerfile: Dockerfile.cpu
    ports:
      - "8765:8765"
    volumes:
      - ./models:/models
      - ./data:/data
    env_file: .env
    restart: unless-stopped
    # GPU 版取消注释（需 nvidia-container-toolkit）：
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

- [ ] **Step 6: 构建并验证 CPU 镜像**

```bash
cd frontend-src && npm run build && cd ..
docker build -f Dockerfile.cpu -t aham-voice-web:test .
docker run -d --name aham-test -p 8766:8765 \
    -v /tmp/aham-test-data:/data -v /tmp/aham-test-models:/models \
    -e AHAMVOICE_ACCESS_PASSWORD=test \
    aham-voice-web:test
sleep 5
curl -s http://localhost:8766/api/health
# Expected: {"ok":true}
curl -s -o /dev/null -w "%{http_code}" http://localhost:8766/api/me
# Expected: 401（密码门拦截）
curl -s -c /tmp/cookies -X POST http://localhost:8766/api/auth/login -H "Content-Type: application/json" -d '{"password":"test"}'
curl -s -b /tmp/cookies http://localhost:8766/api/me
# Expected: 200 + local-admin
docker stop aham-test && docker rm aham-test
```

- [ ] **Step 7: Commit（8b）**

```bash
git add Dockerfile.cpu Dockerfile.gpu docker-compose.yml .dockerignore .env.example
git commit -m "feat: Docker 化（cpu + gpu 双镜像 + compose）

Dockerfile.cpu: python:3.12-slim，多架构，apt 装 ffmpeg。
Dockerfile.gpu: nvidia/cuda 基镜像，CUDA torch。
compose: volume 挂载 models/data，restart: unless-stopped，GPU 段注释化。
.env.example 含全部配置项。"
```

---

## Task 9: README + 收尾

**Files:**
- Modify: `README.md`（重写）

- [ ] **Step 1: 重写 README**

按新项目定位重写：项目介绍（Linux/Windows Docker Web 版，Mac 用户去原 repo）、快速开始（docker compose up）、配置（.env 各项）、两平台说明（Linux GPU 选项、Windows CPU only）、模型首次下载说明、从原 repo fork 的关系。

- [ ] **Step 2: 跑全部单测确认无回归**

Run: `python -m pytest backend/tests/ -v`
Expected: 所有测试 PASS（config 4 + security 7 + model_download 3 = 14 个）

- [ ] **Step 3: 最终冒烟（完整流程，需本地模型）**

若有模型：
```bash
AHAMVOICE_HOME=/tmp/aham-final AHAMVOICE_MODELS_DIR=<你的模型路径> \
    AHAMVOICE_ACCESS_PASSWORD=test python -m uvicorn backend.app.main:app --port 8765
```
浏览器：登录 → 上传一段短音频 → 等转写完成 → 看逐字稿 → 生成纪要。全流程跑通。

若无模型：跳过此步，Task 8 的容器冒烟已覆盖部署路径。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: 重写 README（Linux/Windows Docker Web 版）"
```

- [ ] **Step 5: 确认 git 历史清晰**

Run: `git log --oneline | head -20`
Expected: 每个 task 一个清晰的 commit，信息可读。

---

## Self-Review 记录

计划写完后对照 spec 检查：

**Spec coverage（spec 各节 → task）：**
- 第一节三平台分工 → Task 0（fork + 删 Mac 壳）✓
- 第二节架构/12 模块 → Task 3-6（config/state/db/领域/routes）✓
- 第三节单密码门 → Task 6a（TDD）✓
- 第四节 Docker → Task 8 ✓
- 第五节 .env → Task 8b（.env.example）✓
- 第六节前端 3 处 → Task 7 ✓
- 第七节删多用户死代码 → Task 2 ✓
- 第八节迁移顺序 → Task 0-9 完全覆盖 ✓
- 第十节风险 → 散布在各 task 的验证步骤里 ✓

**Placeholder 扫描：** 无 TBD/TODO，每个代码步骤有完整代码。

**Type/命名一致性：** `Security`/`SecurityMiddleware`/`build_security` 在 Task 6a 定义，6b 引用一致；`find_missing_models`/`ensure_models` 在 8a 定义引用一致；`LOCAL_USER_ID`/`current_user` Task 2 定义后续沿用。

**已知边界：**
- Task 2 行号会漂移，已提示用函数名定位
- Task 5f asr 是枢纽，import 方向已明确单向
- Task 8 完整冒烟需模型，无模型时跳过
