# -*- coding: utf-8 -*-
"""
AI 分析引擎 — 多轮 LLM 调用，将原始热榜数据合成深度日报。

分四个区域独立生成分析：华人圈 / 越南 / 亚太 / 欧美。
每个区域一次 LLM 调用，最后一次生成重要新闻详细摘要。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from core.llm import chat_completion
from newsbot.config import BEIJING, log


def _format_trending_for_prompt(platform_data: dict[str, list[dict]]) -> str:
    """把多平台热榜数据格式化为 prompt 文本。"""
    lines: list[str] = []
    for platform, items in platform_data.items():
        if not items:
            continue
        lines.append(f"\n【{platform}】")
        for item in items:
            score = f" ({item['hot_score']})" if item.get("hot_score") else ""
            lines.append(f"  {item['rank']}. {item['title']}{score}")
    return "\n".join(lines)


def _format_rss_for_prompt(rss_data: dict[str, list[dict]]) -> str:
    """把 RSS 数据格式化为 prompt 文本。"""
    lines: list[str] = []
    for source, items in rss_data.items():
        if not items:
            continue
        lines.append(f"\n【{source}】")
        for item in items[:10]:
            summary = f" — {item['summary'][:80]}" if item.get("summary") else ""
            lines.append(f"  {item['rank']}. {item['title']}{summary}")
    return "\n".join(lines)


def _format_reddit_for_prompt(reddit_data: dict[str, list[dict]]) -> str:
    """Reddit 数据格式化。"""
    lines: list[str] = []
    for sub, items in reddit_data.items():
        if not items:
            continue
        lines.append(f"\n【{sub}】")
        for item in items:
            lines.append(f"  {item['rank']}. {item['title']} ({item.get('hot_score', '')})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 华人圈分析
# ---------------------------------------------------------------------------

CHINESE_SPHERE_SYSTEM = """你是一名顶级国际新闻编辑，精通中国大陆、台湾、香港和海外华人社群的舆情态势。
你的任务是基于多平台热榜原始数据，生成一份高质量的华人圈热点日报分析。

输出要求（严格遵循以下结构和格式）：

**今日焦点**
- 列出 8-10 个最重要的事件/话题，每条格式如下：
  "事件标题/简述——补充背景和意义（出现平台1/平台2/平台3）"
- 优先选择跨平台出现的重大事件
- 每条 1-3 行，包含具体数据和背景

**短视频平台视角（抖音 · 快手 · 小红书）**
- 抖音：列出 3-5 个抖音特有或抖音视角的热点
- 快手：同上
- 小红书：同上

**地区热点对比**
- 内地：2-3 句概括内地核心热点
- 台湾：2-3 句概括台湾核心热点（基于 PTT/Dcard 数据）
- 香港：2-3 句概括香港核心热点（基于 LIHKG 数据）
- 海外华人：2-3 句概括海外华人社区热点（基于 Reddit 数据）

**主题分类**
- 社会/时事：列出属于此类的事件
- 娱乐/体育：同上
- 科技/经济：同上

**今日洞察**
一段 100-150 字的综合分析，点出今日最核心的叙事主线和深层逻辑。

**明日预测**
- 列出 4-5 条对明日舆情走向的预判

注意：
- 用中文输出
- 不要编造数据中没有的事件
- 如果某个平台数据缺失，跳过该平台的分析
- 每个事件尽量标注数据来源平台"""


def analyze_chinese_sphere(
    cn_trending: dict[str, list[dict]],
    hk_tw_data: dict[str, list[dict]],
    reddit_cn: dict[str, list[dict]],
    global_news: list[dict],
    date_str: str,
) -> str:
    """生成华人圈 AI 深度分析。"""
    trending_text = _format_trending_for_prompt(cn_trending)
    hk_tw_text = _format_trending_for_prompt(hk_tw_data)
    reddit_text = _format_reddit_for_prompt(reddit_cn)

    global_lines = ""
    if global_news:
        global_lines = "\n【Google News 全球热点】\n"
        for item in global_news[:15]:
            global_lines += f"  {item.get('rank', '')}. {item['title']}\n"

    user_msg = f"""以下是 {date_str} 的全平台热榜原始数据：

=== 中国大陆平台 ===
{trending_text}

=== 港台平台 ===
{hk_tw_text}

=== 海外华人社区 ===
{reddit_text}
{global_lines}

