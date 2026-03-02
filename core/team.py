# -*- coding: utf-8 -*-
"""
团队管理 — 团队码创建 / 加入 / 离开 / 查询 / 资源绑定。

存储结构：
  data/teams/{team_code}.json    — 团队配置（成员、绑定的飞书表格等）
  data/user_profiles/{open_id}.json — 用户档案（所属团队列表、当前团队）

设计原则：
  - 扁平结构，团队之间互相独立
  - 一个用户可加入多个团队，有"当前团队"概念
  - 未加入团队的用户 = 单人模式，完全向下兼容
  - 团队码为 6 位大写字母数字，可读性好、便于口头分享
"""
import json
import os
import random
import string
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TEAMS_DIR = _DATA_DIR / "teams"
_PROFILES_DIR = _DATA_DIR / "user_profiles"
_lock = threading.Lock()

_CODE_LENGTH = 6
_CODE_CHARS = string.ascii_uppercase + string.digits


# ═══════════════════════════════════════════════════════════════
#  内部 IO
# ═══════════════════════════════════════════════════════════════

def _ensure_dirs() -> None:
    _TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _team_path(code: str) -> Path:
    return _TEAMS_DIR / f"{code}.json"


def _profile_path(open_id: str) -> Path:
    return _PROFILES_DIR / f"{open_id}.json"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_code() -> str:
    """生成一个不重复的团队码。"""
    for _ in range(100):
        code = "".join(random.choices(_CODE_CHARS, k=_CODE_LENGTH))
        if not _team_path(code).exists():
            return code
    raise RuntimeError("无法生成唯一团队码，请重试")


# ═══════════════════════════════════════════════════════════════
#  团队 CRUD
# ═══════════════════════════════════════════════════════════════

def create_team(
    name: str,
    owner_open_id: str,
    description: str = "",
) -> Tuple[bool, Dict[str, Any]]:
    """创建团队，返回 (ok, team_dict)。自动将创建者加入团队。"""
    name = name.strip()
    if not name:
        return False, {"error": "团队名不能为空"}

    with _lock:
        _ensure_dirs()
        code = _generate_code()
        team = {
            "code": code,
            "name": name,
            "description": description,
            "owner": owner_open_id,
            "members": [owner_open_id],
            "bindings": {},
            "created_at": _now_iso(),
        }
        _write_json(_team_path(code), team)
        _add_team_to_profile(owner_open_id, code, set_current=True)
    return True, team


def get_team(code: str) -> Optional[Dict[str, Any]]:
    """按团队码查询团队信息。"""
    return _read_json(_team_path(code.upper().strip()))


def list_all_teams() -> List[Dict[str, Any]]:
    """列出所有团队（管理用途）。"""
    _ensure_dirs()
    teams = []
    for f in _TEAMS_DIR.glob("*.json"):
        t = _read_json(f)
        if t:
            teams.append(t)
    return sorted(teams, key=lambda t: t.get("created_at", ""))


def update_team(code: str, **updates: Any) -> Tuple[bool, str]:
    """更新团队属性（name / description）。"""
    with _lock:
        team = _read_json(_team_path(code))
        if not team:
            return False, "团队不存在"
        for key in ("name", "description"):
            if key in updates and updates[key] is not None:
                team[key] = updates[key]
        _write_json(_team_path(code), team)
    return True, "已更新"


def delete_team(code: str, requester_open_id: str) -> Tuple[bool, str]:
    """解散团队（仅 owner 可操作）。"""
    with _lock:
        team = _read_json(_team_path(code))
        if not team:
            return False, "团队不存在"
        if team["owner"] != requester_open_id:
            return False, "只有团队创建者可以解散团队"
        for member_id in team["members"]:
            _remove_team_from_profile(member_id, code)
        try:
            _team_path(code).unlink()
        except OSError:
            pass
    return True, f"团队「{team['name']}」已解散"


# ═══════════════════════════════════════════════════════════════
#  成员管理
# ═══════════════════════════════════════════════════════════════

def join_team(code: str, open_id: str) -> Tuple[bool, str]:
    """用团队码加入团队。"""
    code = code.upper().strip()
    with _lock:
        team = _read_json(_team_path(code))
        if not team:
            return False, "团队码无效，请检查后重试"
        if open_id in team["members"]:
            return True, f"你已经在「{team['name']}」团队中了"
        team["members"].append(open_id)
        _write_json(_team_path(code), team)
        _add_team_to_profile(open_id, code, set_current=True)
    return True, f"已加入「{team['name']}」团队（共 {len(team['members'])} 人）"


