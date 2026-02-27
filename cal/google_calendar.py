# -*- coding: utf-8 -*-
"""
Google 日历只读拉取：iCal 链接（优先）+ 服务账号 API（可选），两者合并去重。

配置：
  GOOGLE_CALENDAR_ICAL_URL  — Google 日历 iCal 订阅地址（推荐）
  GOOGLE_CALENDAR_CREDENTIALS_JSON — 服务账号 JSON 文件路径（可选）
"""
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    import urllib.request
except ImportError:
    urllib = None  # type: ignore


def _get_ical_url() -> Optional[str]:
    u = (os.environ.get("GOOGLE_CALENDAR_ICAL_URL") or "").strip()
    return u if u else None


def _get_credentials_path() -> Optional[str]:
    p = (os.environ.get("GOOGLE_CALENDAR_CREDENTIALS_JSON") or "").strip()
    return p if p and os.path.isfile(p) else None


def _parse_dt(v) -> Optional[date]:
    if v is None:
        return None
    try:
        dt = v.dt if hasattr(v, "dt") else v
        if isinstance(dt, datetime):
            return dt.date()
        if isinstance(dt, date):
            return dt
        return None
    except Exception:
        return None


def _format_dt(v) -> str:
    if v is None:
        return ""
    try:
        dt = v.dt if hasattr(v, "dt") else v
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        if isinstance(dt, date):
            return dt.strftime("%Y-%m-%d")
        return str(dt)
    except Exception:
        return ""


def _list_events_from_ical(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    url = _get_ical_url()
    if not url:
        return []
    try:
        from icalendar import Calendar
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        cal = Calendar.from_ical(data)
        if cal is None:
            return []
        out: List[Dict[str, Any]] = []
        d_min = datetime.strptime(date_from, "%Y-%m-%d").date()
        d_max = datetime.strptime(date_to, "%Y-%m-%d").date()
        for component in cal.walk("vevent"):
            dtstart = component.get("dtstart")
            dtend = component.get("dtend") or dtstart
            start_d = _parse_dt(dtstart)
            end_d = _parse_dt(dtend) or start_d
            if start_d is None:
                continue
            if start_d > d_max or end_d < d_min:
                continue
            summary = component.get("summary") or "(无标题)"
            if hasattr(summary, "to_ical"):
                summary = summary.to_ical().decode("utf-8", errors="replace")
            out.append({"summary": (summary or "(无标题)").strip(), "start": _format_dt(dtstart), "end": _format_dt(dtend), "source": "google"})
        return out
    except Exception:
        return []


def _list_events_from_api(date_from: str, date_to: str, calendar_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cred_path = _get_credentials_path()
    if not cred_path:
        return []
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
        creds = service_account.Credentials.from_service_account_file(cred_path, scopes=scopes)
        service = build("calendar", "v3", credentials=creds)
        cal_id = (calendar_id or os.environ.get("GOOGLE_CALENDAR_ID") or "").strip() or "primary"
        events_result = service.events().list(
            calendarId=cal_id, timeMin=f"{date_from}T00:00:00Z", timeMax=f"{date_to}T23:59:59Z",
            singleEvents=True, orderBy="startTime",
        ).execute()
        out = []
        for e in events_result.get("items", []):
            start = e.get("start") or {}
            end = e.get("end") or {}
            out.append({
                "summary": (e.get("summary") or "(无标题)").strip(),
                "start": start.get("dateTime") or start.get("date") or "",
                "end": end.get("dateTime") or end.get("date") or "",
                "source": "google",
            })
        return out
    except Exception:
        return []


def list_events(date_from: str, date_to: str, calendar_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取 Google 日历在 date_from ~ date_to 内的日程（iCal + API 合并去重）。"""
    ical_events = _list_events_from_ical(date_from, date_to)
    api_events = _list_events_from_api(date_from, date_to, calendar_id)
    seen = {(e.get("summary"), e.get("start")) for e in ical_events}
    for e in api_events:
        k = (e.get("summary"), e.get("start"))
        if k not in seen:
            seen.add(k)
            ical_events.append(e)
    ical_events.sort(key=lambda x: (x.get("start") or "", x.get("summary") or ""))
    return ical_events
