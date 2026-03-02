# -*- coding: utf-8 -*-
"""
线程看板注册表：保存已创建的飞书电子表格看板信息，支持自动追加更新。
存储路径：data/boards.json
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_PATH = str(Path(__file__).resolve().parent.parent / "data" / "boards.json")
_lock = threading.Lock()


def _path() -> str:
    return (os.environ.get("BOARD_STORE_PATH") or "").strip() or _DEFAULT_PATH


def _load() -> List[Dict[str, Any]]:
    p = _path()
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def register_board(
    thread: str,
    spreadsheet_token: str,
    sheet_id: str,
    url: str,
    user_open_id: str = "",
) -> Dict[str, Any]:
    """注册或更新一个线程的看板信息。同一线程只保留一条记录。"""
    thread_key = thread.strip().lstrip("#").lower()
    entry = {
        "thread": thread.strip().lstrip("#"),
        "thread_key": thread_key,
        "spreadsheet_token": spreadsheet_token,
        "sheet_id": sheet_id,
        "url": url,
        "user_open_id": user_open_id,
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with _lock:
        items = _load()
        items = [b for b in items if b.get("thread_key") != thread_key]
        items.append(entry)
        _save(items)
    return entry


def find_board(thread: str) -> Optional[Dict[str, Any]]:
    """按线程名查找已注册的看板。"""
    thread_key = thread.strip().lstrip("#").lower()
    with _lock:
        items = _load()
    for b in items:
        if b.get("thread_key") == thread_key:
            return b
    return None


def list_boards() -> List[Dict[str, Any]]:
    """列出所有已注册的看板。"""
    with _lock:
        return _load()
