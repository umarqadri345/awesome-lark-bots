# -*- coding: utf-8 -*-
"""
中国平台热榜采集 — 微博/百度/知乎/B站/抖音/快手/小红书。

每个函数返回 list[dict]，格式统一：
  {"rank": int, "title": str, "hot_score": str, "url": str}

所有函数对异常做静默降级，失败返回空列表。
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from newsbot.config import HEADERS, REQUEST_TIMEOUT, MAX_ITEMS_PER_PLATFORM, JOA_TOKEN, JOA_BASE, log


def _get(url: str, headers: dict | None = None, params: dict | None = None,
         timeout: int = REQUEST_TIMEOUT) -> Any:
    """通用 GET，返回 JSON 或 None。"""
    try:
        r = requests.get(url, headers=headers or HEADERS, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
        return None


def _joa(endpoint: str, params: dict) -> Any:
    """JOA API 请求。"""
    if not JOA_TOKEN:
        return None
    p = {**params, "token": JOA_TOKEN}
    try:
        r = requests.get(f"{JOA_BASE}{endpoint}", params=p, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("code") == 0:
            return body.get("data")
    except Exception as e:
        log.warning("JOA %s failed: %s", endpoint, e)
    return None


# ---------------------------------------------------------------------------
# 微博热搜
# ---------------------------------------------------------------------------

def fetch_weibo_trending() -> list[dict]:
    """微博实时热搜 — hot_band 接口。"""
    data = _get(
        "https://weibo.com/ajax/statuses/hot_band",
        headers={**HEADERS, "Referer": "https://weibo.com/", "Accept": "application/json"},
    )
    if not data:
        return []
    band_list = (data.get("data") or {}).get("band_list") or []
    items = []
    for i, entry in enumerate(band_list[:MAX_ITEMS_PER_PLATFORM], 1):
        word = entry.get("word") or entry.get("note") or ""
        if not word:
            continue
        score = entry.get("raw_hot") or entry.get("num") or ""
        items.append({
            "rank": i,
            "title": word.strip(),
            "hot_score": str(score),
            "url": f"https://s.weibo.com/weibo?q=%23{word}%23",
        })
    log.info("微博热搜: %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 百度热搜
# ---------------------------------------------------------------------------

def fetch_baidu_trending() -> list[dict]:
    """百度热搜 — 移动端 API（三层嵌套：cards[0].content[0].content[]）。"""
    data = _get(
        "https://top.baidu.com/api/board",
        params={"platform": "wise", "tab": "realtime"},
        headers={**HEADERS, "Referer": "https://top.baidu.com/"},
    )
    if not data:
        return []
    cards = (data.get("data") or {}).get("cards") or []
    if not cards:
        return []
    outer = cards[0].get("content") or []
    content_list = outer[0].get("content") if outer and isinstance(outer[0], dict) else outer
    if not content_list or not isinstance(content_list, list):
        return []
    items = []
    for i, entry in enumerate(content_list[:MAX_ITEMS_PER_PLATFORM], 1):
        if not isinstance(entry, dict):
            continue
        word = entry.get("word") or entry.get("query") or ""
        if not word:
            continue
        score = entry.get("hotScore") or entry.get("index") or ""
        items.append({
            "rank": i,
            "title": word.strip(),
            "hot_score": str(score),
            "url": entry.get("url") or f"https://www.baidu.com/s?wd={word}",
        })
    log.info("百度热搜: %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 知乎热榜
# ---------------------------------------------------------------------------

def fetch_zhihu_trending() -> list[dict]:
    """知乎热榜 — 尝试公开 API → JOA 搜索 → tophub 兜底。"""
    zhihu_headers = {
        **HEADERS,
        "Referer": "https://www.zhihu.com/hot",
    }
    data = _get(
        "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total",
        headers=zhihu_headers,
        params={"limit": str(MAX_ITEMS_PER_PLATFORM)},
    )
    if data:
        entries = data.get("data") or []
        items = []
        for i, entry in enumerate(entries[:MAX_ITEMS_PER_PLATFORM], 1):
            target = entry.get("target") or {}
            title = target.get("title") or ""
            if not title:
                continue
            detail = entry.get("detail_text") or ""
            qid = target.get("id") or ""
            items.append({
                "rank": i,
                "title": title.strip(),
                "hot_score": detail,
                "url": f"https://www.zhihu.com/question/{qid}" if qid else "",
            })
        if items:
            log.info("知乎热榜: %d 条", len(items))
            return items

    joa_items = _fetch_zhihu_via_joa_search()
    if joa_items:
        return joa_items

    from newsbot.collectors.tophub import fetch_zhihu_from_tophub
    return fetch_zhihu_from_tophub()


def _fetch_zhihu_via_joa_search() -> list[dict]:
    """知乎热榜 — 通过 JOA 搜索热门关键词近似还原。"""
    hot_keywords = ["热搜", "今天", "如何看待"]
    seen: set[str] = set()
    items: list[dict] = []
    for kw in hot_keywords:
        data = _joa("/api/zhihu/search/v1", {"keyword": kw, "offset": 0})
        if not data:
            continue
        raw = data if isinstance(data, list) else data.get("items") or data.get("list") or []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("name") or ""
            q = entry.get("question")
            if not title and isinstance(q, dict):
                title = q.get("title", "")
            title = re.sub(r"<[^>]+>", "", title).strip()
            if not title or title in seen or len(title) < 4:
                continue
            seen.add(title)
            items.append({
                "rank": len(items) + 1,
                "title": title,
                "hot_score": "",
                "url": entry.get("url") or "",
            })
            if len(items) >= MAX_ITEMS_PER_PLATFORM:
                break
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break
        time.sleep(0.5)
    log.info("知乎(JOA搜索): %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# B站排行榜
# ---------------------------------------------------------------------------

def fetch_bilibili_trending() -> list[dict]:
    """B站热门视频排行榜 — 公开 API。"""
    data = _get(
        "https://api.bilibili.com/x/web-interface/ranking/v2",
        params={"rid": "0", "type": "all"},
    )
    if not data:
        return []
    entries = (data.get("data") or {}).get("list") or []
    items = []
    for i, entry in enumerate(entries[:MAX_ITEMS_PER_PLATFORM], 1):
        title = entry.get("title") or ""
        if not title:
            continue
        stat = entry.get("stat") or {}
        view = stat.get("view") or 0
        if view >= 10000:
            score_str = f"{view / 10000:.1f}万播放"
        else:
            score_str = f"{view}播放"
        bvid = entry.get("bvid") or ""
        items.append({
            "rank": i,
            "title": title.strip(),
            "hot_score": score_str,
            "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
        })
    log.info("B站热门: %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 抖音热搜
# ---------------------------------------------------------------------------

def fetch_douyin_trending() -> list[dict]:
    """抖音热搜 — 尝试公开接口 + JOA 回退。"""
    items = _fetch_douyin_direct()
    if items:
        return items
    return _fetch_douyin_via_joa()


def _fetch_douyin_direct() -> list[dict]:
    """抖音热搜直接请求（可能需要 cookie）。"""
    try:
        r = requests.get(
            "https://www.douyin.com/aweme/v1/web/hot/search/list/",
            headers={
                **HEADERS,
                "Referer": "https://www.douyin.com/",
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    word_list = (data.get("data") or {}).get("word_list") or []
    items = []
    for i, entry in enumerate(word_list[:MAX_ITEMS_PER_PLATFORM], 1):
        word = entry.get("word") or ""
        if not word:
            continue
        score = entry.get("hot_value") or ""
        items.append({
            "rank": i,
            "title": word.strip(),
            "hot_score": str(score),
            "url": f"https://www.douyin.com/search/{word}",
        })
    if items:
        log.info("抖音热搜(直连): %d 条", len(items))
    return items


def _fetch_douyin_via_joa() -> list[dict]:
    """抖音热搜 JOA 回退。"""
    data = _joa("/api/douyin/hot-search/v1", {})
    if not data:
        return []
    raw = data if isinstance(data, list) else data.get("list") or data.get("items") or []
    items = []
    for i, entry in enumerate(raw[:MAX_ITEMS_PER_PLATFORM], 1):
        word = entry.get("word") or entry.get("title") or entry.get("query") or ""
        if not word:
            continue
        items.append({
            "rank": i,
            "title": word.strip(),
            "hot_score": str(entry.get("hotValue") or entry.get("hot_value") or ""),
            "url": entry.get("url") or "",
        })
    if items:
        log.info("抖音热搜(JOA): %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 快手热搜
# ---------------------------------------------------------------------------

def fetch_kuaishou_trending() -> list[dict]:
    """快手热搜。"""
    items = _fetch_kuaishou_via_joa()
    if items:
        return items
    return []


def _fetch_kuaishou_via_joa() -> list[dict]:
    """快手热搜 JOA。"""
    data = _joa("/api/kuaishou/hot-search/v1", {})
    if not data:
        return []
    raw = data if isinstance(data, list) else data.get("list") or data.get("items") or []
    items = []
    for i, entry in enumerate(raw[:MAX_ITEMS_PER_PLATFORM], 1):
        word = entry.get("word") or entry.get("title") or entry.get("name") or ""
        if not word:
            continue
        items.append({
            "rank": i,
            "title": word.strip(),
            "hot_score": str(entry.get("hotValue") or ""),
            "url": entry.get("url") or "",
        })
    if items:
        log.info("快手热搜(JOA): %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 小红书热点（搜索型，非热榜）
# ---------------------------------------------------------------------------

def fetch_xiaohongshu_trending(seed_keywords: list[str] | None = None) -> list[dict]:
    """
    小红书没有公开热榜 API。
    策略：用其他平台的热词作为种子搜索小红书，统计高频话题。
    """
    if not JOA_TOKEN:
        return []
    keywords = seed_keywords or ["今日热点", "热搜", "今天"]
    seen_titles: set[str] = set()
    items: list[dict] = []
    for kw in keywords[:5]:
        data = _joa("/api/xiaohongshu/search-note/v2", {
            "keyword": kw, "page": 1, "sort": "general", "noteType": "_0",
        })
        if not data:
            continue
        notes = data if isinstance(data, list) else data.get("items") or data.get("list") or []
        for note in notes:
            if not isinstance(note, dict):
                continue
            title = note.get("title") or note.get("noteCard", {}).get("displayTitle") or ""
            title = title.strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            likes = note.get("likes") or note.get("likedCount") or ""
            items.append({
                "rank": 0,
                "title": title,
                "hot_score": str(likes),
                "url": note.get("url") or "",
            })
            if len(items) >= MAX_ITEMS_PER_PLATFORM:
                break
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break
        time.sleep(0.5)
    for i, item in enumerate(items, 1):
        item["rank"] = i
    log.info("小红书: %d 条 (搜索型)", len(items))
    return items


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def fetch_all_cn_trending() -> dict[str, list[dict]]:
    """采集所有中国平台热榜，返回 {平台名: 热榜列表}。"""
    from newsbot.collectors.tophub import (
        fetch_toutiao_from_tophub,
        fetch_weixin_from_tophub,
        fetch_pengpai_from_tophub,
    )

    results: dict[str, list[dict]] = {}
    fetchers = {
        "微博热搜": fetch_weibo_trending,
        "百度热搜": fetch_baidu_trending,
        "知乎热榜": fetch_zhihu_trending,
        "哔哩哔哩": fetch_bilibili_trending,
        "抖音热搜": fetch_douyin_trending,
        "今日头条": fetch_toutiao_from_tophub,
        "微信热文": fetch_weixin_from_tophub,
        "澎湃热榜": fetch_pengpai_from_tophub,
    }
    for name, fn in fetchers.items():
        try:
            results[name] = fn()
        except Exception as e:
            log.error("采集 %s 失败: %s", name, e)
            results[name] = []
    return results