请基于以上数据，生成华人圈热点日报的 AI 深度分析部分。"""

    try:
        result = chat_completion(
            provider="deepseek",
            system=CHINESE_SPHERE_SYSTEM,
            user=user_msg,
            temperature=0.4,
        )
        log.info("华人圈分析完成: %d 字", len(result))
        return result
    except Exception as e:
        log.error("华人圈分析失败: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 越南分析
# ---------------------------------------------------------------------------

VIETNAM_SYSTEM = """你是一名精通越南时事的国际新闻编辑。
基于越南各大新闻网站的 RSS 头条数据，生成一份越南热点日报分析。

输出要求：

**🔥 今日越南焦点**
- 列出 5-8 个最重要的越南新闻，每条格式：
  "越南语关键短语 中文翻译——补充背景（来源）"

**📂 话题分类**
- 政治/社会：相关事件
- 娱乐/文化：相关事件
- 经济/科技：相关事件

**💡 越南舆论洞察**
一段 80-120 字的综合分析。

**🔗 与华人圈的关联**
如有中越共同关注的话题，点出关联。

注意：用中文输出，越南语人名/地名保留原文并附中文。"""


def analyze_vietnam(rss_data: dict[str, list[dict]], date_str: str) -> str:
    """生成越南 AI 深度分析。"""
    rss_text = _format_rss_for_prompt(rss_data)
    if not rss_text.strip():
        return ""

    user_msg = f"""以下是 {date_str} 越南主要新闻网站的最新头条：
{rss_text}

请生成越南热点日报的 AI 深度分析部分。"""

    try:
        result = chat_completion(
            provider="deepseek",
            system=VIETNAM_SYSTEM,
            user=user_msg,
            temperature=0.4,
        )
        log.info("越南分析完成: %d 字", len(result))
        return result
    except Exception as e:
        log.error("越南分析失败: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 亚太分析
# ---------------------------------------------------------------------------

ASIA_PACIFIC_SYSTEM = """你是一名资深亚太区域新闻编辑。
基于印度、印尼、韩国、日本各大媒体的 RSS 头条和 Reddit/Twitter 数据，生成亚太热点日报分析。

输出要求：

**🔥 今日亚太焦点**
- 列出 5-8 个最重要的亚太新闻

**🌏 各国热点速览**
- 印尼：2-3 条关键新闻
- 印度：2-3 条
- 韩国：2-3 条
- 日本：2-3 条

**📂 主题分类**
- 政治/社会
- 娱乐/文化
- 经济/科技

**💡 亚太洞察**
一段综合分析。

**📈 明日预测**
2-3 条预判。

注意：用中文输出，保留各国人名地名原文。"""


def analyze_asia_pacific(
    rss_data: dict[str, dict[str, list[dict]]],
    reddit_data: dict[str, list[dict]],
    date_str: str,
) -> str:
    """生成亚太 AI 深度分析。"""
    parts: list[str] = []
    for country_key in ("in", "id", "kr", "jp"):
        country_feeds = rss_data.get(country_key, {})
        if country_feeds:
            country_names = {"in": "印度", "id": "印尼", "kr": "韩国", "jp": "日本"}
            parts.append(f"\n=== {country_names.get(country_key, country_key)} ===")
            parts.append(_format_rss_for_prompt(country_feeds))

    reddit_text = _format_reddit_for_prompt(reddit_data)
    if reddit_text:
        parts.append(f"\n=== Reddit 亚太 ===\n{reddit_text}")

    if not any(p.strip() for p in parts):
        return ""

    user_msg = f"""以下是 {date_str} 亚太各国主要媒体的最新头条：
{"".join(parts)}

请生成亚太热点日报的 AI 深度分析部分。"""

    try:
        result = chat_completion(
            provider="deepseek",
            system=ASIA_PACIFIC_SYSTEM,
            user=user_msg,
            temperature=0.4,
        )
        log.info("亚太分析完成: %d 字", len(result))
        return result
    except Exception as e:
        log.error("亚太分析失败: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 欧美分析
# ---------------------------------------------------------------------------

WESTERN_SYSTEM = """你是一名精通欧美时事的国际新闻编辑。
基于美国、英国、德国、法国各大媒体的 RSS 头条和 Reddit 数据，生成欧美热点日报分析。

输出要求：

**🔥 今日欧美焦点**
- 列出 5-8 个最重要的欧美新闻

**🌍 各国热点速览**
- 美国：3-4 条
- 英国：2-3 条
- 德国：2-3 条
- 法国：2-3 条

**📂 主题分类**
- 政治/时事
- 娱乐/体育
- 经济/科技

**💡 欧美洞察**
一段综合分析。

**📈 明日预测**
2-3 条预判。