def leave_team(code: str, open_id: str) -> Tuple[bool, str]:
    """离开团队。Owner 不可离开（需先转让或解散）。"""
    code = code.upper().strip()
    with _lock:
        team = _read_json(_team_path(code))
        if not team:
            return False, "团队不存在"
        if open_id not in team["members"]:
            return False, "你不在这个团队中"
        if team["owner"] == open_id:
            return False, "团队创建者不能离开，请先转让所有权或解散团队"
        team["members"].remove(open_id)
        _write_json(_team_path(code), team)
        _remove_team_from_profile(open_id, code)
    return True, f"已离开「{team['name']}」团队"


def list_members(code: str) -> List[str]:
    """返回团队成员 open_id 列表。"""
    team = get_team(code)
    return team["members"] if team else []


# ═══════════════════════════════════════════════════════════════
#  资源绑定（飞书表格等）
# ═══════════════════════════════════════════════════════════════

def bind_resource(
    code: str,
    resource_type: str,
    token: str,
    sheet_id: str = "",
    url: str = "",
) -> Tuple[bool, str]:
    """
    绑定团队共享资源。

    resource_type 例如: "project_sheet", "budget_sheet", "asset_sheet", "content_sheet"
    """
    with _lock:
        team = _read_json(_team_path(code))
        if not team:
            return False, "团队不存在"
        team["bindings"][resource_type] = {
            "token": token,
            "sheet_id": sheet_id,
            "url": url,
            "bound_at": _now_iso(),
        }
        _write_json(_team_path(code), team)
    return True, f"已绑定 {resource_type}"


def get_binding(code: str, resource_type: str) -> Optional[Dict[str, str]]:
    """获取团队绑定的某类资源信息。"""
    team = get_team(code)
    if not team:
        return None
    return team.get("bindings", {}).get(resource_type)


# ═══════════════════════════════════════════════════════════════
#  用户档案
# ═══════════════════════════════════════════════════════════════

def get_user_profile(open_id: str) -> Dict[str, Any]:
    """获取用户档案，不存在则返回默认空档案。"""
    profile = _read_json(_profile_path(open_id))
    if profile:
        return profile
    return {"open_id": open_id, "current_team": "", "teams": []}


def get_current_team(open_id: str) -> Optional[Dict[str, Any]]:
    """获取用户当前所在团队的完整信息。无团队返回 None。"""
    profile = get_user_profile(open_id)
    code = profile.get("current_team", "")
    if not code:
        return None
    return get_team(code)


def switch_team(open_id: str, code: str) -> Tuple[bool, str]:
    """切换用户的当前团队。"""
    code = code.upper().strip()
    profile = get_user_profile(open_id)
    if code not in profile.get("teams", []):
        return False, "你不在这个团队中，请先加入"
    team = get_team(code)
    if not team:
        return False, "团队不存在"
    with _lock:
        profile["current_team"] = code
        _write_json(_profile_path(open_id), profile)
    return True, f"已切换到「{team['name']}」团队"


def get_user_teams(open_id: str) -> List[Dict[str, Any]]:
    """列出用户所属的所有团队。"""
    profile = get_user_profile(open_id)
    teams = []
    for code in profile.get("teams", []):
        t = get_team(code)
        if t:
            teams.append(t)
    return teams


def resolve_team_by_name(open_id: str, name_hint: str) -> Optional[Dict[str, Any]]:
    """根据名称片段在用户的团队中模糊匹配。"""
    name_hint = name_hint.strip().lower()
    if not name_hint:
        return None
    for t in get_user_teams(open_id):
        if name_hint in t["name"].lower():
            return t
    return None


# ═══════════════════════════════════════════════════════════════
#  内部辅助
# ═══════════════════════════════════════════════════════════════

def _add_team_to_profile(open_id: str, code: str, set_current: bool = False) -> None:
    """将团队加入用户档案（调用方需持有 _lock）。"""
    _ensure_dirs()
    profile = _read_json(_profile_path(open_id)) or {
        "open_id": open_id, "current_team": "", "teams": [],
    }
    if code not in profile["teams"]:
        profile["teams"].append(code)
    if set_current or not profile.get("current_team"):
        profile["current_team"] = code
    _write_json(_profile_path(open_id), profile)


def _remove_team_from_profile(open_id: str, code: str) -> None:
    """从用户档案中移除团队（调用方需持有 _lock）。"""
    profile = _read_json(_profile_path(open_id))
    if not profile:
        return
    if code in profile.get("teams", []):
        profile["teams"].remove(code)
    if profile.get("current_team") == code:
        profile["current_team"] = profile["teams"][0] if profile["teams"] else ""
    _write_json(_profile_path(open_id), profile)
