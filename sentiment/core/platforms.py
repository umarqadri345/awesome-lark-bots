# -*- coding: utf-8 -*-
"""
平台相关的共享工具：数据提取、字段解析、时间解析。
"""

from __future__ import annotations
from datetime import datetime
from sentiment.config.settings import PLATFORM_CN, URL_DOMAIN_TO_PLATFORM, BEIJING


# ---------------------------------------------------------------------------
# 从 API 返回中提取列表
# ---------------------------------------------------------------------------

_EXTRACT_KEYS_BY_PLATFORM = {
    "weibo": ("weibo_list", "statuses", "data", "list", "items"),
    "douyin": ("business_data", "itemList", "list", "data", "items", "result"),
    "xiaohongshu": ("data", "notes", "items", "list"),
    "bilibili": ("result", "data", "list", "items"),
    "kuaishou": ("feeds", "list", "data", "items", "result"),
    "zhihu": ("data", "list", "result", "items"),
}
_EXTRACT_KEYS_FALLBACK = (
    "items", "list", "data", "result", "itemList",
    "notes", "feeds", "statuses", "records",
)


def _first_list_in_dict(d, keys_to_try):
    if not isinstance(d, dict) or not keys_to_try:
        return None
    for key in keys_to_try:
        v = d.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            inner = _first_list_in_dict(v, keys_to_try)
            if inner is not None:
                return inner
    return None


def extract_items(data, platform=None):
    """按平台解析列表，各接口返回结构不同。"""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    keys = (_EXTRACT_KEYS_BY_PLATFORM.get(platform, _EXTRACT_KEYS_FALLBACK)
            if platform else _EXTRACT_KEYS_FALLBACK)
    lst = _first_list_in_dict(data, keys)
    return list(lst) if lst is not None else []


def ensure_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return v.get("items") or v.get("list") or v.get("data") or []
    return []


# ---------------------------------------------------------------------------
# 平台名称标准化
# ---------------------------------------------------------------------------

def norm_platform(raw_platform):
    return PLATFORM_CN.get(raw_platform, raw_platform or "其他")


def infer_platform_from_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return "其他"
    u = url.lower().strip()
    for domain, plat in URL_DOMAIN_TO_PLATFORM:
        if domain in u:
            return plat
    return "其他"


# ---------------------------------------------------------------------------
# 帖子解析
# ---------------------------------------------------------------------------

def _title_content_url_by_platform(raw, platform):
    if not platform or not isinstance(raw, dict):
        return None, None, None
    if platform == "weibo":
        content = (raw.get("text") or "").strip()
        url = (raw.get("article_url") or "").strip()
        if not url and raw.get("user_id") and raw.get("bid"):
            url = "https://weibo.com/{}/{}".format(raw.get("user_id"), raw.get("bid"))
        return "", content, url
    if platform == "douyin":
        data = raw.get("data") or {}
        aweme = data.get("aweme_info") or {}
        content = (aweme.get("desc") or "").strip()
        share = aweme.get("share_info") or {}
        url = (share.get("share_url") or "").strip()
        if not url and aweme.get("aweme_id"):
            url = "https://www.douyin.com/video/{}".format(aweme.get("aweme_id"))
        return "", content, url
    if platform == "bilibili":
        title = (raw.get("title") or "").strip()
        content = (raw.get("description") or raw.get("title") or "").strip()
        url = (raw.get("arcurl") or raw.get("link") or raw.get("url") or "").strip()
        return title, content, url
    if platform == "kuaishou":
        content = (raw.get("caption") or "").strip()
        url = (raw.get("main_url") or raw.get("main_mv_url") or raw.get("url") or "").strip()
        if not url and raw.get("photo_id"):
            url = "https://www.kuaishou.com/short-video/{}".format(raw.get("photo_id"))
        return "", content, url
    if platform == "zhihu":
        obj = raw.get("object") or raw
        title = (obj.get("title") or "").strip()
        content = (obj.get("excerpt") or obj.get("content") or obj.get("title") or "").strip()
        url = (obj.get("url") or raw.get("url") or "").strip()
        return title, content, url
    if platform == "xiaohongshu":
        title = (raw.get("title") or raw.get("display_title") or "").strip()
        content = (raw.get("desc") or raw.get("content") or raw.get("title") or "").strip()
        url = (raw.get("url") or raw.get("link") or raw.get("share_url") or "").strip()
        if not url:
            note_id = raw.get("note_id") or raw.get("id") or raw.get("item_id")
            if note_id:
                url = "https://www.xiaohongshu.com/discovery/item/{}".format(note_id)
        return title, content, url
    return None, None, None


