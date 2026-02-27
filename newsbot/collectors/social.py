# -*- coding: utf-8 -*-
"""
Reddit + Twitter 采集。

Reddit: 公开 JSON API（不需要认证）
Twitter: 通过 JustOneAPI 搜索
"""

from __future__ import annotations

import time
from typing import Any

import requests

from newsbot.config import (
    HEADERS, REQUEST_TIMEOUT, MAX_ITEMS_PER_PLATFORM,
    JOA_TOKEN, JOA_BASE, REDDIT_SUBS, log,
)


# ---------------------------------------------------------------------------
# Reddit — 公开 JSON API
# ---------------------------------------------------------------------------

def fetch_reddit_hot(subreddits: list[str], limit: int = 10) -> dict[str, list[dict]]:
    """
    抓取多个 subreddit 的热门帖子。
    返回 {subreddit: 帖子列表}。
    """
    results: dict[str, list[dict]] = {}
    reddit_headers = {
        "User-Agent": "NewsBot/1.0 (daily digest bot)",
        "Accept": "application/json",
    }
    for sub in subreddits:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                headers=reddit_headers,
                params={"limit": str(limit), "raw_json": "1"},
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("Reddit r/%s failed: %s", sub, e)
            continue

        children = (data.get("data") or {}).get("children") or []
        items: list[dict] = []
        for i, child in enumerate(children, 1):
            post = child.get("data") or {}
            if post.get("stickied"):
                continue
            title = post.get("title") or ""
            if not title:
                continue
            score = post.get("score") or 0
            permalink = post.get("permalink") or ""
            items.append({
                "rank": len(items) + 1,
                "title": title.strip(),
                "hot_score": f"{score}分",
                "url": f"https://www.reddit.com{permalink}" if permalink else "",
                "subreddit": sub,
                "comments": post.get("num_comments") or 0,
            })
            if len(items) >= limit:
                break

        if items:
            results[f"r/{sub}"] = items
            log.info("Reddit r/%s: %d 条", sub, len(items))

        time.sleep(1)

    return results


def fetch_reddit_for_region(region: str) -> dict[str, list[dict]]:
    """采集指定区域的 Reddit 数据。"""
    subs = REDDIT_SUBS.get(region, [])
    if not subs:
        return {}
    return fetch_reddit_hot(subs, limit=8)


# ---------------------------------------------------------------------------
# Google News Global — 替代 Twitter 作为全球热点视角
# ---------------------------------------------------------------------------

def fetch_global_news() -> list[dict]:
    """
    通过 Google News Global 获取全球热点新闻，
    作为 Twitter/X 趋势数据的替代。
    """
    from newsbot.collectors.international import fetch_google_news
    return fetch_google_news("global")


# ---------------------------------------------------------------------------
# Hacker News — 科技圈热点
# ---------------------------------------------------------------------------

def fetch_hackernews() -> list[dict]:
    """获取 Hacker News 前沿科技热帖。"""
    from newsbot.collectors.international import fetch_hackernews as _hn
    return _hn()
