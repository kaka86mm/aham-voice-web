"""会议纪要：分块 map-reduce、模板、自然语言改写、导出。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from .config import env_int, EXPORTS, get_llm_config
from .db import (
    db, now, rowdict, safe_json, slug, seconds_label,
    create_task, update_task, can_access_recording, audit,
)
from .deepseek import _deepseek_post_with_retry
from .emotion import current_emotion_analysis


def transcript_text(conn: sqlite3.Connection, recording_id: str) -> str:
    rows = conn.execute(
        "select start_label, end_sec, speaker, speaker_name, text from transcript_segments where recording_id = ? order by start_sec",
        (recording_id,),
    ).fetchall()
    lines = []
    for row in rows:
        label = row["speaker_name"] or f"Speaker {row['speaker']}"
        lines.append(f"[{row['start_label']}-{seconds_label(row['end_sec'])}] {label}: {row['text']}")
    return "\n".join(lines)



def summary_depth_instruction(rec: dict[str, Any], text: str) -> str:
    duration = float(rec.get("duration") or 0)
    if duration >= 7200:
        target = "最终纪要建议 4500-7000 个中文字符，至少覆盖 10 个以上具体议题或商机/项目节点。"
    elif duration >= 3600:
        target = "最终纪要建议 3200-5200 个中文字符，至少覆盖 8 个以上具体议题或商机/项目节点。"
    elif duration >= 1200:
        target = "最终纪要建议 1800-3200 个中文字符，至少覆盖 5 个以上具体议题。"
    else:
        target = "最终纪要建议 900-1800 个中文字符，短会也要保留具体事实，不要只写泛泛概括。"
    if len(text) > 90000:
        target += " 转写很长，合并时要优先保留反复讨论、出现具体客户/项目/数字/系统名的内容。"
    return target



def meeting_focus_instruction(meeting_type: str) -> str:
    if meeting_type == "内部会议":
        return (
            "会议类型是内部会议。重点沉淀：销售/项目复盘脉络、客户或商机名称、项目阶段、现场判断、争议点、"
            "资源/报价/方案/交付边界等讨论内容。不要写行动项或跟进清单。"
        )
    if meeting_type == "客户调研":
        return (
            "会议类型是客户调研。重点沉淀：客户业务背景、当前系统与流程、涉及部门/岗位、痛点或关注点、"
            "预算/周期/范围等被明确提到的信息、客户原话和待澄清点。不要生成客户需求库。"
        )
    if meeting_type == "方案汇报":
        return (
            "会议类型是方案汇报。重点沉淀：方案范围、模块能力、客户反馈、异议与澄清、部署/集成/数据口径、"
            "报价或边界讨论、达成共识与仍需确认的问题。"
        )
    if meeting_type == "销售电话":
        return (
            "会议类型是销售电话。重点沉淀：客户/联系人、来电背景、关注问题、产品或服务匹配点、价格/周期/竞品/决策链线索、"
            "对话中的明确结论和待确认问题。"
        )
    return "根据会议类型保留业务背景、讨论细节、明确结论、待确认问题和可追溯原文证据。"



def meeting_template(meeting_type: str) -> str:
    """每类会议的专属纪要结构骨架。AI 按对应结构逐节输出，无内容的小节写“未明确”。
    顶部「会议信息/一句话概览」与底部「关键原文证据」是所有类型共用的壳，
    中间板块按会议类型切换。"""
    head = ["# 会议纪要", "## 会议信息", "## 一句话概览"]
    foot = ["## 关键原文证据"]
    bodies = {
        "销售电话": [
            "## 通话背景（客户 / 联系人 / 来电由头）",
            "## 客户现状与关注点",
            "## 产品 / 服务匹配讨论",
            "## 价格 / 周期 / 竞品 / 决策链线索",
            "## 关键结论",
            "## 待确认问题",
        ],
        "客户调研": [
            "## 客户业务背景",
            "## 当前系统与流程现状",
            "## 涉及部门 / 岗位",
            "## 痛点与关注点",
            "## 预算 / 周期 / 范围（已明确提到的）",
            "## 客户原话与待澄清点",
        ],
        "方案汇报": [
            "## 方案范围与模块能力",
            "## 客户反馈",
            "## 异议与澄清",
            "## 部署 / 集成 / 数据口径",
            "## 报价与边界讨论",
            "## 达成共识与仍需确认",
        ],
        "内部会议": [
            "## 复盘主线（客户 / 商机 / 项目阶段）",
            "## 各汇报人分述（能识别汇报人时每人一节，逐个过其名下项目：阶段/卡点/策略/结论）",
            "## 争议点",
            "## 资源 / 报价 / 方案 / 交付边界",
            "## 关键结论",
            "## 待确认问题",
        ],
    }
    default_body = [
        "## 核心摘要",
        "## 讨论主线",
        "## 重点议题详述",
        "## 客户 / 项目 / 商机信息沉淀",
        "## 关键结论",
        "## 待确认问题",
    ]
    body = bodies.get((meeting_type or "").strip(), default_body)
    return "\n".join(head + body + foot)



async def call_deepseek_summary(text: str, rec: dict[str, Any]) -> tuple[str, str]:
    api_key, base, model = get_llm_config()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    chunk_chars = env_int("AHAMVOICE_SUMMARY_CHUNK_CHARS", 18000, 8000, 28000)
    chunks = [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)] or [""]
    depth = summary_depth_instruction(rec, text)
    focus = meeting_focus_instruction(rec.get("meeting_type") or "")
    partials: list[str] = []
    chat_url = f"{base}/chat/completions"
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        for index, chunk in enumerate(chunks, 1):
            payload = {
                "model": model,
                "temperature": 0.2,
                "max_tokens": env_int("AHAMVOICE_SUMMARY_CHUNK_MAX_TOKENS", 4096, 1200, 8192),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是企业内部会议纪要的信息抽取助手。只基于转写文本输出，不编造事实。"
                            "你的任务不是压缩到最短，而是保留后续生成详细纪要所需的事实、对象、数字、观点和证据。"
                            "禁止提炼行动项、待办、下一步、风险或客户需求模块。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "请把下面这段转写整理成“分块纪要素材”，用于后续合成完整会议纪要。\n"
                            "要求：\n"
                            "1. 不要只写摘要，要保留具体客户/项目/系统/产品/人员/金额/时间/数量/阶段等信息。\n"
                            "2. 每个议题写清背景、讨论内容、不同说话人的观点或判断、已形成的共识、仍待确认的问题。\n"
                            "3. 原文证据必须带时间戳，优先选择能支撑结论的短句；识别不确定的词用“疑似”。\n"
                            "4. 如果本段只是闲聊或重复内容，可以标注为低信息密度，但不能编造。\n"
                            "5. 全文不要出现“行动项”“待办”“下一步”“跟进事项”等表述。\n\n"
                            "输出 Markdown，固定结构：\n"
                            "### 本段核心概览\n"
                            "### 议题与细节\n"
                            "### 客户/项目/商机/系统实体\n"
                            "### 结论与待确认\n"
                            "### 可引用原文证据\n\n"
                            f"录音标题：{rec['title']}\n"
                            f"会议类型：{rec['meeting_type']}\n"
                            f"分块：{index}/{len(chunks)}\n\n"
                            f"{focus}\n\n"
                            f"{chunk}"
                        ),
                    },
                ],
            }
            partials.append(await _deepseek_post_with_retry(client, chat_url, api_key, payload))

        final_payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": env_int("AHAMVOICE_SUMMARY_FINAL_MAX_TOKENS", 8192, 2000, 12000),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是企业内部会议纪要助手。输出信息丰富、层次清楚、可追溯的 Markdown 纪要。"
                        "只基于转写和分块素材，不编造事实；不确定内容必须标注“疑似”或“未明确”。"
                        "重要：转写里的公司/项目/人名可能被语音识别带偏或张冠李戴——突兀的长全称"
                        "（尤其含“有限公司/集团”且只出现一两次的）不要当成标准项目名，优先用口语高频的简称；"
                        "同一项目出现多个候选名时取最一致的那个；项目归属（谁负责/哪个客户）拿不准就标“疑似”，绝不硬编。"
                        "禁止输出或提及行动项、待办、下一步、风险、客户需求、CRM 跟进模块。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"请将以下分块素材合并为最终纪要。纪要要比普通摘要更丰富，适合销售经理或项目负责人回看会议全貌。\n\n"
                        f"标题：{rec['title']}\n"
                        f"会议类型：{rec['meeting_type']}\n"
                        f"录音时长：{rec['duration_label']}\n\n"
                        f"深度要求：{depth}\n"
                        f"类型侧重点：{focus}\n\n"
                        "写作要求：\n"
                        "- 先给整体判断，再按议题展开细节；不要把所有内容压成三五条。\n"
                        "- 每个重点议题尽量包含：背景/上下文、讨论细节、相关人或客户态度、明确结论、待确认问题、时间戳证据。\n"
                        "- 对长会议，要按客户/项目/模块/流程分组，合并重复表达，但保留具体名称和关键数字。\n"
                        "- 关键原文证据要分散覆盖主要议题，不要只引用开头几分钟。\n"
                        "- 不要出现“行动项”“待办”“下一步”“跟进事项”等表述。\n\n"
                        "请严格按以下结构输出（小节标题和顺序保持不变；某节无内容就写“未明确”，不要删节也不要新增顶级小节）：\n"
                        + meeting_template(rec.get("meeting_type") or "") + "\n\n"
                        + "\n\n".join(partials)
                    ),
                },
            ],
        }
        return await _deepseek_post_with_retry(client, chat_url, api_key, final_payload), model



async def call_deepseek_revision(instruction: str, base_summary: str, transcript: str, rec: dict[str, Any]) -> tuple[str, str]:
    api_key, base, model = get_llm_config()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    if len(transcript) <= 26000:
        transcript_context = transcript
    else:
        transcript_context = (
            transcript[:9000]
            + "\n\n[中间转写过长，以下保留当前纪要和末尾校验片段；需要更多细节时请重新生成完整纪要。]\n\n"
            + transcript[-9000:]
        )
    depth = summary_depth_instruction(rec, transcript)
    focus = meeting_focus_instruction(rec.get("meeting_type") or "")
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": env_int("AHAMVOICE_SUMMARY_FINAL_MAX_TOKENS", 8192, 2000, 12000),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是企业内部会议纪要助手。根据用户修改要求重写完整 Markdown 纪要。"
                    "保持信息丰富、结构清楚、可追溯；只基于原纪要和转写文本，不编造事实。"
                    "转写里的公司/项目/人名可能被语音识别带偏——突兀的长全称不要当标准名、优先口语简称，归属拿不准标“疑似”。"
                    "禁止输出或提及行动项、待办、下一步、风险、客户需求、CRM 跟进模块。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"录音标题：{rec['title']}\n"
                    f"会议类型：{rec['meeting_type']}\n"
                    f"录音时长：{rec['duration_label']}\n\n"
                    f"深度要求：{depth}\n"
                    f"类型侧重点：{focus}\n\n"
                    f"目标结构（除非用户明确要求改结构，否则按此组织小节）：\n{meeting_template(rec.get('meeting_type') or '')}\n\n"
                    f"用户修改要求：\n{instruction}\n\n"
                    f"当前纪要：\n{base_summary}\n\n"
                    f"转写文本校验依据：\n{transcript_context}\n\n"
                    "请输出修改后的完整 Markdown 纪要。除非用户明确要求删减，否则要保留并补足具体信息、实体名称、数字、讨论细节和时间戳证据；不要只输出简短摘要。"
                ),
            },
        ],
    }
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        content = await _deepseek_post_with_retry(client, f"{base}/chat/completions", api_key, payload)
    return content, model



def next_summary_version(conn: sqlite3.Connection, recording_id: str) -> int:
    current = conn.execute(
        "select coalesce(max(version), 0) from summaries where recording_id = ?",
        (recording_id,),
    ).fetchone()[0]
    return int(current or 0) + 1



async def summarize_recording(recording_id: str, user: dict[str, Any]) -> dict[str, Any]:
    with db() as conn:
        rec = can_access_recording(conn, recording_id, user)
        if rec["asr_status"] != "done":
            raise HTTPException(status_code=409, detail="transcript is not ready")
        text = transcript_text(conn, recording_id)
        if not text.strip():
            raise HTTPException(status_code=409, detail="transcript is empty")
        task_id = create_task(conn, recording_id, rec["title"], "云端纪要")
        conn.execute("update recordings set summary_status = ?, updated_at = ? where id = ?", ("running", now(), recording_id))
        version = next_summary_version(conn, recording_id)
        conn.commit()

    try:
        content, model = await call_deepseek_summary(text, rec)
        with db() as conn:
            summary_id = str(uuid.uuid4())
            conn.execute("update summaries set is_current = 0 where recording_id = ?", (recording_id,))
            conn.execute(
                """
                insert into summaries(id,recording_id,content,model,created_at,version,instruction,base_summary_id,is_current)
                values(?,?,?,?,?,?,?,?,?)
                """,
                (summary_id, recording_id, content, model, now(), version, None, None, 1),
            )
            conn.execute(
                "update recordings set summary_status = ?, updated_at = ? where id = ?",
                ("done", now(), recording_id),
            )
            update_task(conn, task_id, "done", 100)
            audit(conn, user, "summary", f"生成会议纪要：{rec['title']}，模型 {model}。")
        return {"recording_id": recording_id, "model": model, "summary_id": summary_id, "version": version}
    except Exception as exc:
        with db() as conn:
            conn.execute(
                "update recordings set summary_status = ?, updated_at = ? where id = ?",
                ("failed", now(), recording_id),
            )
            update_task(conn, task_id, "failed", 100, str(exc))
            audit(conn, user, "summary", f"DeepSeek 调用失败：{rec['title']}。")
        print(f"[error] summary: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="纪要生成失败，请查看日志") from exc



async def revise_summary(recording_id: str, instruction: str, user: dict[str, Any]) -> dict[str, Any]:
    instruction = (instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")
    with db() as conn:
        rec = can_access_recording(conn, recording_id, user)
        if rec["asr_status"] != "done":
            raise HTTPException(status_code=409, detail="transcript is not ready")
        base_summary = rowdict(
            conn.execute(
                """
                select * from summaries
                where recording_id = ?
                order by is_current desc, version desc, created_at desc
                limit 1
                """,
                (recording_id,),
            ).fetchone()
        )
        if not base_summary:
            raise HTTPException(status_code=409, detail="summary is not ready")
        text = transcript_text(conn, recording_id)
        task_id = create_task(conn, recording_id, rec["title"], "自然语言修改纪要")
        conn.execute("update recordings set summary_status = ?, updated_at = ? where id = ?", ("running", now(), recording_id))
        version = next_summary_version(conn, recording_id)
        conn.commit()

    try:
        content, model = await call_deepseek_revision(instruction, base_summary["content"], text, rec)
        with db() as conn:
            summary_id = str(uuid.uuid4())
            conn.execute("update summaries set is_current = 0 where recording_id = ?", (recording_id,))
            conn.execute(
                """
                insert into summaries(id,recording_id,content,model,created_at,version,instruction,base_summary_id,is_current)
                values(?,?,?,?,?,?,?,?,?)
                """,
                (summary_id, recording_id, content, model, now(), version, instruction, base_summary["id"], 1),
            )
            conn.execute(
                "update recordings set summary_status = ?, updated_at = ? where id = ?",
                ("done", now(), recording_id),
            )
            update_task(conn, task_id, "done", 100)
            audit(conn, user, "summary", f"按自然语言要求修改纪要：{rec['title']}，版本 v{version}。")
        return {"recording_id": recording_id, "model": model, "summary_id": summary_id, "version": version}
    except Exception as exc:
        with db() as conn:
            conn.execute(
                "update recordings set summary_status = ?, updated_at = ? where id = ?",
                ("failed", now(), recording_id),
            )
            update_task(conn, task_id, "failed", 100, str(exc))
            audit(conn, user, "summary", f"自然语言修改纪要失败：{rec['title']}。")
        print(f"[error] revision: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail="纪要改写失败，请查看日志") from exc



def transcript_markdown(conn: sqlite3.Connection, rec: dict[str, Any]) -> str:
    rows = conn.execute(
        "select start_label, end_sec, speaker, speaker_name, text from transcript_segments where recording_id = ? order by start_sec",
        (rec["id"],),
    ).fetchall()
    parts = []
    for row in rows:
        label = row["speaker_name"] or f"Speaker {row['speaker']}"
        parts.append(f"### {row['start_label']}-{seconds_label(row['end_sec'])} · {label}\n\n{row['text']}")
    body = "\n\n".join(parts)
    return (
        f"# {rec['title']} 转写\n\n"
        "## 录音信息\n\n"
        f"- 会议类型：{rec['meeting_type']}\n"
        f"- 客户 / 项目：{rec.get('tag') or '-'}\n"
        f"- 录音时长：{rec['duration_label']}\n"
        "- ASR 引擎：Paraformer + FSMN-VAD + CT-Punc + CAM++\n"
        "- 切分方式：VAD 动态切分后合并为语义发言段\n"
        "- 热词：启用本地热词库纠错\n\n"
        "## 完整转写\n\n"
        f"{body or '暂无转写内容。'}\n"
    )



def write_export(recording_id: str, kind: str, user: dict[str, Any]) -> Path:
    with db() as conn:
        rec = can_access_recording(conn, recording_id, user)
        if kind == "transcript":
            content = transcript_markdown(conn, rec)
            suffix = "转写"
        elif kind == "summary":
            summary = rowdict(
                conn.execute(
                    """
                    select * from summaries
                    where recording_id = ?
                    order by is_current desc, version desc, created_at desc
                    limit 1
                    """,
                    (recording_id,),
                ).fetchone()
            )
            if not summary:
                raise HTTPException(status_code=404, detail="summary not found")
            content = summary["content"]
            suffix = f"纪要_v{summary.get('version') or 1}"
        elif kind == "emotion":
            emotion = current_emotion_analysis(conn, recording_id)
            if not emotion:
                raise HTTPException(status_code=404, detail="emotion analysis not found")
            content = emotion["content"]
            suffix = f"情绪分析_v{emotion.get('version') or 1}"
        else:
            raise HTTPException(status_code=404, detail="unknown export")
    path = EXPORTS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug(rec['title'])}_{suffix}.md"
    path.write_text(content, encoding="utf-8")
    return path



def write_summary_export(recording_id: str, summary_id: str, user: dict[str, Any]) -> Path:
    with db() as conn:
        rec = can_access_recording(conn, recording_id, user)
        summary = rowdict(
            conn.execute(
                "select * from summaries where recording_id = ? and id = ?",
                (recording_id, summary_id),
            ).fetchone()
        )
        if not summary:
            raise HTTPException(status_code=404, detail="summary not found")
        suffix = f"纪要_v{summary.get('version') or 1}"
        path = EXPORTS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug(rec['title'])}_{suffix}.md"
        path.write_text(summary["content"], encoding="utf-8")
        return path

