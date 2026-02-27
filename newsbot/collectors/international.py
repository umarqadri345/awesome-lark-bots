# -*- coding: utf-8 -*-
"""
国际新闻 RSS 采集 — 越南/日韩/东南亚/欧美。

使用 feedparser 统一解析各国 RSS 源。
每个 feed 最多取 MAX_ITEMS_PER_PLATFORM 条。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from newsbot.config import (
    RSS_FEEDS, GOOGLE_NEWS_FEEDS, HACKERNEWS_FEED,
    MAX_ITEMS_PER_PLATFORM, HEADERS, REQUEST_TIMEOUT, log,
)

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]


def _parse_one_feed(feed_cfg: dict) -> list[dict]:
    """解析单个 RSS 源。"""
    if feedparser is None:
        log.warning("feedparser 未安装，跳过 RSS 采集")
        return []

    url = feed_cfg["url"]
    name = feed_cfg["name"]
    lang = feed_cfg.get("lang", "en")

    try:
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": HEADERS["User-Agent"]},
        )
    except Exception as e:
        log.warning("RSS %s (%s) 解析失败: %s", name, url, e)
        return []

    if not parsed.entries:
        log.debug("RSS %s 无条目", name)
        return []

    items: list[dict] = []
    for i, entry in enumerate(parsed.entries[:MAX_ITEMS_PER_PLATFORM], 1):
        title = entry.get("title") or ""
        if not title:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        if len(summary) > 300:
            summary = summary[:300] + "…"
        link = entry.get("link") or ""
        published = entry.get("published") or entry.get("updated") or ""

        items.append({
            "rank": i,
            "title": title.strip(),
            "summary": summary.strip(),
            "url": link,
            "published": published,
            "source": name,
            "lang": lang,
        })

    log.info("RSS %s: %d 条", name, len(items))
    return items


def fetch_rss_by_region(region_key: str) -> dict[str, list[dict]]:
    """
    采集指定区域的所有 RSS 源。
    返回 {源名称: 条目列表}。
    """
    feeds = RSS_FEEDS.get(region_key, [])
    if not feeds:
        return {}

    results: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_parse_one_feed, cfg): cfg["name"] for cfg in feeds}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                items = fut.result()
                if items:
                    results[name] = items
            except Exception as e:
                log.warning("RSS %s 采集异常: %s", name, e)

    return results


def fetch_google_news(region_key: str) -> list[dict]:
    """
    采集指定区域的 Google News。
    region_key: cn/tw/hk/vn/jp/kr/us/global
    """
    cfg = GOOGLE_NEWS_FEEDS.get(region_key)
    if not cfg:
        return []
    return _parse_one_feed(cfg)


def fetch_hackernews() -> list[dict]:
    """采集 Hacker News 前 15 条。"""
    return _parse_one_feed(HACKERNEWS_FEED)


def fetch_all_international() -> dict[str, dict[str, list[dict]]]:
    """
    采集所有国际 RSS 源。
    返回 {区域key: {源名称: 条目列表}}。
    """
    all_data: dict[str, dict[str, list[dict]]] = {}
    for region_key in RSS_FEEDS:
        region_data = fetch_rss_by_region(region_key)
        if region_data:
            all_data[region_key] = region_data
    return all_data
