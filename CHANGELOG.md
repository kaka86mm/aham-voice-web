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
- **测试**：pytest 基础设施 + 53 单测（config/security/model_download/hotword_discover/glossary/chunking/docx）
- 对齐上游 v2.0.0：speaker_count 字段、声纹 note、声纹删除 API
- **纪要质量增强**：
  - 热词规范名词表注入 LLM——纪要中专有名词（产品/系统/项目/人名）统一用规范写法，不再被 ASR 同音错字带偏
  - 转写按段边界智能切块——替代字符数硬切，避免把一个话题/说话人轮次劈成两半，长会议纪要信息更完整
  - 空小节省略——纪要不再满屏"未明确"，显得空洞
- **时间戳跳转**：纪要里的时间戳（如 `[00:12:30]`）渲染成可点击胶囊，点击后左侧播放器自动 seek 到对应时刻并播放，无需手动翻找
- **Word(docx) 导出**：纪要支持 docx 格式下载（国内主流），下载菜单可选 Word/Markdown；自建 Markdown→docx 转换器（python-docx），无需 pandoc/libreoffice 重型依赖

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
