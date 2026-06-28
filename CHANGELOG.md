# Changelog

本项目基于 [aham-voice](https://github.com/li599198347-svg/aham-voice)（MIT）改造，
从 macOS 桌面应用变为 Linux/Windows Docker Web 应用。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [SemVer](https://semver.org/)。

## [Unreleased]

### Added
- **Web 化**：去桌面壳（pywebview），浏览器访问，Docker 部署（Linux/Windows）
- **单密码门**：局域网共享时可选启用（cookie token + middleware）
- **OpenAI 兼容端点**：纪要/情绪支持任意 OpenAI Chat Completions 兼容服务
- **热词智能发现**：转写+纪要后 LLM 自动抽取候选热词，批量审阅面板确认/纠正/丢弃
- **ROCm 支持**：AMD GPU（gfx1151/Radeon 8060S）容器化 GPU 加速
- **Docker 多架构**：CPU（amd64+arm64）/ GPU（CUDA）/ ROCm 三种镜像变体
- **代码拆分**：单文件 main.py → 13 个聚焦模块
- **测试**：pytest 基础设施 + 26 单测（config/security/model_download/hotword_discover）
- 对齐上游 v2.0.0：speaker_count 字段、声纹 note、声纹删除 API

### Changed
- 多用户死代码清理（删 users/sessions/teams 等表+函数+路由）
- ffmpeg 路径 fallback 到系统 PATH（容器化适配）
- 模型首次启动自动下载（ModelScope）
- 前端 credentials:'include' + 401 跳登录页

### Removed
- macOS 桌面壳（app_launcher.py + packaging/macos/）
- 多用户认证体系（登录/权限/角色）

## 基于上游

- 来源：[aham-voice](https://github.com/li599198347-svg/aham-voice) v2.0.0（MIT License）
- 核心业务逻辑（FunASR 管线/热词双轨/声纹匹配/纪要 map-reduce/情绪分析）原样保留
