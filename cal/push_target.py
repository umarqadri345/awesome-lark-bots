# -*- coding: utf-8 -*-
"""定时推送接收人管理：优先 FEISHU_PUSH_OPEN_ID，否则用最近发过消息的人。"""
import os
from pathlib import Path

_FILE = str(Path(__file__).resolve().parent.parent / "data" / "push_target_open_id.txt")


def save_push_target_open_id(open_id: str) -> None:
    if not open_id or not open_id.strip():
        return
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            f.write(open_id.strip())
    except Exception:
        pass


def get_push_target_open_id() -> str:
    v = (os.environ.get("FEISHU_PUSH_OPEN_ID") or "").strip()
    if v:
        return v
    try:
        if os.path.isfile(_FILE):
            with open(_FILE, "r", encoding="utf-8") as f:
                return (f.read() or "").strip()
    except Exception:
        pass
    return ""
