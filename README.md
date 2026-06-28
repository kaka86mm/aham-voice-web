<div align="center">

# Aham Voice Web

**录音转写与会议纪要 · 自部署 Web 版 · GPU 加速 · 隐私优先**

[![License: MIT](https://img.shields.io/badge/License-MIT-336EE8.svg)](LICENSE)
[![Type](https://img.shields.io/badge/Type-Self--hosted%20Web%20App-336EE8.svg)](#)
[![GPU](https://img.shields.io/badge/GPU-ROCm%20%7C%20CUDA%20%7C%20CPU-336EE8.svg)](#)
[![Design](https://img.shields.io/badge/Design-Aham%20UI-336EE8.svg)](#)

![Aham Voice](assets/social-preview.png)

[English](#english) · [中文](#中文)

</div>

---

<a id="中文"></a>

## 中文

> 基于 [aham-voice](https://github.com/li599198347-svg/aham-voice)（MIT）改造。Mac 用户请用[原项目](https://github.com/li599198347-svg/aham-voice)（原生 MPS 加速）。

### 为什么做

录音转写工具不少，但多是网页服务：音频要上传到别人的服务器，转写完只给一段没分说话人、没结构的纯文本。本地能离线跑的，又通常停在「出一段字」。

**Aham Voice Web** 把整条链路在你的服务器上接完整——转写、说话人分离、声学情绪全部本地离线 GPU 加速，只有纪要才交给你的大模型，音频和数据不离开你的机器。

### 核心特性

| 特性 | 说明 |
|---|---|
| 🔒 **隐私优先** | 转写/说话人/情绪全部本地，音频不上传 |
| ⚡ **GPU 加速** | AMD ROCm / NVIDIA CUDA / CPU 三种模式，21 分钟录音 30 秒转完 |
| 🤖 **任意大模型** | 纪要走 OpenAI 兼容端点——DeepSeek / 通义 / Kimi / Ollama / vLLM 随便换 |
| 🏷️ **热词智能发现** | 转写后 LLM 自动抽取专业术语，批量审阅确认 |
| 🗣️ **说话人分离** | CAM++ 声纹，逐句标注谁在说，声纹可管理 |
| 📝 **结构化纪要** | 会议类型模板 + 分块生成 + 自然语言改写 |
| 🎭 **双层情绪** | emotion2vec 声学层 + LLM 语义层对冲分析 |
| 🐳 **一键部署** | Docker 镜像，`docker compose up -d` 即用 |

### 快速开始

```bash
git clone <repo> aham-voice-web && cd aham-voice-web
cp .env.example .env          # 填密码 + LLM Key
docker compose up -d          # 首次自动下载 ~4GB 模型
```

浏览器打开 `http://<服务器IP>:8765`，手机/平板同 Wi-Fi 也能访问。

<details>
<summary><b>🖥️ GPU 加速</b></summary>

**NVIDIA CUDA**（Linux）：
```bash
# docker-compose.yml 改 image: aham-voice-web:gpu, dockerfile: Dockerfile.gpu
# 取消 deploy.resources 注释，.env 设 AHAMVOICE_ASR_DEVICE=cuda
```

**AMD ROCm**（gfx1151/Radeon 等）：
```bash
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d
```

</details>

<details>
<summary><b>⚙️ 配置项（.env）</b></summary>

```bash
AHAMVOICE_ACCESS_PASSWORD=          # 空=裸奔；非空=启用单密码门
LLM_API_KEY=                         # OpenAI 兼容端点的 Key
LLM_API_BASE=https://api.deepseek.com
LLM_MODEL=deepseek-chat
AHAMVOICE_ASR_DEVICE=cpu             # cpu / cuda
```

</details>

<details>
<summary><b>🏗️ 架构</b></summary>

```
backend/app/
├── main.py            # FastAPI + 路由 + 静态托管
├── config.py          # 路径/env/LLM 配置
├── db.py              # SQLite + schema + 中断恢复
├── security.py        # 单密码门
├── asr.py             # FunASR 转写（枢纽）
├── hotwords.py        # 热词双轨系统
├── hotword_discover.py # 热词 LLM 智能发现
├── voiceprint.py      # 声纹多采样匹配
├── emotion.py         # emotion2vec + LLM 情绪
├── summary.py         # 纪要 map-reduce + 改写
└── deepseek.py        # LLM 传输层
```

</details>

<details>
<summary><b>🔧 本地开发</b></summary>

```bash
# 后端
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
AHAMVOICE_HOME=/tmp/aham-dev python -m uvicorn backend.app.main:app --port 8765 --reload

# 前端（另一个终端）
cd frontend-src && npm install && npm run dev   # Vite 5174

# 测试
python -m pytest backend/tests/ -v
```

</details>

### 三平台分工

| 平台 | 方案 | GPU |
|---|---|---|
| **Mac** | [原项目](https://github.com/li599198347-svg/aham-voice) | MPS ✅ |
| **Linux** | 本项目 Docker | CUDA / ROCm / CPU |
| **Windows** | 本项目 Docker | CPU |

---

<a id="english"></a>

## English

> Forked from [aham-voice](https://github.com/li599198347-svg/aham-voice) (MIT). Mac users should use the [original project](https://github.com/li599198347-svg/aham-voice) (native MPS acceleration).

### Why

Most transcription tools are cloud services: you upload audio to someone else's server, and get back unstructured plain text without speaker labels. Local tools usually stop at "here's some text."

**Aham Voice Web** completes the entire pipeline on your own server — transcription, speaker diarization, and acoustic emotion all run locally with GPU acceleration. Only the meeting summary goes to your LLM. Audio and data never leave your machine.

### Key Features

| Feature | Description |
|---|---|
| 🔒 **Privacy-first** | Transcription/diarization/emotion all local — audio never uploaded |
| ⚡ **GPU accelerated** | AMD ROCm / NVIDIA CUDA / CPU — 21-min audio in 30 seconds |
| 🤖 **Any LLM** | Summaries via OpenAI-compatible endpoint — DeepSeek / Qwen / Kimi / Ollama / vLLM |
| 🏷️ **Smart hotword discovery** | LLM auto-extracts domain terms post-transcription, batch review |
| 🗣️ **Speaker diarization** | CAM++ voiceprints, per-utterance speaker labels, manageable profiles |
| 📝 **Structured summaries** | Meeting-type templates + chunked generation + NL revision |
| 🎭 **Dual-layer emotion** | emotion2vec acoustic + LLM semantic analysis |
| 🐳 **One-command deploy** | Docker image, `docker compose up -d` and you're running |

### Quick Start

```bash
git clone <repo> aham-voice-web && cd aham-voice-web
cp .env.example .env          # Set password + LLM key
docker compose up -d          # Auto-downloads ~4GB models on first run
```

Open `http://<server-ip>:8765` in your browser. Phones/tablets on the same Wi-Fi can access it too.

<details>
<summary><b>🖥️ GPU Acceleration</b></summary>

**NVIDIA CUDA** (Linux):
```bash
# Edit docker-compose.yml: image: aham-voice-web:gpu, dockerfile: Dockerfile.gpu
# Uncomment deploy.resources, set AHAMVOICE_ASR_DEVICE=cuda in .env
```

**AMD ROCm** (gfx1151/Radeon etc.):
```bash
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up -d
```

</details>

<details>
<summary><b>⚙️ Configuration (.env)</b></summary>

```bash
AHAMVOICE_ACCESS_PASSWORD=          # Empty=no gate; set to enable password
LLM_API_KEY=                         # Your OpenAI-compatible API key
LLM_API_BASE=https://api.deepseek.com
LLM_MODEL=deepseek-chat
AHAMVOICE_ASR_DEVICE=cpu             # cpu / cuda
```

</details>

### License

[MIT](LICENSE) — forked from [aham-voice](https://github.com/li599198347-svg/aham-voice) (MIT)

---

<div align="center">

**把灵光一现，做成能用的 AI 工具。**

*Turn sparks of insight into AI tools that actually work.*

</div>