注意：用中文输出。"""


def analyze_western(
    rss_data: dict[str, dict[str, list[dict]]],
    reddit_data: dict[str, list[dict]],
    date_str: str,
) -> str:
    """生成欧美 AI 深度分析。"""
    parts: list[str] = []
    for country_key in ("us", "uk", "de", "fr"):
        country_feeds = rss_data.get(country_key, {})
        if country_feeds:
            country_names = {"us": "美国", "uk": "英国", "de": "德国", "fr": "法国"}
            parts.append(f"\n=== {country_names.get(country_key, country_key)} ===")
            parts.append(_format_rss_for_prompt(country_feeds))

    reddit_text = _format_reddit_for_prompt(reddit_data)
    if reddit_text:
        parts.append(f"\n=== Reddit 欧美 ===\n{reddit_text}")

    if not any(p.strip() for p in parts):
        return ""

    user_msg = f"""以下是 {date_str} 欧美各国主要媒体的最新头条：
{"".join(parts)}

请生成欧美热点日报的 AI 深度分析部分。"""

    try:
        result = chat_completion(
            provider="deepseek",
            system=WESTERN_SYSTEM,
            user=user_msg,
            temperature=0.4,
        )
        log.info("欧美分析完成: %d 字", len(result))
        return result
    except Exception as e:
        log.error("欧美分析失败: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 重要新闻详细摘要
# ---------------------------------------------------------------------------

SUMMARY_SYSTEM = """你是一名顶级新闻编辑。根据今日热榜数据，选出 5-8 条最重要的新闻，
为每条生成一份 150-250 字的详细摘要。

每条摘要包含：
1. 标题（用 ### 格式）
2. 事件概要（具体事实、数据、人物）
3. 背景与意义
4. 引用来源提示（> 来源：[媒体名](URL) 格式，URL 可以用占位）

选择标准：
- 优先跨区域影响的重大事件
- 优先有具体数据支撑的事件
- 覆盖政治、经济、社会、体育等多领域

用中文输出。"""


def generate_detailed_summaries(all_raw_text: str, date_str: str) -> str:
    """生成重要新闻详细摘要。"""
    user_msg = f"""以下是 {date_str} 全球各平台的热榜原始数据汇总：

{all_raw_text[:8000]}

请选出今日最重要的 5-8 条新闻，生成详细摘要。"""

    try:
        result = chat_completion(
            provider="deepseek",
            system=SUMMARY_SYSTEM,
            user=user_msg,
            temperature=0.3,
        )
        log.info("详细摘要完成: %d 字", len(result))
        return result
    except Exception as e:
        log.error("详细摘要失败: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 主入口：并行分析
# ---------------------------------------------------------------------------

def run_all_analysis(
    cn_trending: dict[str, list[dict]],
    hk_tw_data: dict[str, list[dict]],
    reddit_data: dict[str, dict[str, list[dict]]],
    global_news: list[dict],
    rss_data: dict[str, dict[str, list[dict]]],
    date_str: str,
) -> dict[str, str]:
    """
    并行运行所有区域分析，返回 {区域: 分析文本}。
    """
    results: dict[str, str] = {}

    all_raw_text = _format_trending_for_prompt(cn_trending)
    all_raw_text += _format_trending_for_prompt(hk_tw_data)
    for region_feeds in rss_data.values():
        all_raw_text += _format_rss_for_prompt(region_feeds)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}

        # 华人圈
        futures[pool.submit(
            analyze_chinese_sphere,
            cn_trending, hk_tw_data,
            reddit_data.get("cn", {}), global_news, date_str,
        )] = "cn"

        # 越南
        vn_feeds = rss_data.get("vn", {})
        if vn_feeds:
            futures[pool.submit(analyze_vietnam, vn_feeds, date_str)] = "vn"

        # 亚太
        asia_feeds = {k: v for k, v in rss_data.items() if k in ("in", "id", "kr", "jp")}
        if asia_feeds:
            futures[pool.submit(
                analyze_asia_pacific, asia_feeds,
                reddit_data.get("asia", {}), date_str,
            )] = "asia"

        # 欧美
        west_feeds = {k: v for k, v in rss_data.items() if k in ("us", "uk", "de", "fr")}
        if west_feeds:
            futures[pool.submit(
                analyze_western, west_feeds,
                reddit_data.get("west", {}), date_str,
            )] = "west"

        for fut in as_completed(futures):
            region = futures[fut]
            try:
                text = fut.result()
                if text:
                    results[region] = text
            except Exception as e:
                log.error("分析 %s 失败: %s", region, e)

    # 详细摘要（串行，依赖前面结果）
    try:
        summaries = generate_detailed_summaries(all_raw_text, date_str)
        if summaries:
            results["summaries"] = summaries
    except Exception as e:
        log.error("详细摘要失败: %s", e)

    return results
