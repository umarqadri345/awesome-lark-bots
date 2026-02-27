# -*- coding: utf-8 -*-
"""
Markdown 格式化输出 — 将原始数据 + AI 分析组装为最终日报。
"""

from __future__ import annotations

from datetime import datetime

from newsbot.config import BEIJING, DATA_SOURCES_LINE, REGIONS, log


def _trending_table(items: list[dict], extra_col: str = "") -> str:
    """生成热榜表格。"""
    if not items:
        return "_（数据暂缺）_\n"
    lines: list[str] = []
    if extra_col:
        lines.append(f"| 排名 | 话题 | {extra_col} |")
        lines.append(f"|------|------|{'------' * (len(extra_col) // 3 + 1)}|")
        for item in items:
            lines.append(f"| {item['rank']} | {item['title']} | {item.get('hot_score', '')} |")
    else:
        lines.append("| 排名 | 话题 |")
        lines.append("|------|------|")
        for item in items:
            score = f" ({item['hot_score']})" if item.get("hot_score") else ""
            lines.append(f"| {item['rank']} | {item['title']}{score} |")
    return "\n".join(lines) + "\n"


def _rss_table(items: list[dict]) -> str:
    """生成 RSS 新闻表格。"""
    if not items:
        return "_（数据暂缺）_\n"
    lines: list[str] = []
    lines.append("| 排名 | 话题 |")
    lines.append("|------|------|")
    for item in items:
        lines.append(f"| {item['rank']} | {item['title']} |")
    return "\n".join(lines) + "\n"


def _source_links(platform: str) -> str:
    """平台数据来源标注。"""
    links_map = {
        "微博热搜": "[微博实时热点](https://weibo.com/a/hot/realtime) | [热搜时光机](https://www.weibotop.cn/2.0/) | [今日热榜](https://tophub.today/)",
        "百度热搜": "[百度热搜](https://top.baidu.com/board) | [今日热榜](https://tophub.today/)",
        "知乎热榜": "[知乎热榜](https://www.zhihu.com/hot) | [今日热榜](https://tophub.today/)",
        "哔哩哔哩": "[哔哩哔哩](https://www.bilibili.com) | [今日热榜](https://tophub.today/)",
        "小红书": "[小红书](https://www.xiaohongshu.com) | [新榜](https://www.newrank.cn/)",
        "抖音热搜": "[抖音](https://www.douyin.com) | [今日热榜](https://tophub.today/)",
        "今日头条": "[今日头条](https://www.toutiao.com) | [今日热榜](https://tophub.today/)",
        "微信热文": "[微信公众平台](https://mp.weixin.qq.com) | [今日热榜](https://tophub.today/)",
        "澎湃热榜": "[澎湃新闻](https://www.thepaper.cn) | [今日热榜](https://tophub.today/)",
        "PTT（台湾）": "[PTT网页版](https://www.pttweb.cc/hot/all/today) | [Mo PTT](https://moptt.tw/popular)",
        "Dcard（台湾）": "[Dcard 热门](https://www.dcard.tw/f)",
        "LIHKG（香港）": "[LIHKG 讨论区](https://lihkg.com)",
    }
    return links_map.get(platform, "")


# ---------------------------------------------------------------------------
# 华人圈部分
# ---------------------------------------------------------------------------

def format_chinese_section(
    ai_analysis: str,
    cn_trending: dict[str, list[dict]],
    hk_tw_data: dict[str, list[dict]],
    reddit_cn: dict[str, list[dict]],
    xiaohongshu: list[dict],
) -> str:
    """格式化华人圈完整部分。"""
    lines: list[str] = []

    lines.append("## 🌏 华人圈热点日报")
    lines.append("### 🤖 AI 深度分析")
    if ai_analysis:
        lines.append(ai_analysis)
    else:
        lines.append("_（AI 分析生成中或数据不足）_")
    lines.append("")

    # 原始数据表格
    lines.append("---")
    lines.append("### 📊 各平台原始数据")

    # 中国大陆平台
    platform_order = [
        "微博热搜", "百度热搜", "知乎热榜", "哔哩哔哩",
        "抖音热搜", "今日头条", "微信热文", "澎湃热榜",
    ]
    for platform_name in platform_order:
        items = cn_trending.get(platform_name, [])
        if not items and platform_name not in ("微博热搜", "百度热搜", "知乎热榜"):
            continue
        lines.append(f"#### {platform_name}")
        if platform_name == "哔哩哔哩":
            lines.append(_trending_table(items, "播放量"))
        else:
            lines.append(_trending_table(items))
        src = _source_links(platform_name)
        if src:
            lines.append(f"> 数据来源：{src}")
        lines.append("")

    # 小红书
    if xiaohongshu:
        lines.append("#### 小红书")
        lines.append(_trending_table(xiaohongshu))
        lines.append(f"> 数据来源：{_source_links('小红书')}")
        lines.append("")

    # 港台平台
    hk_tw_order = [
        "PTT（台湾）", "Dcard（台湾）", "Google News台湾",
        "LIHKG（香港）", "Google News香港",
    ]
    for platform_name in hk_tw_order:
        items = hk_tw_data.get(platform_name, [])
        if not items:
            continue
        lines.append(f"#### {platform_name}")
        if platform_name.startswith("Google News"):
            lines.append(_rss_table(items))
        else:
            lines.append(_trending_table(items))
        src = _source_links(platform_name)
        if src:
            lines.append(f"> 数据来源：{src}")
        lines.append("")

    # Reddit
    if reddit_cn:
        lines.append("#### 海外华人 Reddit")
        all_reddit: list[dict] = []
        for sub_items in reddit_cn.values():
            all_reddit.extend(sub_items)
        for i, item in enumerate(all_reddit[:MAX_REDDIT_DISPLAY], 1):
            item["rank"] = i
        lines.append(_trending_table(all_reddit[:MAX_REDDIT_DISPLAY]))
        subs = " | ".join(f"[{s}](https://www.reddit.com/{s}/)" for s in reddit_cn)
        lines.append(f"> 数据来源：{subs}")
        lines.append("")

    return "\n".join(lines)