def parse_post(raw, platform=None):
    """解析单条为 { platform, title, content, url }。"""
    plat = norm_platform(raw.get("source") or raw.get("platform") or "")
    platform_key = platform
    if platform:
        plat = norm_platform(platform) if isinstance(platform, str) else plat
    title, content, url = _title_content_url_by_platform(
        raw, platform_key if platform_key and plat != "其他" else None
    )
    if title is None:
        url = (raw.get("url") or raw.get("link") or raw.get("shareUrl")
               or raw.get("article_url") or "")
        title = (raw.get("title") or "").strip()
        content = (
            raw.get("content") or raw.get("desc") or raw.get("description")
            or raw.get("text") or raw.get("title") or ""
        ).strip()
    if plat == "其他" or not plat:
        plat = infer_platform_from_url(url)
    return {
        "platform": plat,
        "title": title or "",
        "content": (content or "").strip(),
        "url": url or "",
    }


def fix_platform_from_url(posts: list[dict]) -> None:
    for p in posts:
        if p.get("platform") == "其他" or not p.get("platform"):
            p["platform"] = infer_platform_from_url(p.get("url") or "")


def dedup_posts(posts):
    """按 URL 或内容前 80 字去重。"""
    seen, out = set(), []
    for p in posts:
        k = p["url"] or p["content"][:80]
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# 时间解析 & 过滤
# ---------------------------------------------------------------------------

def parse_item_time(raw: dict, platform: str | None = None) -> datetime | None:
    if platform == "douyin":
        v = (raw.get("data") or {}).get("aweme_info") or {}
        v = v.get("create_time")
        if v is not None:
            try:
                if isinstance(v, (int, float)) and v > 0:
                    if v > 1e12:
                        v = v / 1000.0
                    return datetime.fromtimestamp(v, tz=BEIJING)
            except Exception:
                pass
    if platform == "bilibili":
        v = raw.get("pubdate")
        if v is not None:
            try:
                if isinstance(v, (int, float)) and v > 0:
                    return datetime.fromtimestamp(v, tz=BEIJING)
            except Exception:
                pass
    if platform == "kuaishou":
        v = raw.get("timestamp") or raw.get("time")
        if v is not None:
            try:
                if isinstance(v, (int, float)) and v > 0:
                    if v > 1e12:
                        v = v / 1000.0
                    return datetime.fromtimestamp(v, tz=BEIJING)
                if isinstance(v, str):
                    return datetime.strptime(
                        v[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=BEIJING)
            except Exception:
                pass

    for key in ("createTime", "publishTime", "postTime", "date", "time",
                "created_at", "create_time"):
        v = raw.get(key)
        if v is None:
            continue
        try:
            if isinstance(v, (int, float)):
                if v > 1e12:
                    v = v / 1000.0
                return datetime.fromtimestamp(v, tz=BEIJING)
            if isinstance(v, str):
                s = v.replace("Z", "").strip()
                for fmt, ln in (
                    ("%Y-%m-%d %H:%M:%S", 19),
                    ("%Y-%m-%dT%H:%M:%S", 19),
                    ("%Y-%m-%d", 10),
                ):
                    try:
                        return datetime.strptime(s[:ln], fmt).replace(tzinfo=BEIJING)
                    except ValueError:
                        pass
        except Exception:
            continue
    return None


def filter_raw_by_time(raw_list: list, start_dt: datetime, end_dt: datetime,
                       platform: str | None = None) -> list:
    out = []
    for r in raw_list:
        if not isinstance(r, dict):
            continue
        t = parse_item_time(r, platform)
        if t is None:
            out.append(r)
            continue
        if start_dt <= t <= end_dt:
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# 互动量 & 粉丝数解析（月度统计用）
# ---------------------------------------------------------------------------

def safe_int(v, default=0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def engagement_one(item: dict, platform: str | None = None) -> int:
    if platform == "douyin":
        aweme = (item.get("data") or {}).get("aweme_info") or {}
        st = aweme.get("statistics") or {}
        return (safe_int(st.get("digg_count")) + safe_int(st.get("comment_count"))
                + safe_int(st.get("share_count")) + safe_int(st.get("play_count")))
    if platform == "bilibili":
        return (safe_int(item.get("like")) + safe_int(item.get("video_review"))
                + safe_int(item.get("play")))
    total = 0
    for key in (
        "like_count", "likes_count", "digg_count", "likes", "likeCount", "attitudes_count",
        "comment_count", "comments_count", "comments", "commentCount",
        "share_count", "shareCount", "repost_count", "reposts_count",
        "play_count", "playCount", "view_count", "views",
    ):
        v = item.get(key)
        if v is not None:
            total += safe_int(v)
    if "reads_count" in item:
        total += safe_int(item.get("reads_count"))
    return total


def author_fans_from_item(item: dict, platform: str | None = None) -> int | None:
    if platform == "douyin":
        author = (item.get("data") or {}).get("aweme_info") or {}
        author = author.get("author") or author
        if isinstance(author, dict):
            v = author.get("follower_count") or author.get("followerCount")
            if v is not None:
                return safe_int(v) or None
    for obj in [item, item.get("user") or {}, item.get("author") or {}]:
        if not isinstance(obj, dict):
            continue
        for key in (
            "followers_count", "fans_count", "follower_count", "followersCount",
            "fansCount", "followerCount", "fans", "follower",
        ):
            v = obj.get(key)
            if v is not None and str(v).isdigit():
                return int(v)
    return None
