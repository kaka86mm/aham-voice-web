"""首次启动模型检测 + 自动下载。

容器场景模型不进镜像（4GB 太大），volume 挂载 + 首次下载。
find_missing_models 是纯函数（好测）；ensure_models 跑 modelscope
snapshot_download，进度写 stdout（docker logs -f 可见）。
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
