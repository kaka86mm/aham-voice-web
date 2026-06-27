"""热词智能发现：从转写+纪要用 LLM 抽取候选词，去重后入库。

独立于 hotwords.py（纯本地打分/双轨包逻辑）——本模块是 LLM 调用 + 文本处理。
"""
from __future__ import annotations

import json
import re
from typing import Any


def _parse_llm_json(content: str) -> list[dict[str, Any]]:
    """从容许格式的 LLM 响应中解析候选词列表。

    处理：标准 JSON / markdown 包裹 / 前后多余文本 / 空响应。
    要求 JSON 含 "terms" 键（值为候选词数组）。
    """
    if not content or not content.strip():
        return []
    # 去掉 markdown 代码块标记
    cleaned = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()
    # 用 JSONDecoder.raw_decode 从第一个 { 开始解析完整 JSON（支持嵌套）
    start = cleaned.find("{")
    if start == -1:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError:
        return []
    terms = data.get("terms")
    if not isinstance(terms, list):
        return []
    return terms


def _dedupe_against_db(candidates: list[dict[str, Any]], recording_id: str) -> list[dict[str, Any]]:
    """过滤掉已在库的词（active/candidate/protected 跳过，discarded 跳过）+ 同批去重。"""
    from .db import db
    with db() as conn:
        existing = {
            row["word"].lower()
            for row in conn.execute(
                "select word from hotwords where state in ('active', 'candidate', 'protected')"
            ).fetchall()
        }
        discarded = {
            row["word"].lower()
            for row in conn.execute("select word from hotwords where state = 'discarded'").fetchall()
        }
    result = []
    for c in candidates:
        w = (c.get("word") or "").strip().lower()
        if not w or w in existing or w in discarded:
            continue
        existing.add(w)  # 同批内去重
        result.append(c)
    return result
