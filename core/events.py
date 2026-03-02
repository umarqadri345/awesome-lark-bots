# -*- coding: utf-8 -*-
"""
轻量事件轨迹 — 各 bot 在关键节点写事件，助手 heartbeat 定期扫描。

存储：data/events/YYYY-MM-DD.jsonl（每天一个文件，按行追加 JSON）
设计：
  - 写入极简，一行 emit() 搞定
  - 扫描侧按时间窗口读取，支持增量
  - 事件不做清理策略，每天一个文件自然归档（30 天前的可手动删除）
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "events"
_write_lock = threading.Lock()

_BEIJING = timezone(timedelta(hours=8))


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _today_file() -> Path:
    return _DATA_DIR / f"{datetime.now(_BEIJING).strftime('%Y-%m-%d')}.jsonl"


# ═══════════════════════════════════════════════════════════════
#  写入侧（各 bot 调用）
# ═══════════════════════════════════════════════════════════════

def emit(
    bot: str,
    event: str,
    summary: str,
    *,
    user_id: str = "",
    team_code: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    写入一条事件。

    Args:
        bot:       来源 bot 名称 ("brainstorm" / "conductor" / "sentiment" / …)
        event:     事件类型 ("session_completed" / "content_published" / "alert" / …)
        summary:   人类可读的一句话摘要
        user_id:   触发用户的 open_id（可选）
        team_code: 关联的团队码（可选）
        meta:      结构化附加数据（可选）
    """
    record = {
        "ts": datetime.now(_BEIJING).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "bot": bot,
        "event": event,
        "summary": summary,
    }
    if user_id:
        record["user_id"] = user_id
    if team_code:
        record["team_code"] = team_code
    if meta:
        record["meta"] = meta

    try:
        with _write_lock:
            _ensure_dir()
            with open(_today_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("事件写入失败: %s", e)


# ═══════════════════════════════════════════════════════════════
#  读取侧（助手 heartbeat 调用）
# ═══════════════════════════════════════════════════════════════

def scan(
    hours: int = 24,
    bot: str = "",
    event: str = "",
    team_code: str = "",
    since_ts: str = "",
) -> List[Dict[str, Any]]:
    """
    扫描最近 N 小时的事件，支持过滤。

    Args:
        hours:     时间窗口（默认 24h）
        bot:       只看某个 bot 的事件
        event:     只看某种事件类型
        team_code: 只看某个团队的事件
        since_ts:  增量扫描——只返回此时间戳之后的事件（ISO 格式）

    Returns:
        事件列表（按时间正序）
    """
    _ensure_dir()
    now = datetime.now(_BEIJING)
    cutoff = now - timedelta(hours=hours)

    days_to_check = set()
    d = cutoff.date()
    while d <= now.date():
        days_to_check.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    results: List[Dict[str, Any]] = []
    for day_str in sorted(days_to_check):
        fpath = _DATA_DIR / f"{day_str}.jsonl"
        if not fpath.exists():
            continue
        try:
            for line in fpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if bot and rec.get("bot") != bot:
                    continue
                if event and rec.get("event") != event:
                    continue
                if team_code and rec.get("team_code") != team_code:
                    continue
                if since_ts and rec.get("ts", "") <= since_ts:
                    continue
                results.append(rec)
        except IOError as e:
            log.warning("读取事件文件失败 %s: %s", fpath, e)

    return results


def scan_summary(hours: int = 24, team_code: str = "") -> str:
    """
    生成人类可读的事件摘要文本，供注入 LLM prompt。

    Returns:
        多行文本，每行一条事件摘要；无事件时返回 "（无）"
    """
    events = scan(hours=hours, team_code=team_code)
    if not events:
        return "（无）"

    lines = []
    for e in events:
        ts_short = e.get("ts", "")[-14:-6]  # "HH:MM:SS"
        bot = e.get("bot", "?")
        summary = e.get("summary", "")
        lines.append(f"  [{ts_short}] {bot}: {summary}")
    return "\n".join(lines)


def count_by_bot(hours: int = 24, team_code: str = "") -> Dict[str, int]:
    """统计各 bot 在时间窗口内的事件数量。"""
    events = scan(hours=hours, team_code=team_code)
    counts: Dict[str, int] = {}
    for e in events:
        b = e.get("bot", "unknown")
        counts[b] = counts.get(b, 0) + 1
    return counts
