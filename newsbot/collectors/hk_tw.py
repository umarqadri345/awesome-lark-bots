# -*- coding: utf-8 -*-
"""
港台平台热榜采集 — PTT / Dcard / LIHKG。

PTT :  pttweb.cc 热门文章聚合 (HTML 抓取)
Dcard: 公开 API
LIHKG: 公开 API
"""

from __future__ import annotations

import re
from typing import Any

import requests

from newsbot.config import HEADERS, REQUEST_TIMEOUT, MAX_ITEMS_PER_PLATFORM, log

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[misc,assignment]


def _get_json(url: str, headers: dict | None = None, timeout: int = REQUEST_TIMEOUT) -> Any:
    try:
        r = requests.get(url, headers=headers or HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
        return None


def _get_html(url: str, headers: dict | None = None, timeout: int = REQUEST_TIMEOUT) -> str:
    try:
        r = requests.get(url, headers=headers or HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
        return ""


# ---------------------------------------------------------------------------
# PTT — 通过 pttweb.cc 热门文章
# ---------------------------------------------------------------------------

def fetch_ptt_hot() -> list[dict]:
    """PTT 今日热门 — 从 pttweb.cc 抓取。"""
    html = _get_html("https://www.pttweb.cc/hot/all/today")
    if not html or not BeautifulSoup:
        return _fetch_ptt_fallback()
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    divs = soup.select("div.e7-right-body-container a, a.e7-container")
    if not divs:
        divs = soup.select("a[href*='/bbs/']")

    for a_tag in divs:
        title_el = a_tag.select_one("span.e7-show-if-device-is-not-xs") or a_tag.select_one(".title-text")
        title = ""
        if title_el:
            title = title_el.get_text(strip=True)
        if not title:
            title = a_tag.get_text(strip=True)
        title = re.sub(r"^(Re:\s*)+", "", title).strip()
        if not title or len(title) < 4:
            continue
        href = a_tag.get("href", "")
        url = f"https://www.pttweb.cc{href}" if href.startswith("/") else href
        push_el = a_tag.select_one(".e7-push-count, .push-count")
        push = push_el.get_text(strip=True) if push_el else ""
        items.append({
            "rank": len(items) + 1,
            "title": title,
            "hot_score": push,
            "url": url,
        })
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break

    log.info("PTT热门: %d 条", len(items))
    return items


def _fetch_ptt_fallback() -> list[dict]:
    """PTT 回退 — 直接请求 ptt.cc 热门看板。"""
    html = _get_html(
        "https://www.ptt.cc/bbs/hotboards.html",
        headers={**HEADERS, "Cookie": "over18=1"},
    )
    if not html or not BeautifulSoup:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for a_tag in soup.select("a.board"):
        name = a_tag.select_one(".board-name")
        if not name:
            continue
        items.append({
            "rank": len(items) + 1,
            "title": name.get_text(strip=True),
            "hot_score": "",
            "url": "https://www.ptt.cc" + a_tag.get("href", ""),
        })
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break
    log.info("PTT热门(fallback): %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# Dcard — 热门文章 API
# ---------------------------------------------------------------------------

def fetch_dcard_hot() -> list[dict]:
    """Dcard 台湾热门文章 — 尝试多个 API 路径。"""
    apis = [
        "https://www.dcard.tw/service/api/v2/posts?popular=true&limit=30",
        "https://www.dcard.tw/service/api/v2/forums/all/posts?popular=true&limit=30",
    ]
    dcard_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://www.dcard.tw/f",
        "Accept": "application/json",
    }
    data = None
    for url in apis:
        data = _get_json(url, headers=dcard_headers)
        if data and isinstance(data, list):
            break
        data = None

    if not data:
        return _fetch_dcard_via_scrape()

    items: list[dict] = []
    for i, post in enumerate(data[:MAX_ITEMS_PER_PLATFORM], 1):
        title = post.get("title") or ""
        if not title:
            continue
        likes = post.get("likeCount") or 0
        pid = post.get("id") or ""
        items.append({
            "rank": i,
            "title": title.strip(),
            "hot_score": f"{likes}赞" if likes else "",
            "url": f"https://www.dcard.tw/f/all/p/{pid}" if pid else "",
        })
    log.info("Dcard热门: %d 条", len(items))
    return items


def _fetch_dcard_via_scrape() -> list[dict]:
    """Dcard 回退 — HTML 抓取。"""
    html = _get_html("https://www.dcard.tw/f", headers={
        **HEADERS, "Accept": "text/html",
    })
    if not html or not BeautifulSoup:
        log.info("Dcard: 无法获取数据")
        return []
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for a_tag in soup.select("h2 a, a[href*='/p/']"):
        title = a_tag.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        href = a_tag.get("href", "")
        url = f"https://www.dcard.tw{href}" if href.startswith("/") else href
        items.append({
            "rank": len(items) + 1,
            "title": title,
            "hot_score": "",
            "url": url,
        })
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break
    log.info("Dcard(scrape): %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# LIHKG — 热门帖子 API
# ---------------------------------------------------------------------------

def fetch_lihkg_hot() -> list[dict]:
    """LIHKG 香港讨论区热门。"""
    lihkg_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://lihkg.com/",
        "X-Li-Device": "browser",
        "Accept": "application/json",
    }
    data = _get_json(
        "https://lihkg.com/api_v2/thread/hot",
        headers=lihkg_headers,
        timeout=15,
    )
    if not data:
        return []
    threads = (data.get("response") or {}).get("items") or []
    items: list[dict] = []
    for i, thread in enumerate(threads[:MAX_ITEMS_PER_PLATFORM], 1):
        title = thread.get("title") or ""
        if not title:
            continue
        replies = thread.get("no_of_reply") or 0
        tid = thread.get("thread_id") or ""
        items.append({
            "rank": i,
            "title": title.strip(),
            "hot_score": f"{replies}回复" if replies else "",
            "url": f"https://lihkg.com/thread/{tid}" if tid else "",
        })
    log.info("LIHKG热门: %d 条", len(items))
    return items


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def fetch_google_news_tw() -> list[dict]:
    """Google News 台湾 — Dcard 的替代数据源。"""
    from newsbot.collectors.international import fetch_google_news
    return fetch_google_news("tw")


def fetch_google_news_hk() -> list[dict]:
    """Google News 香港 — LIHKG 的补充数据源。"""
    from newsbot.collectors.international import fetch_google_news
    return fetch_google_news("hk")


def fetch_all_hk_tw() -> dict[str, list[dict]]:
    """采集所有港台平台，返回 {平台名: 热榜列表}。"""
    results: dict[str, list[dict]] = {}
    fetchers = {
        "PTT（台湾）": fetch_ptt_hot,
        "Dcard（台湾）": fetch_dcard_hot,
        "LIHKG（香港）": fetch_lihkg_hot,
        "Google News台湾": fetch_google_news_tw,
        "Google News香港": fetch_google_news_hk,
    }
    for name, fn in fetchers.items():
        try:
            data = fn()
            if data:
                results[name] = data
        except Exception as e:
            log.error("采集 %s 失败: %s", name, e)
    return results
