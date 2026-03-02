# -*- coding: utf-8 -*-
"""
作用域路由 — 判断用户意图应走「团队」还是「个人」通道。

核心逻辑：
  1. 操作类型天然决定默认作用域（项目/预算→团队，备忘/日程→个人）
  2. 用户可用关键词显式覆盖（"帮团队记…" / "我自己的项目…"）
  3. 消息中提到团队名时自动切换当前团队

使用方式：
  from core.scope import resolve_scope
  scope = resolve_scope(user_text, open_id, action=action)
  # scope.is_team / scope.team_code / scope.team / ...
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.team import (
    get_current_team,
    get_user_profile,
    resolve_team_by_name,
    switch_team,
)

# ═══════════════════════════════════════════════════════════════
#  作用域结果
# ═══════════════════════════════════════════════════════════════

@dataclass
class Scope:
    """一次请求的作用域解析结果。"""
    kind: str                                   # "team" | "personal"
    open_id: str                                # 发消息的用户
    team_code: str = ""                         # 团队码（kind=="team" 时有值）
    team: Optional[Dict[str, Any]] = field(default=None, repr=False)
    reason: str = ""                            # 为什么是这个 scope（调试用）

    @property
    def is_team(self) -> bool:
        return self.kind == "team"

    @property
    def is_personal(self) -> bool:
        return self.kind == "personal"


# ═══════════════════════════════════════════════════════════════
#  默认作用域表
# ═══════════════════════════════════════════════════════════════

_TEAM_ACTIONS = {
    "project", "add_task", "list_tasks", "create_project", "import_project",
    "budget", "create_budget", "budget_overview",
    "expense", "add_expense", "month_expenses", "month_summary",
    "asset", "add_asset", "asset_stats",
    "content", "create_content", "list_content", "publish",
    "board", "create_board", "export_board",
    "team_brainstorm", "team_plan",
}

_PERSONAL_ACTIONS = {
    "memo", "add_memo", "list_memo", "complete_memo", "delete_memo",
    "calendar", "add_event", "list_events",
    "reminder", "set_reminder",
    "research",
    "sentiment",
    "creative",
    "chat",
}

# 用户显式覆盖关键词
_TEAM_OVERRIDE_RE = re.compile(
    r"(?:帮?团队|团队的|共享|项目(?:表|组)|预算表|素材表|内容日历)",
)
_PERSONAL_OVERRIDE_RE = re.compile(
    r"(?:我自己的?|我个人的?|私人的?|只给我)",
)
_TEAM_NAME_RE = re.compile(
    r"(?:切换到|切到|去|switch\s+to)\s*[「「\"]?(.+?)[」」\"]?\s*(?:团队)?$",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def resolve_scope(
    user_text: str,
    open_id: str,
    action: str = "",
) -> Scope:
    """
    综合判断本次请求的作用域。

    优先级（从高到低）：
      1. 用户显式关键词（"帮团队…" / "我自己的…"）
      2. 消息中提到团队名 → 自动切换
      3. action 在 _TEAM_ACTIONS / _PERSONAL_ACTIONS 中的默认值
      4. 兜底：有团队走团队，无团队走个人
    """
    text = (user_text or "").strip()

    # ── 1. 显式覆盖 ──────────────────────────────────────────
    if _PERSONAL_OVERRIDE_RE.search(text):
        return Scope(kind="personal", open_id=open_id, reason="用户显式指定个人")

    if _TEAM_OVERRIDE_RE.search(text):
        team = get_current_team(open_id)
        if team:
            return Scope(
                kind="team", open_id=open_id,
                team_code=team["code"], team=team,
                reason="用户显式指定团队",
            )

    # ── 2. 团队名切换 ────────────────────────────────────────
    m = _TEAM_NAME_RE.search(text)
    if m:
        hint = m.group(1).strip()
        matched = resolve_team_by_name(open_id, hint)
        if matched:
            switch_team(open_id, matched["code"])
            return Scope(
                kind="team", open_id=open_id,
                team_code=matched["code"], team=matched,
                reason=f"匹配到团队「{matched['name']}」并切换",
            )

    # ── 3. action 默认表 ─────────────────────────────────────
    action_lower = action.lower().strip()
    if action_lower in _TEAM_ACTIONS:
        team = get_current_team(open_id)
        if team:
            return Scope(
                kind="team", open_id=open_id,
                team_code=team["code"], team=team,
                reason=f"action={action_lower} 默认走团队",
            )
        return Scope(
            kind="personal", open_id=open_id,
            reason=f"action={action_lower} 应走团队但用户无团队，降级为个人",
        )

    if action_lower in _PERSONAL_ACTIONS:
        return Scope(kind="personal", open_id=open_id, reason=f"action={action_lower} 默认走个人")

    # ── 4. 兜底 ──────────────────────────────────────────────
    team = get_current_team(open_id)
    if team:
        return Scope(
            kind="team", open_id=open_id,
            team_code=team["code"], team=team,
            reason="兜底：用户有团队，默认走团队",
        )
    return Scope(kind="personal", open_id=open_id, reason="兜底：用户无团队")


# ═══════════════════════════════════════════════════════════════
#  便捷函数
# ═══════════════════════════════════════════════════════════════

def is_team_action(action: str) -> bool:
    """判断某个 action 是否默认走团队作用域。"""
    return action.lower().strip() in _TEAM_ACTIONS


def is_personal_action(action: str) -> bool:
    """判断某个 action 是否默认走个人作用域。"""
    return action.lower().strip() in _PERSONAL_ACTIONS