MAX_REDDIT_DISPLAY = 8


# ---------------------------------------------------------------------------
# 国际区域部分
# ---------------------------------------------------------------------------

def format_international_section(
    region_key: str,
    ai_analysis: str,
    rss_data: dict[str, list[dict]],
    reddit_data: dict[str, list[dict]] | None = None,
) -> str:
    """格式化一个国际区域的完整部分。"""
    region_cfg = REGIONS.get(region_key, {})
    emoji = region_cfg.get("emoji", "🌍")
    name = region_cfg.get("name", region_key)

    lines: list[str] = []
    lines.append(f"## {emoji} {name}")
    lines.append("### 🤖 AI 深度分析")
    if ai_analysis:
        lines.append(ai_analysis)
    else:
        lines.append("_（AI 分析生成中或数据不足）_")
    lines.append("")

    lines.append("---")
    lines.append("### 📊 各平台原始数据")

    country_names = region_cfg.get("country_names", {})

    for source_name, items in rss_data.items():
        if not items:
            continue
        lines.append(f"#### {source_name}")
        lines.append(_rss_table(items))
        lines.append("")

    if reddit_data:
        for sub, items in reddit_data.items():
            if not items:
                continue
            lines.append(f"#### Reddit {sub}")
            lines.append(_trending_table(items))
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 组装完整日报
# ---------------------------------------------------------------------------

def format_full_report(
    date_str: str,
    ai_results: dict[str, str],
    cn_trending: dict[str, list[dict]],
    hk_tw_data: dict[str, list[dict]],
    xiaohongshu: list[dict],
    reddit_data: dict[str, dict[str, list[dict]]],
    rss_data: dict[str, dict[str, list[dict]]],
    global_news: list[dict] | None = None,
    hackernews: list[dict] | None = None,
) -> str:
    """组装完整的早知天下事日报。"""
    sections: list[str] = []

    # ── 头部
    sections.append(f"# 早知天下事热点日报 · {date_str}")
    sections.append(f"> {DATA_SOURCES_LINE}")
    sections.append("---")
    sections.append("")

    # ── 华人圈
    cn_section = format_chinese_section(
        ai_analysis=ai_results.get("cn", ""),
        cn_trending=cn_trending,
        hk_tw_data=hk_tw_data,
        reddit_cn=reddit_data.get("cn", {}),
        xiaohongshu=xiaohongshu,
    )
    sections.append(cn_section)
    sections.append("---")
    sections.append("")

    # ── 越南
    vn_feeds = rss_data.get("vn", {})
    if vn_feeds or ai_results.get("vn"):
        vn_section = format_international_section(
            "vn", ai_results.get("vn", ""), vn_feeds,
        )
        sections.append(vn_section)
        sections.append("---")
        sections.append("")

    # ── 亚太
    asia_feeds: dict[str, list[dict]] = {}
    for country_key in ("in", "id", "kr", "jp"):
        for source, items in rss_data.get(country_key, {}).items():
            country_name = {"in": "印度", "id": "印尼", "kr": "韩国", "jp": "日本"}.get(country_key, "")
            asia_feeds[f"{country_name} {source}"] = items
    if asia_feeds or ai_results.get("asia"):
        asia_section = format_international_section(
            "asia", ai_results.get("asia", ""), asia_feeds,
            reddit_data.get("asia"),
        )
        sections.append(asia_section)
        sections.append("---")
        sections.append("")

    # ── 欧美
    west_feeds: dict[str, list[dict]] = {}
    for country_key in ("us", "uk", "de", "fr"):
        for source, items in rss_data.get(country_key, {}).items():
            country_name = {"us": "美国", "uk": "英国", "de": "德国", "fr": "法国"}.get(country_key, "")
            west_feeds[f"{country_name} {source}"] = items
    if west_feeds or ai_results.get("west"):
        west_section = format_international_section(
            "west", ai_results.get("west", ""), west_feeds,
            reddit_data.get("west"),
        )
        sections.append(west_section)
        sections.append("---")
        sections.append("")

    # ── 全球热点 & 科技前沿
    if global_news or hackernews:
        sections.append("## 🌐 全球热点 & 科技前沿")
        if global_news:
            sections.append("#### Google News 全球热点")
            sections.append(_rss_table(global_news))
            sections.append("")
        if hackernews:
            sections.append("#### Hacker News 科技前沿")
            sections.append(_rss_table(hackernews))
            sections.append("")
        sections.append("---")
        sections.append("")

    # ── 重要新闻详细摘要
    summaries = ai_results.get("summaries", "")
    if summaries:
        sections.append("## 重要新闻详细摘要")
        sections.append(summaries)
        sections.append("")

    return "\n".join(sections)
