# -*- coding: utf-8 -*-
"""
Agency 比稿主流程。
==================

流水线：
  Phase 1 — Brief 结构化 + 联网搜索（复用 Planner）
  Phase 2 — Agency 组队
  Phase 3 — 独立提案（并行 LLM）
  Phase 4 — 交叉点评（并行 LLM）
  Phase 5 — 裁决 + 融合
  Phase 6 — 保存 & 推送

使用方式：
  CLI  : python3 -m pitch --topic "618 大促营销方案"
  代码 : from pitch.run import run_pitch
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.feishu_webhook import send_planner_text as send_text, send_planner_card
from core.llm import chat_completion
from core.utils import load_context, run_timestamp, save_session, truncate_for_display
from pitch.agencies import Agency, DEFAULT_AGENCIES, parse_agency_spec
from pitch.prompts import (
    PITCH_INSTRUCTION,
    CRITIQUE_SYSTEM,
    CRITIQUE_INSTRUCTION,
    VERDICT_SYSTEM,
    VERDICT_INSTRUCTION,
    DOC_PITCH_REPORT_SYSTEM,
)

FEISHU_INTERVAL = 1.0
PROVIDER = "deepseek"


# ---------------------------------------------------------------------------
# Phase 1 — Brief 结构化 + 联网搜索
# ---------------------------------------------------------------------------

def _refine_and_research(topic: str, context: str) -> tuple[str, str]:
    """复用 Planner 的 Brief 结构化和联网搜索能力。返回 (enriched_context, brief)。"""
    from planner.run import refine_brief, research_for_planning

    print("[比稿] Phase 1: Brief 结构化…", flush=True)
    brief = refine_brief(topic, context)
    if brief:
        send_planner_card("🏆 比稿启动 — Brief", truncate_for_display(brief), color="indigo")
        time.sleep(FEISHU_INTERVAL)
        context = brief + "\n\n" + context
    else:
        print("[比稿] Brief 结构化失败，使用原始输入", flush=True)

    search_ctx = research_for_planning(topic, context)
    if search_ctx:
        context = context + "\n\n【联网搜索补充材料】\n" + search_ctx

    return context, brief or topic


# ---------------------------------------------------------------------------
# Phase 3 — 独立提案（单个 Agency）
# ---------------------------------------------------------------------------

def _generate_proposal(agency: Agency, topic: str, context: str) -> str:
    """为单个 Agency 生成提案。"""
    user_msg = (
        f"## 比稿课题\n{topic}\n\n"
        f"## 背景材料\n{context[:6000]}\n\n"
        f"{PITCH_INSTRUCTION}"
    )
    try:
        from core.skill_router import enrich_prompt
        system = enrich_prompt(agency.system_prompt, user_text=user_msg, bot_type="planner")
    except Exception:
        system = agency.system_prompt

    return chat_completion(provider=PROVIDER, system=system, user=user_msg).strip()


def _run_proposals_parallel(
    agencies: List[Agency], topic: str, context: str,
) -> list[tuple[Agency, str]]:
    """Phase 3: 并行生成所有提案。"""
    print(f"[比稿] Phase 3: {len(agencies)} 个 Agency 并行提案…", flush=True)
    send_planner_card(
        "🏆 比稿进行中 — 提案阶段",
        f"**{len(agencies)} 个 Agency** 正在独立出方案（互相看不到）…\n\n"
        + "\n".join(f"- {a.emoji} {a.name}" for a in agencies),
        color="purple",
    )
    time.sleep(FEISHU_INTERVAL)

    results: list[tuple[Agency, str]] = [None] * len(agencies)  # type: ignore

    with ThreadPoolExecutor(max_workers=len(agencies)) as pool:
        futures = {
            pool.submit(_generate_proposal, ag, topic, context): i
            for i, ag in enumerate(agencies)
        }
        for future in as_completed(futures):
            idx = futures[future]
            ag = agencies[idx]
            try:
                proposal = future.result()
                results[idx] = (ag, proposal)
                print(f"  ✅ {ag.name} 提案完成 ({len(proposal)} 字)", flush=True)
                send_planner_card(
                    f"{ag.emoji} {ag.name} 提案",
                    truncate_for_display(proposal),
                    color=ag.color,
                )
                time.sleep(FEISHU_INTERVAL)
            except Exception as e:
                print(f"  ❌ {ag.name} 提案失败: {e}", flush=True)
                results[idx] = (ag, f"（{ag.name}提案生成失败）")

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Phase 4 — 交叉点评
# ---------------------------------------------------------------------------

def _generate_critique(
    reviewer: Agency,
    reviewer_proposal: str,
    opponents: list[tuple[Agency, str]],
) -> str:
    """让一个 Agency 点评其他 Agency 的方案。"""
    parts = [f"你是 **{reviewer.name}**。\n\n你的提案摘要：\n{reviewer_proposal[:1500]}\n"]
    for opp_ag, opp_prop in opponents:
        parts.append(f"--- {opp_ag.emoji} {opp_ag.name} 的提案 ---\n{opp_prop[:2000]}\n")
    parts.append(CRITIQUE_INSTRUCTION)
    user_msg = "\n\n".join(parts)

    system = CRITIQUE_SYSTEM + f"\n\n你代表的是 **{reviewer.name}** 的立场。"
    return chat_completion(provider=PROVIDER, system=system, user=user_msg).strip()


def _run_critiques_parallel(
    proposals: list[tuple[Agency, str]],
) -> list[tuple[Agency, str]]:
    """Phase 4: 并行交叉点评。"""
    print(f"[比稿] Phase 4: 交叉点评…", flush=True)
    send_planner_card(
        "🏆 比稿进行中 — 交叉点评",
        "各 Agency 正在互相点评对方方案…\n\n"
        "规则：承认亮点 → 指出软肋 → 说想偷什么",
        color="orange",
    )
    time.sleep(FEISHU_INTERVAL)

    results: list[tuple[Agency, str]] = [None] * len(proposals)  # type: ignore

    with ThreadPoolExecutor(max_workers=len(proposals)) as pool:
        futures = {}
        for i, (reviewer_ag, reviewer_prop) in enumerate(proposals):
            opponents = [(ag, prop) for j, (ag, prop) in enumerate(proposals) if j != i]
            futures[pool.submit(_generate_critique, reviewer_ag, reviewer_prop, opponents)] = i

        for future in as_completed(futures):
            idx = futures[future]
            ag = proposals[idx][0]
            try:
                critique = future.result()
                results[idx] = (ag, critique)
                print(f"  ✅ {ag.name} 点评完成", flush=True)
                send_planner_card(
                    f"{ag.emoji} {ag.name} 的点评",
                    truncate_for_display(critique),
                    color=ag.color,
                )
                time.sleep(FEISHU_INTERVAL)
            except Exception as e:
                print(f"  ❌ {ag.name} 点评失败: {e}", flush=True)
                results[idx] = (ag, f"（{ag.name}点评生成失败）")

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Phase 5 — 裁决 + 融合
# ---------------------------------------------------------------------------

def _run_verdict(
    topic: str,
    proposals: list[tuple[Agency, str]],
    critiques: list[tuple[Agency, str]],
) -> str:
    """Phase 5: 裁判做最终裁决。"""
    print("[比稿] Phase 5: 裁决与融合…", flush=True)
    send_planner_card("🏆 比稿进行中 — 裁决", "裁判正在评审所有方案…", color="green")
    time.sleep(FEISHU_INTERVAL)

    parts = [f"## 比稿课题\n{topic}\n"]

    for ag, prop in proposals:
        parts.append(f"--- {ag.emoji} {ag.name} 的提案 ---\n{prop}")

    parts.append("\n## 交叉点评\n")
    for ag, crit in critiques:
        parts.append(f"--- {ag.emoji} {ag.name} 的点评 ---\n{crit}")

    parts.append(f"\n{VERDICT_INSTRUCTION}")
    user_msg = "\n\n".join(parts)

    verdict = chat_completion(provider=PROVIDER, system=VERDICT_SYSTEM, user=user_msg).strip()

    send_planner_card("🏆 裁决结果", truncate_for_display(verdict), color="green")
    time.sleep(FEISHU_INTERVAL)
    return verdict


# ---------------------------------------------------------------------------
# 比稿报告生成（文档用）
# ---------------------------------------------------------------------------

def generate_pitch_report(
    topic: str,
    proposals: list[tuple[Agency, str]],
    critiques: list[tuple[Agency, str]],
    verdict: str,
) -> str:
    """生成完整比稿报告文档。"""
    parts = [f"## 比稿课题\n{topic}\n"]
    for ag, prop in proposals:
        parts.append(f"--- {ag.emoji} {ag.name} ---\n{prop}")
    parts.append("\n## 交叉点评\n")
    for ag, crit in critiques:
        parts.append(f"--- {ag.emoji} {ag.name} ---\n{crit}")
    parts.append(f"\n## 裁决\n{verdict}")

    user_msg = "\n\n".join(parts)
    return chat_completion(
        provider=PROVIDER, system=DOC_PITCH_REPORT_SYSTEM, user=user_msg,
    ).strip()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_pitch(
    topic: str,
    context: str = "",
    agencies: Optional[List[Agency]] = None,
) -> tuple[str, list[tuple[int, str, str]], dict]:
    """
    执行完整比稿流程。

    Returns:
        (session_path, planning_outputs, pitch_data)
        - planning_outputs: 与 Planner 格式兼容的 [(step_num, step_name, output), ...]
        - pitch_data: 原始比稿数据，用于后续文档生成
    """
    ts = run_timestamp()
    if agencies is None:
        agencies = list(DEFAULT_AGENCIES)

    session_lines = [
        f"# Agency 比稿 Session {ts}",
        f"课题：{topic}",
        f"Agency：{', '.join(a.name for a in agencies)}",
        "",
    ]

    # Phase 1 — Brief + 搜索
    enriched_context, brief = _refine_and_research(topic, context)
    session_lines.extend(["## Brief", "", brief, "", "---", ""])

    # Phase 3 — 并行提案
    proposals = _run_proposals_parallel(agencies, topic, enriched_context)
    for ag, prop in proposals:
        session_lines.extend([f"## {ag.emoji} {ag.name} 提案", "", prop, "", "---", ""])

    # Phase 4 — 交叉点评
    critiques = _run_critiques_parallel(proposals)
    for ag, crit in critiques:
        session_lines.extend([f"## {ag.emoji} {ag.name} 点评", "", crit, "", "---", ""])

    # Phase 5 — 裁决
    verdict = _run_verdict(topic, proposals, critiques)
    session_lines.extend(["## 裁决与融合", "", verdict, "", "---", ""])

    # 保存
    session_content = "\n".join(session_lines)
    path = save_session(session_content, f"{ts}_pitch")
    print(f"[比稿] 保存至 {path}", flush=True)

    send_planner_card(
        "🏆 比稿完成",
        f"**课题：**{topic[:200]}\n"
        f"**参赛：**{', '.join(a.emoji + ' ' + a.name for a in agencies)}\n\n"
        f"完整内容已保存至 `{path}`\n\n"
        f"💬 私聊 planner bot 可追问比稿内容或生成文档",
        color="green",
    )

    # 构造与 Planner 兼容的 planning_outputs 格式
    planning_outputs: list[tuple[int, str, str]] = []
    planning_outputs.append((1, "Brief 结构化", brief))
    for i, (ag, prop) in enumerate(proposals, 2):
        planning_outputs.append((i, f"{ag.name}提案", truncate_for_display(prop)))
    critique_step = len(proposals) + 2
    for i, (ag, crit) in enumerate(critiques):
        planning_outputs.append((critique_step + i, f"{ag.name}点评", truncate_for_display(crit)))
    verdict_step = critique_step + len(critiques)
    planning_outputs.append((verdict_step, "裁决与融合", truncate_for_display(verdict)))

    pitch_data = {
        "agencies": agencies,
        "proposals": proposals,
        "critiques": critiques,
        "verdict": verdict,
    }

    print("\n========== 比稿结束 ==========", flush=True)
    return str(path), planning_outputs, pitch_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Agency 比稿 AI 引擎")
    parser.add_argument("--topic", required=True, help="比稿课题")
    parser.add_argument("--context", default="", help="背景材料")
    args = parser.parse_args()
    path, _, _ = run_pitch(
        topic=args.topic.strip(),
        context=load_context(args.context or ""),
    )


if __name__ == "__main__":
    main()
