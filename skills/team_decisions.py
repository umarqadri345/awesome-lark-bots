# -*- coding: utf-8 -*-
"""
团队判断力沉淀 — 记录并复用团队在各 bot 中做出的重要决策和偏好。

核心理念：
  判断力是团队最稀缺的资源。一个人说过的判断（"这种风格太硬了"、"我们的受众偏年轻"、
  "方向A被否了因为太像竞品"），不应该消失在聊天记录里，而应该被系统记住，
  自动注入到后续所有 bot 的 LLM prompt 中。

存储：data/team_decisions.jsonl（按行追加 JSON，轻量持久化）

写入（各 bot 调用）：
  >>> from skills.team_decisions import record_decision
  >>> record_decision("brand_tone", "文案要口语化，不要营销腔", source="conductor")

读取（skill_router 自动注入）：
  通过 Skill 接口注册，skill_router 会在所有 bot 的 prompt 中自动注入最近的团队决策。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from skills import Skill, register

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DECISIONS_FILE = _DATA_DIR / "team_decisions.jsonl"
_write_lock = threading.Lock()

CATEGORIES = {
    "brand_tone": "品牌调性与风格偏好",
    "audience": "目标受众认知",
    "content_pref": "内容偏好（什么管用/什么不管用）",
    "rejected": "被否决的方向及原因",
    "strategy": "战略判断与取舍",
    "process": "流程与协作偏好",
    "other": "其他判断",
}


def record_decision(
    category: str,
    decision: str,
    *,
    source: str = "",
    user_id: str = "",
    context: str = "",
) -> bool:
    """记录一条团队决策。各 bot 在识别到用户做出判断时调用。"""
    if not decision or not decision.strip():
        return False
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "category": category if category in CATEGORIES else "other",
        "decision": decision.strip()[:500],
        "source": source,
    }
    if user_id:
        record["user_id"] = user_id
    if context:
        record["context"] = context[:200]
    try:
        with _write_lock:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_DECISIONS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def get_recent_decisions(limit: int = 20, category: str = "") -> list[dict]:
    """读取最近的团队决策。"""
    if not _DECISIONS_FILE.exists():
        return []
    try:
        lines = _DECISIONS_FILE.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if category and rec.get("category") != category:
                    continue
                records.append(rec)
                if len(records) >= limit:
                    break
            except json.JSONDecodeError:
                continue
        return records
    except Exception:
        return []


def format_decisions_for_prompt(limit: int = 15) -> str:
    """将最近决策格式化为可注入 LLM prompt 的文本。"""
    decisions = get_recent_decisions(limit=limit)
    if not decisions:
        return ""
    lines = ["以下是团队之前做出的重要判断和偏好，请在回复中遵循这些决策：\n"]
    for d in decisions:
        cat_label = CATEGORIES.get(d.get("category", ""), "其他")
        source = d.get("source", "")
        source_tag = f" ({source})" if source else ""
        lines.append(f"- [{cat_label}]{source_tag} {d['decision']}")
    return "\n".join(lines)


class TeamDecisionsSkill(Skill):
    """团队判断力沉淀技能 — 所有 bot 自动获得团队历史决策上下文。"""

    name = "team_decisions"
    description = "团队历史决策与偏好（自动注入）"
    bot_types = ["brainstorm", "conductor", "creative", "planner", "assistant"]

    def get_context(self, **kwargs) -> str:
        return format_decisions_for_prompt(limit=15)

    def should_activate(self, user_text: str = "", bot_type: str = "", **kwargs) -> bool:
        if bot_type in self.bot_types:
            decisions = get_recent_decisions(limit=1)
            return len(decisions) > 0
        return False


    def as_tool(self):
        from core.agent import ToolDef

        def _query(category: str = "") -> str:
            decisions = get_recent_decisions(limit=15, category=category)
            if not decisions:
                return "暂无团队决策记录。"
            lines = []
            for d in decisions:
                cat = CATEGORIES.get(d.get("category", ""), "其他")
                lines.append(f"- [{cat}] {d['decision']}")
            return "\n".join(lines)

        return ToolDef(
            name="get_team_decisions",
            description="查询团队历史决策和偏好，如品牌调性、被否决的方向、受众认知等。",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string",
                                 "description": "筛选类别：brand_tone/audience/content_pref/rejected/strategy/process。留空查全部。"},
                },
            },
            fn=_query,
        )


register(TeamDecisionsSkill())
