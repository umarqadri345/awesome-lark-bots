# -*- coding: utf-8 -*-
"""日程聚合：飞书日历 + Google 日历 + 本地备忘，供「今日日程」使用。"""
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.feishu_client import list_calendar_events, get_primary_calendar_id, get_user_access_token
from memo.store import list_memos

try:
    from cal.google_calendar import list_events as google_list_events
except ImportError:
    def google_list_events(*_args, **_kwargs):  # type: ignore[misc]
        return []


def get_calendar_id_for_listing(user_open_id: Optional[str] = None) -> Optional[str]:
    cal_id = (os.environ.get("FEISHU_CALENDAR_ID") or "").strip()
    if cal_id:
        return cal_id
    if user_open_id:
        token = get_user_access_token("calendar_get")
        return get_primary_calendar_id(user_open_id, user_access_token=token)
    return None


def aggregate_for_date(date_str: str, user_open_id: Optional[str] = None) -> Dict[str, Any]:
    """
    date_str: YYYY-MM-DD 或 "today"/"tomorrow"/"今天"/"明天"。
    返回 {"date": "YYYY-MM-DD", "feishu_events": [...], "google_events": [...], "memos": [...]}.
    """
    if date_str in ("today", "今天"):
        d = datetime.now().date()
    elif date_str in ("tomorrow", "明天"):
        d = (datetime.now() + timedelta(days=1)).date()
    else:
        try:
            d = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            d = datetime.now().date()

    date_from = d.strftime("%Y-%m-%d")
    start_ts = int(datetime(d.year, d.month, d.day, 0, 0, 0).timestamp())
    end_ts = int(datetime(d.year, d.month, d.day, 23, 59, 59).timestamp())

    feishu_events: List[dict] = []
    cal_id = get_calendar_id_for_listing(user_open_id)
    if cal_id:
        token = get_user_access_token("calendar_get")
        raw = list_calendar_events(cal_id, start_ts, end_ts, user_access_token=token)
        for e in raw:
            feishu_events.append({
                "summary": (e.get("summary") or "(无标题)").strip(),
                "start": e.get("start_time") or {},
                "end": e.get("end_time") or {},
                "source": "feishu",
            })

    google_events = google_list_events(date_from, date_from)
    memos = list_memos(date_from=date_from, date_to=date_from, user_open_id=user_open_id or None)
    memos_out = [{"content": m.get("content", ""), "reminder_date": m.get("reminder_date", "")} for m in memos]

    return {"date": date_from, "feishu_events": feishu_events, "google_events": google_events, "memos": memos_out}
