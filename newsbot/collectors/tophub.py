# -*- coding: utf-8 -*-
"""
Tophub.today 聚合热榜采集 — 补全无直接 API 的平台。

tophub.today 聚合了几十个中文平台的热搜/热榜，通过 HTML 抓取获得。
用于补全知乎、微信、头条、澎湃等无法直接调 API 的平台。
"""

from __future__ import annotations

import re
from typing import Optional

import requests

from newsbot.config import HEADERS, REQUEST_TIMEOUT, MAX_ITEMS_PER_PLATFORM, log

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[misc,assignment]

TOPHUB_NODES = {
    "知乎热榜": "mproPpoq6O",
    "今日头条": "x9ozB4KoXb",
    "微信热文": "WnBe01o371",
    "澎湃热榜": "wWmoO5Rd4E",
    "百度贴吧": "Om4ejxvxEN",
    "抖音热搜": "DpQvNABoNE",
    "36氪": "Q1Vd5Ko85R",
}


def fetch_tophub_node(node_name: str) -> list[dict]:
    """
    从 tophub.today 抓取指定节点的热榜。
    返回 [{"rank": int, "title": str, "hot_score": str, "url": str}]
    """
    node_id = TOPHUB_NODES.get(node_name)
    if not node_id:
        log.warning("未知的 tophub 节点: %s", node_name)
        return []
    if not BeautifulSoup:
        log.warning("beautifulsoup4 未安装")
        return []

    url = f"https://tophub.today/n/{node_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        log.warning("tophub %s failed: %s", node_name, e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tr")
    items: list[dict] = []

    for row in rows:
        tds = row.select("td")
        if len(tds) < 2:
            continue
        num_text = tds[0].get_text(strip=True).rstrip(".")
        if not num_text.isdigit():
            continue

        title_td = None
        for td in tds[1:]:
            text = td.get_text(strip=True)
            if text and len(text) > 3:
                title_td = td
                break
        if title_td is None:
            continue

        full_text = title_td.get_text(strip=True)
        a_tag = title_td.select_one("a")
        title = a_tag.get_text(strip=True) if a_tag else full_text
        href = a_tag.get("href", "") if a_tag else ""
        link = f"https://tophub.today{href}" if href.startswith("/") else href

        hot_score = ""
        match = re.search(r"(\d+[\.\d]*\s*万?热度)", full_text)
        if match:
            hot_score = match.group(1)
            title = title.replace(hot_score, "").strip()

        if not title or len(title) < 3:
            continue

        items.append({
            "rank": int(num_text),
            "title": title,
            "hot_score": hot_score,
            "url": link,
        })
        if len(items) >= MAX_ITEMS_PER_PLATFORM:
            break

    log.info("tophub %s: %d 条", node_name, len(items))
    return items


def fetch_zhihu_from_tophub() -> list[dict]:
    return fetch_tophub_node("知乎热榜")


def fetch_toutiao_from_tophub() -> list[dict]:
    return fetch_tophub_node("今日头条")


def fetch_weixin_from_tophub() -> list[dict]:
    return fetch_tophub_node("微信热文")


def fetch_pengpai_from_tophub() -> list[dict]:
    return fetch_tophub_node("澎湃热榜")


def fetch_all_supplementary() -> dict[str, list[dict]]:
    """
    采集所有补充平台，返回 {平台名: 热榜列表}。
    用于填补主采集器的空缺。
    """
    results: dict[str, list[dict]] = {}
    for node_name in ("知乎热榜", "今日头条", "微信热文", "澎湃热榜"):
        try:
            items = fetch_tophub_node(node_name)
            if items:
                results[node_name] = items
        except Exception as e:
            log.warning("tophub %s 采集失败: %s", node_name, e)
    return results
