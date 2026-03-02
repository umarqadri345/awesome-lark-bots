# -*- coding: utf-8 -*-
"""
creative/asset_tracker.py — 素材需求管理

维护素材执行需求的全生命周期：
- 一张飞书电子表格作为管理总表（含「总表」tab + 按月 tab）
- 提交需求时同时写入总表和当月 tab
- 与 assistant 项目管理表轻量同步

存储路径：data/creative_assets.json
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_CONFIG_PATH = str(Path(__file__).resolve().parent.parent / "data" / "creative_assets.json")
_lock = threading.Lock()

ASSET_HEADERS = [
    "需求编号", "品牌", "创意概念", "素材类型", "渠道",
    "执行方", "预算", "截止日期", "状态", "Brief链接",
    "提交人", "提交日期",
]


# ── 配置持久化 ────────────────────────────────────────────────

def _load_config() -> Dict[str, Any]:
    if not os.path.exists(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_config(cfg: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _next_id() -> str:
    """生成下一个需求编号，如 CR-001。"""
    with _lock:
        cfg = _load_config()
        seq = cfg.get("next_seq", 1)
        cfg["next_seq"] = seq + 1
        _save_config(cfg)
    return f"CR-{seq:03d}"


def _month_key(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now()).strftime("%Y-%m")


def _month_tab_title(key: str) -> str:
    y, m = key.split("-")
    return f"{y}年{int(m)}月"


# ── 总表初始化 ────────────────────────────────────────────────

def init_master_sheet(owner_open_id: Optional[str] = None) -> Tuple[bool, str]:
    """创建素材需求管理总表（首次使用时自动调用）。"""
    from core.feishu_client import create_spreadsheet_detail, write_sheet_header, add_sheet_tab

    with _lock:
        cfg = _load_config()
        if cfg.get("spreadsheet_token"):
            return True, cfg.get("url", "")

    ok, detail = create_spreadsheet_detail(
        title="📋 素材需求管理表",
        headers=ASSET_HEADERS,
        rows=[],
        owner_open_id=owner_open_id,
        theme="indigo",
    )
    if not ok:
        return False, str(detail)

    ss_token = detail["spreadsheet_token"]
    master_sid = detail["sheet_id"]
    url = detail["url"]

    mk = _month_key()
    tab_ok, monthly_sid = add_sheet_tab(ss_token, _month_tab_title(mk), index=1)
    if tab_ok:
        write_sheet_header(ss_token, monthly_sid, ASSET_HEADERS, theme="green")

    with _lock:
        cfg = _load_config()
        cfg.update({
            "spreadsheet_token": ss_token,
            "master_sheet_id": master_sid,
            "url": url,
            "monthly_sheets": {mk: monthly_sid} if tab_ok else {},
            "next_seq": cfg.get("next_seq", 1),
        })
        _save_config(cfg)
    return True, url


# ── 月度 tab ──────────────────────────────────────────────────

def _ensure_monthly_tab() -> Tuple[str, str]:
    """确保当月 tab 存在，返回 (spreadsheet_token, sheet_id)。"""
    from core.feishu_client import add_sheet_tab, write_sheet_header

    mk = _month_key()
    with _lock:
        cfg = _load_config()
        ss_token = cfg.get("spreadsheet_token", "")
        monthly = cfg.get("monthly_sheets", {})
        if mk in monthly:
            return ss_token, monthly[mk]

    if not ss_token:
        ok, _ = init_master_sheet()
        if not ok:
            return "", ""
        cfg = _load_config()
        ss_token = cfg.get("spreadsheet_token", "")
        monthly = cfg.get("monthly_sheets", {})
        if mk in monthly:
            return ss_token, monthly[mk]

    tab_ok, sid = add_sheet_tab(ss_token, _month_tab_title(mk))
    if tab_ok:
        write_sheet_header(ss_token, sid, ASSET_HEADERS, theme="green")
        with _lock:
            cfg = _load_config()
            cfg.setdefault("monthly_sheets", {})[mk] = sid
            _save_config(cfg)
        return ss_token, sid
    return ss_token, ""


# ── 提交需求 ──────────────────────────────────────────────────

def submit_asset_request(
    info: Dict[str, str],
    brief_url: str = "",
    owner_open_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """提交一条素材需求到管理表。返回 (ok, req_id_or_error)。

    info keys: brand, concept, asset_type, channel, executor, budget, deadline, contact, submitter
    """
    from core.feishu_client import append_spreadsheet_rows

    cfg = _load_config()
    ss_token = cfg.get("spreadsheet_token", "")
    master_sid = cfg.get("master_sheet_id", "")

    if not ss_token or not master_sid:
        ok, url = init_master_sheet(owner_open_id)
        if not ok:
            return False, f"创建管理表失败: {url}"
        cfg = _load_config()
        ss_token = cfg["spreadsheet_token"]
        master_sid = cfg["master_sheet_id"]

    req_id = _next_id()
    now = datetime.now()
    row = [
        req_id,
        info.get("brand", "待确认"),
        info.get("concept", ""),
        info.get("asset_type", "待确认"),
        info.get("channel", "待确认"),
        info.get("executor", "待确认"),
        info.get("budget", "待确认"),
        info.get("deadline", "待确认"),
        "待分配",
        brief_url,
        info.get("submitter", ""),
        now.strftime("%Y-%m-%d"),
    ]

    ok1, msg1 = append_spreadsheet_rows(ss_token, master_sid, [row])
    if not ok1:
        return False, f"写入总表失败: {msg1}"

    _, monthly_sid = _ensure_monthly_tab()
    if monthly_sid:
        append_spreadsheet_rows(ss_token, monthly_sid, [row])

    return True, req_id


# ── 月度统计 ──────────────────────────────────────────────────

def get_monthly_stats(month: Optional[str] = None) -> Dict[str, Any]:
    """获取当月（或指定月）素材需求统计。"""
    from core.feishu_client import read_spreadsheet_values

    mk = month or _month_key()
    cfg = _load_config()
    ss_token = cfg.get("spreadsheet_token", "")
    monthly = cfg.get("monthly_sheets", {})
    sid = monthly.get(mk, "")

    if not ss_token or not sid:
        return {"total": 0, "by_status": {}, "month": mk}

    ok, values = read_spreadsheet_values(ss_token, f"{sid}!A2:L200")
    if not ok or not values:
        return {"total": 0, "by_status": {}, "month": mk}

    by_status: Dict[str, int] = {}
    for row in values:
        if len(row) > 0 and row[0]:
            status = str(row[8]) if len(row) > 8 else "未知"
            by_status[status] = by_status.get(status, 0) + 1

    return {"total": sum(by_status.values()), "by_status": by_status, "month": mk}


def get_management_table_url() -> str:
    """获取素材需求管理表的 URL。"""
    return _load_config().get("url", "")


# ── 与 assistant 项目表同步 ───────────────────────────────────

def sync_to_assistant(info: Dict[str, str], brief_url: str = "") -> Tuple[bool, str]:
    """将素材需求同步到 assistant 的项目管理表（轻量链接）。"""
    try:
        from memo.projects import find_project, register_project, PROJECT_HEADERS
        from core.feishu_client import append_spreadsheet_rows, create_spreadsheet_detail

        project = find_project("素材需求跟踪")
        if not project:
            ok, detail = create_spreadsheet_detail(
                title="📋 素材需求跟踪",
                headers=PROJECT_HEADERS,
                rows=[],
                theme="green",
            )
            if not ok:
                return False, f"创建项目表失败: {detail}"
            register_project(
                name="素材需求跟踪",
                spreadsheet_token=detail["spreadsheet_token"],
                sheet_id=detail["sheet_id"],
                url=detail["url"],
                source="creative",
                doc_type="素材跟踪",
            )
            project = find_project("素材需求跟踪")
            if not project:
                return False, "注册项目失败"

        stats = get_monthly_stats()
        total = stats["total"]
        completed = stats["by_status"].get("已完成", 0)
        summary = f"本月素材需求 {total} 条"
        if total > 0:
            summary += f"，已完成 {completed} 条（{completed * 100 // total}%）"

        concept = info.get("concept", "素材需求")
        row = [
            f"素材需求：{concept[:30]}",
            "creative bot",
            info.get("contact", ""),
            "进行中",
            "中",
            info.get("deadline", ""),
            summary,
        ]

        return append_spreadsheet_rows(
            project["spreadsheet_token"],
            project["sheet_id"],
            [row],
        )
    except Exception as e:
        return False, f"同步失败: {e}"
