# -*- coding: utf-8 -*-
"""每日简报与收尾：定时拉取日程+备忘，由 DeepSeek 生成简报并推送到飞书单聊。"""
import sys
from typing import List

from core.llm import chat


def _format_events(events: List[dict]) -> str:
    if not events:
        return "（无）"
    lines = []
    for e in events:
        s = (e.get("summary") or "(无标题)").strip()
        start = e.get("start") or ""
        end = e.get("end") or ""
        if isinstance(start, dict):
            start = str(start.get("timestamp", ""))
        if isinstance(end, dict):
            end = str(end.get("timestamp", ""))
        lines.append(f"  - {s}  {start}～{end}")
    return "\n".join(lines)


def _format_memos(memos: List[dict]) -> str:
    if not memos:
        return "（无）"
    return "\n".join([f"  - {m.get('content', '')}" for m in memos])


def generate_daily_brief(
    events_feishu: List[dict],
    events_google: List[dict],
    memos: List[dict],
    date_str: str,
    is_morning: bool = True,
) -> str:
    events_all = []
    for e in events_feishu + events_google:
        events_all.append({"summary": e.get("summary"), "start": e.get("start"), "end": e.get("end")})

    events_text = _format_events(events_all)
    memos_text = _format_memos(memos)

    if is_morning:
        prompt = f"""你是我的工作助手，请根据以下信息生成今日工作简报。风格：简洁、有重点、像一个靠谱的助手在帮我整理思路。

【今日日历事件】
{events_text}

【最近备忘】
{memos_text}

请输出：
1. 今日日程（列出所有日历事件，标注时间）
2. 今日重点（从备忘+日程中提炼，最多3条）
3. 需要注意（冲突、截止日临近、空白时间段等）
4. 一句话建议（今天的工作节奏建议）

语言：中文，不要使用 Markdown 加粗，纯文本。"""
    else:
        prompt = f"""你是我的工作助手，请根据以下信息生成今日收尾 checklist。风格：简洁。

【今日日历事件】
{events_text}

【最近备忘】
{memos_text}

请输出：
1. 今日已完成/未完成事项简要
2. 明日可提前准备的事项（最多3条）
3. 一句话收尾建议

语言：中文，简洁，不要 Markdown 加粗。"""

    return chat(prompt, system_prompt="你是日程与任务助手，输出简洁、可执行的文本。")


def run_daily_brief(is_morning: bool = True) -> bool:
    """执行一次每日简报推送。"""
    from cal.push_target import get_push_target_open_id
    open_id = get_push_target_open_id()
    if not open_id:
        return False

    from cal.aggregator import aggregate_for_date
    from memo.store import list_memos
    from core.feishu_client import send_message_to_user

    agg = aggregate_for_date("today", user_open_id=open_id)
    events_feishu = agg.get("feishu_events") or []
    events_google = agg.get("google_events") or []
    memos = list_memos(limit=10, user_open_id=open_id)
    date_str = agg.get("date", "")

    try:
        brief = generate_daily_brief(events_feishu, events_google, memos, date_str, is_morning=is_morning)
        if not brief:
            brief = "今日暂无日程与备忘汇总。"
        if len(brief) > 4000:
            brief = brief[:3997] + "..."
        send_message_to_user(open_id, brief)
        return True
    except Exception as e:
        print(f"[DailyBrief] 生成或推送失败: {e}", file=sys.stderr, flush=True)
        return False
