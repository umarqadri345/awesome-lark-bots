# -*- coding: utf-8 -*-
"""
conductor/bitable_sync.py — 内容草稿同步至飞书多维表格。

将 ContentItem 同步到飞书 Bitable，使本地 Claude 定时任务可以通过
Bitable API 读取待发布内容、更新发布状态。

Bitable 表结构:
  content_id | 标题 | 话题 | 品牌 | 平台文案 | 话题标签 | 目标平台
  | 状态 | 定时发布时间 | 素材链接 | 发布URL | 质量分

配置持久化: data/bitable_conductor.json
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_CONFIG_PATH = str(Path(__file__).resolve().parent.parent / "data" / "bitable_conductor.json")
_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[BitableSync] {msg}", file=sys.stderr, flush=True)


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


# ── 表定义 ────────────────────────────────────────────────────

TABLE_FIELDS = [
    {"field_name": "content_id", "type": 1},
    {"field_name": "标题", "type": 1},
    {"field_name": "话题", "type": 1},
    {"field_name": "品牌", "type": 1},
    {"field_name": "内容类型", "type": 1},            # xhs_note / short_video / image_post / article
    {"field_name": "平台文案", "type": 1},          # JSON string: {platform: copy}
    {"field_name": "话题标签", "type": 1},            # 逗号分隔
    {"field_name": "目标平台", "type": 1},            # 逗号分隔
    {"field_name": "素材链接", "type": 1},            # JSON string: [url, ...]
    {"field_name": "状态", "type": 3, "property": {"options": [
        {"name": "draft"}, {"name": "ready"},
        {"name": "scheduled"}, {"name": "published"}, {"name": "failed"},
    ]}},
    {"field_name": "质量分", "type": 2},
    {"field_name": "定时发布时间", "type": 1},         # ISO datetime string
    {"field_name": "发布URL", "type": 1},             # JSON string: {platform: url}
    {"field_name": "发布错误", "type": 1},             # JSON string: {platform: error}
    {"field_name": "创建时间", "type": 1},
]


# ── Bitable 初始化 ────────────────────────────────────────────

def _enabled() -> bool:
    """检查是否启用 Bitable 同步。默认启用，设 CONDUCTOR_BITABLE_SYNC=false 可关闭。"""
    return os.getenv("CONDUCTOR_BITABLE_SYNC", "true").lower() in ("1", "true", "yes")


def ensure_table() -> Tuple[bool, str]:
    """确保 Bitable 应用和内容草稿表已创建。返回 (ok, url_or_error)。"""
    from core.feishu_client import create_bitable, create_bitable_table

    cfg = _load_config()
    if cfg.get("app_token") and cfg.get("table_id"):
        return True, cfg.get("url", "")

    ok, result = create_bitable("📝 内容发布中心")
    if not ok:
        err = result.get("error", "创建失败") if isinstance(result, dict) else str(result)
        _log(f"创建 Bitable 失败: {err}")
        return False, err

    app_token = result["app_token"]
    url = result["url"]

    tok, tid = create_bitable_table(
        app_token, "内容草稿", TABLE_FIELDS,
        default_view_name="全部内容",
    )
    if not tok:
        _log(f"创建表失败: {tid}")
        return False, f"创建表失败: {tid}"

    new_cfg = {"app_token": app_token, "table_id": tid, "url": url}
    with _lock:
        _save_config(new_cfg)

    _log(f"内容发布中心已创建: {url}")
    return True, url


def get_table_info() -> Tuple[str, str]:
    """返回 (app_token, table_id)。"""
    cfg = _load_config()
    return cfg.get("app_token", ""), cfg.get("table_id", "")


# ── 同步写入 ────────────────────────────────────────────────

def _item_to_fields(item) -> Dict[str, Any]:
    """将 ContentItem 转为 Bitable 记录字段。"""
    scheduled_str = ""
    if item.scheduled_at:
        try:
            scheduled_str = datetime.fromtimestamp(item.scheduled_at).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError):
            pass

    created_str = ""
    if item.created_at:
        try:
            created_str = datetime.fromtimestamp(item.created_at).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError):
            pass

    return {
        "content_id": item.content_id,
        "标题": item.title or "",
        "话题": item.topic or "",
        "品牌": item.brand or "",
        "内容类型": item.content_type or "",
        "平台文案": json.dumps(item.platform_copy, ensure_ascii=False) if item.platform_copy else "",
        "话题标签": ", ".join(item.hashtags) if item.hashtags else "",
        "目标平台": ", ".join(item.target_platforms) if item.target_platforms else "",
        "素材链接": json.dumps(item.generated_assets, ensure_ascii=False) if item.generated_assets else "",
        "状态": item.status or "draft",
        "质量分": round(item.quality_score, 2) if item.quality_score else 0,
        "定时发布时间": scheduled_str,
        "发布URL": json.dumps(item.publish_urls, ensure_ascii=False) if item.publish_urls else "",
        "发布错误": json.dumps(item.publish_errors, ensure_ascii=False) if item.publish_errors else "",
        "创建时间": created_str,
    }


def sync_to_bitable(item) -> bool:
    """将 ContentItem 同步到 Bitable。新记录则创建，已有则更新。

    调用时机：ContentStore.save() 之后。
    """
    if not _enabled():
        return False

    from core.feishu_client import (
        add_bitable_record, list_bitable_records, update_bitable_record,
    )

    app_token, table_id = get_table_info()
    if not app_token or not table_id:
        ok, _ = ensure_table()
        if not ok:
            return False
        app_token, table_id = get_table_info()

    fields = _item_to_fields(item)

    try:
        # 查找已有记录
        record_id = _find_record_id(app_token, table_id, item.content_id)

        if record_id:
            ok, _ = update_bitable_record(app_token, table_id, record_id, fields)
            if ok:
                _log(f"Bitable 已更新: {item.content_id} [{item.status}]")
            return ok
        else:
            ok, rid = add_bitable_record(app_token, table_id, fields)
            if ok:
                _log(f"Bitable 已写入: {item.content_id} [{item.status}] record={rid}")
            return ok
    except Exception as e:
        _log(f"Bitable 同步异常: {e}")
        return False


def _find_record_id(app_token: str, table_id: str, content_id: str) -> Optional[str]:
    """根据 content_id 查找 Bitable 记录 ID。"""
    from core.feishu_client import list_bitable_records

    filter_expr = f'CurrentValue.[content_id]="{content_id}"'
    ok, records = list_bitable_records(app_token, table_id, filter_expr=filter_expr, page_size=1)
    if ok and records:
        return records[0].get("record_id")
    return None


# ── 读取（供本地 Claude 使用） ────────────────────────────────

def list_ready_items() -> list[Dict[str, Any]]:
    """列出所有状态为 ready 的内容记录。"""
    from core.feishu_client import list_bitable_records

    app_token, table_id = get_table_info()
    if not app_token or not table_id:
        return []

    filter_expr = 'CurrentValue.[状态]="ready"'
    ok, records = list_bitable_records(app_token, table_id, filter_expr=filter_expr)
    if not ok:
        return []
    return records


def mark_published(content_id: str, platform: str, url: str = "") -> bool:
    """将 Bitable 中的记录标记为已发布。"""
    from core.feishu_client import update_bitable_record

    app_token, table_id = get_table_info()
    if not app_token or not table_id:
        return False

    record_id = _find_record_id(app_token, table_id, content_id)
    if not record_id:
        _log(f"未找到记录: {content_id}")
        return False

    fields: Dict[str, Any] = {"状态": "published"}
    if url:
        fields["发布URL"] = json.dumps({platform: url}, ensure_ascii=False)

    ok, _ = update_bitable_record(app_token, table_id, record_id, fields)
    if ok:
        _log(f"已标记发布: {content_id} [{platform}] {url}")
    return ok


def mark_failed(content_id: str, platform: str, error: str = "") -> bool:
    """将 Bitable 中的记录标记为发布失败。"""
    from core.feishu_client import update_bitable_record

    app_token, table_id = get_table_info()
    if not app_token or not table_id:
        return False

    record_id = _find_record_id(app_token, table_id, content_id)
    if not record_id:
        return False

    fields: Dict[str, Any] = {
        "状态": "failed",
        "发布错误": json.dumps({platform: error}, ensure_ascii=False),
    }
    ok, _ = update_bitable_record(app_token, table_id, record_id, fields)
    return ok
