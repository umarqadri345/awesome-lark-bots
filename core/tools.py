# -*- coding: utf-8 -*-
"""
core/tools.py — LLM 可调用的工具库
==================================

把项目中已有的搜索、数据查询、知识检索等能力包装为标准 ToolDef，
供 AgentLoop 注册使用。

每个工具同时提供：
  - 函数实现（包装现有模块）
  - OpenAI tool definition（通过 ToolDef）

使用方式：
  >>> from core.tools import SEARCH_TOOLS, CONTENT_TOOLS, KNOWLEDGE_TOOLS
  >>> agent.add_tools(SEARCH_TOOLS)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from core.agent import ToolDef

log = logging.getLogger("tools")


# ═══════════════════════════════════════════════════════════════
# 1. 搜索类工具 — 来自 research/search.py
# ═══════════════════════════════════════════════════════════════

def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """网页搜索（Tavily 优先，DuckDuckGo 回退）。"""
    from research.search import web_search
    results = web_search(query, max_results=max_results)
    return [{"title": r.get("title", ""), "content": r.get("content", "")[:500], "url": r.get("url", "")}
            for r in (results or [])]


def _news_search(query: str, max_results: int = 5) -> list[dict]:
    """新闻搜索。"""
    from research.search import news_search
    results = news_search(query, max_results=max_results)
    return [{"title": r.get("title", ""), "content": r.get("content", "")[:500], "url": r.get("url", "")}
            for r in (results or [])]


def _fetch_url(url: str) -> str:
    """抓取网页正文。"""
    from research.search import fetch_url
    return fetch_url(url, max_chars=6000)


WEB_SEARCH_TOOL = ToolDef(
    name="web_search",
    description="搜索网页获取信息。可用于查找行业报告、竞品分析、爆款案例、公开数据等。建议用中英文关键词分别搜索获取更多结果。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "返回结果数量，默认5"},
        },
        "required": ["query"],
    },
    fn=_web_search,
)

NEWS_SEARCH_TOOL = ToolDef(
    name="news_search",
    description="搜索最近的新闻报道。用于获取时事热点、行业动态、近期事件。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "新闻搜索关键词"},
            "max_results": {"type": "integer", "description": "返回结果数量，默认5"},
        },
        "required": ["query"],
    },
    fn=_news_search,
)

FETCH_URL_TOOL = ToolDef(
    name="fetch_url",
    description="获取指定网页的正文内容，用于深入阅读某个来源。",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的网页 URL"},
        },
        "required": ["url"],
    },
    fn=_fetch_url,
)

SEARCH_TOOLS = [WEB_SEARCH_TOOL, NEWS_SEARCH_TOOL, FETCH_URL_TOOL]


# ═══════════════════════════════════════════════════════════════
# 2. 热点趋势 — 来自 newsbot + conductor/stages/trend_scanner.py
# ═══════════════════════════════════════════════════════════════

def _get_trending(platforms: str = "weibo,douyin,zhihu") -> list[dict]:
    """获取各平台热搜/热榜。platforms 用逗号分隔。"""
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    try:
        from conductor.stages.trend_scanner import scan_trends
        items = scan_trends(platform_list, max_per_platform=10)
        return [{"platform": t.platform, "title": t.title, "heat": t.heat}
                for t in items[:30]]
    except Exception as e:
        log.warning("get_trending failed: %s", e)
        return []


TRENDING_TOOL = ToolDef(
    name="get_trending",
    description="获取各平台实时热搜/热榜。可查微博、抖音、知乎、B站、小红书、快手等。",
    parameters={
        "type": "object",
        "properties": {
            "platforms": {
                "type": "string",
                "description": "平台列表，逗号分隔。可选：weibo, douyin, zhihu, bilibili, xiaohongshu, kuaishou。默认 weibo,douyin,zhihu",
            },
        },
    },
    fn=_get_trending,
)


# ═══════════════════════════════════════════════════════════════
# 3. 平台内容搜索 — 来自 sentiment/core/collector.py
# ═══════════════════════════════════════════════════════════════

def _search_platform(platform: str, keyword: str, max_results: int = 10) -> list[dict]:
    """搜索指定平台上的内容（通过 JOA）。"""
    try:
        from sentiment.core.joa_client import joa_request
    except ImportError:
        return [{"error": "joa_client not available"}]

    endpoint_map = {
        "weibo": "/api/weibo/search-all/v2",
        "douyin": "/api/douyin/search-video/v4",
        "xiaohongshu": "/api/xiaohongshu/search-note/v2",
        "bilibili": "/api/bilibili/search-video/v2",
        "kuaishou": "/api/kuaishou/search-video/v2",
        "zhihu": "/api/zhihu/search/v1",
    }
    platform_lower = platform.strip().lower()
    aliases = {"小红书": "xiaohongshu", "抖音": "douyin", "微博": "weibo",
               "B站": "bilibili", "b站": "bilibili", "快手": "kuaishou", "知乎": "zhihu"}
    platform_lower = aliases.get(platform, platform_lower)

    endpoint = endpoint_map.get(platform_lower)
    if not endpoint:
        return [{"error": f"不支持的平台: {platform}"}]

    param_key = "q" if platform_lower == "weibo" else "keyword"
    try:
        data = joa_request(endpoint, {param_key: keyword, "page": 1})
        if not data:
            return []
        items = data if isinstance(data, list) else data.get("data", data.get("items", []))
        results = []
        for item in (items or [])[:max_results]:
            results.append({
                "title": item.get("title", item.get("note_card", {}).get("title", ""))[:100],
                "content": (item.get("content", item.get("text", item.get("desc", "")))[:300]),
                "likes": item.get("likes_count", item.get("digg_count", item.get("liked_count", 0))),
                "url": item.get("url", item.get("share_url", "")),
            })
        return results
    except Exception as e:
        log.warning("search_platform %s failed: %s", platform, e)
        return [{"error": str(e)}]


SEARCH_PLATFORM_TOOL = ToolDef(
    name="search_platform",
    description="搜索指定社交平台上的内容。可查看竞品怎么做、某个话题的爆款表达、用户关注什么。支持微博、抖音、小红书、B站、快手、知乎。",
    parameters={
        "type": "object",
        "properties": {
            "platform": {"type": "string", "description": "平台名（weibo/douyin/xiaohongshu/bilibili/kuaishou/zhihu）"},
            "keyword": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "返回数量，默认10"},
        },
        "required": ["platform", "keyword"],
    },
    fn=_search_platform,
)


# ═══════════════════════════════════════════════════════════════
# 4. 品牌知识 — 来自 skills/brand.py
# ═══════════════════════════════════════════════════════════════

def _get_brand_info(brand_name: str, aspect: str = "all") -> str:
    """查询品牌知识。aspect 可选：all, tone, audience, visual, cases。"""
    try:
        from skills.brand import BrandSkill
        skill = BrandSkill()
        brand = skill.load_brand(brand_name)
        if not brand:
            available = [b["name"] for b in skill.list_brands()]
            return f"未找到品牌 '{brand_name}'。可用品牌：{', '.join(available) if available else '无'}"

        if aspect == "all":
            return skill.brand_to_prompt(brand)

        aspect_map = {
            "tone": ["brand_voice", "tone", "style", "personality"],
            "audience": ["target_audience", "audience", "user_profile"],
            "visual": ["visual_style", "visual", "colors", "design_principles"],
            "cases": ["cases", "examples", "reference"],
        }
        keys = aspect_map.get(aspect, [aspect])
        parts = [f"品牌: {brand.get('name', brand_name)}"]
        for k in keys:
            if k in brand:
                val = brand[k]
                if isinstance(val, list):
                    parts.append(f"{k}: {', '.join(str(v) for v in val)}")
                elif isinstance(val, dict):
                    parts.append(f"{k}: {json.dumps(val, ensure_ascii=False, indent=2)}")
                else:
                    parts.append(f"{k}: {val}")
        return "\n".join(parts) if len(parts) > 1 else skill.brand_to_prompt(brand)
    except Exception as e:
        return f"查询品牌失败: {e}"


BRAND_INFO_TOOL = ToolDef(
    name="get_brand_info",
    description="查询品牌知识库。可获取品牌调性、目标受众、视觉风格、案例参考等。不确定品牌名时可先查 aspect='all' 看完整资料。",
    parameters={
        "type": "object",
        "properties": {
            "brand_name": {"type": "string", "description": "品牌名称"},
            "aspect": {
                "type": "string",
                "description": "查询维度：all(全部), tone(调性), audience(受众), visual(视觉), cases(案例)",
                "enum": ["all", "tone", "audience", "visual", "cases"],
            },
        },
        "required": ["brand_name"],
    },
    fn=_get_brand_info,
)


# ═══════════════════════════════════════════════════════════════
# 5. 平台运营指南 — 来自 skills/platforms.py
# ═══════════════════════════════════════════════════════════════

def _get_platform_guide(platform: str) -> str:
    """获取指定平台的运营指南（算法规则、内容规范、最佳实践）。"""
    try:
        from skills.platforms import PlatformSkill
        skill = PlatformSkill()
        return skill.get_context(platforms=[platform]) or f"未找到 {platform} 的运营指南"
    except Exception as e:
        return f"获取平台指南失败: {e}"


PLATFORM_GUIDE_TOOL = ToolDef(
    name="get_platform_guide",
    description="获取指定平台的运营指南，包括算法推荐规则、内容规范、字数限制、最佳实践、避免事项等。在为某平台写文案前务必查询。",
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "平台名（xiaohongshu/douyin/bilibili/weibo/kuaishou/zhihu）",
            },
        },
        "required": ["platform"],
    },
    fn=_get_platform_guide,
)


# ═══════════════════════════════════════════════════════════════
# 6. 文案框架 — 来自 skills/copywriting.py
# ═══════════════════════════════════════════════════════════════

def _get_copywriting_framework(name: str = "") -> str:
    """获取文案框架（AIDA/PAS/FAB/SCQA 等）。name 为空则返回所有框架概览。"""
    try:
        from skills.copywriting import CopywritingSkill
        skill = CopywritingSkill()
        return skill.get_context(framework=name) or "未找到指定框架"
    except Exception as e:
        return f"获取文案框架失败: {e}"


COPYWRITING_FRAMEWORK_TOOL = ToolDef(
    name="get_copywriting_framework",
    description="获取文案写作框架和模板。如 AIDA、PAS、FAB、SCQA、Hook-Story-Offer 等。可按名称查特定框架，或留空查所有框架概览。",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "框架名称（AIDA/PAS/FAB/SCQA/Hook-Story-Offer/4U），留空查全部",
            },
        },
    },
    fn=_get_copywriting_framework,
)


# ═══════════════════════════════════════════════════════════════
# 7. 团队决策记录 — 来自 skills/team_decisions.py
# ═══════════════════════════════════════════════════════════════

def _get_team_decisions(category: str = "") -> str:
    """获取团队历史决策和偏好记录。"""
    try:
        from skills.team_decisions import get_recent_decisions, CATEGORIES
        decisions = get_recent_decisions(limit=15, category=category)
        if not decisions:
            return "暂无团队决策记录。"
        lines = []
        for d in decisions:
            cat = CATEGORIES.get(d.get("category", ""), "其他")
            lines.append(f"- [{cat}] {d['decision']}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取团队决策失败: {e}"


TEAM_DECISIONS_TOOL = ToolDef(
    name="get_team_decisions",
    description="查询团队之前做过的重要判断和偏好，如品牌调性偏好、被否决的方向、受众认知等。生成内容前务必查询以保持一致性。",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "筛选类别：brand_tone, audience, content_pref, rejected, strategy, process。留空查全部。",
            },
        },
    },
    fn=_get_team_decisions,
)


# ═══════════════════════════════════════════════════════════════
# 8. 历史内容 — 来自 conductor/store.py
# ═══════════════════════════════════════════════════════════════

def _list_past_content(brand: str = "", limit: int = 10) -> list[dict]:
    """列出过去生成的内容，了解什么有效、什么已做过。"""
    try:
        from conductor.store import ContentStore
        store = ContentStore()
        items = store.list_all()
        if brand:
            brand_lower = brand.lower()
            items = [i for i in items if brand_lower in (i.brand or "").lower()]
        results = []
        for item in items[:limit]:
            results.append({
                "id": item.content_id,
                "title": item.title[:60],
                "brand": item.brand,
                "status": item.status,
                "quality_score": item.quality_score,
                "quality_feedback": item.quality_feedback[:100] if item.quality_feedback else "",
                "platforms": item.target_platforms,
                "hook": item.idea_hook[:60] if item.idea_hook else "",
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


PAST_CONTENT_TOOL = ToolDef(
    name="list_past_content",
    description="查看过去生成的内容列表，包括标题、品牌、状态、质量评分、使用的钩子等。用于避免重复选题和了解什么有效。",
    parameters={
        "type": "object",
        "properties": {
            "brand": {"type": "string", "description": "按品牌筛选，留空查全部"},
            "limit": {"type": "integer", "description": "返回数量，默认10"},
        },
    },
    fn=_list_past_content,
)


# ═══════════════════════════════════════════════════════════════
# 9. 用户工作上下文 — 来自 memo/store + memo/projects + core/events
# ═══════════════════════════════════════════════════════════════

def _get_user_context(scope: str = "all", *, _open_id: str = "") -> str:
    """查询用户的工作上下文：待办备忘、项目、团队近期活动。"""
    parts = []
    scopes = [scope] if scope != "all" else ["memos", "projects", "activity"]

    if "memos" in scopes:
        try:
            from memo.store import list_memos, list_threads
            memos = list_memos(limit=15, user_open_id=_open_id)
            pending = [m for m in memos if not m.get("done")]
            if pending:
                lines = [f"待办备忘（{len(pending)} 条）："]
                for i, m in enumerate(pending[:10], 1):
                    thread = m.get("thread") or ""
                    tag = f" #{thread}" if thread else ""
                    lines.append(f"  {i}. {m.get('content', '')[:60]}{tag}")
                parts.append("\n".join(lines))

            threads = list_threads(user_open_id=_open_id)
            if threads:
                thread_lines = ["工作线程："]
                for info in threads[:8]:
                    t = info["thread"]
                    latest = info.get("latest_content", "")[:40]
                    thread_lines.append(f"  #{t}（{info.get('pending', info['count'])}条待办）— {latest}")
                parts.append("\n".join(thread_lines))
        except Exception:
            pass

    if "projects" in scopes:
        try:
            from memo.projects import list_projects
            projects = list_projects()
            if projects:
                lines = ["项目（{} 个）：".format(len(projects))]
                for p in projects[:8]:
                    lines.append(f"  - {p['name']}（{p['created_at'][:10]}）")
                parts.append("\n".join(lines))
        except Exception:
            pass

    if "activity" in scopes:
        try:
            from core.events import scan
            events = scan(hours=48)
            if events:
                by_bot: dict[str, int] = {}
                for e in events:
                    by_bot[e.get("bot", "?")] = by_bot.get(e.get("bot", "?"), 0) + 1
                summary_parts = [f"{bot} {n}次" for bot, n in sorted(by_bot.items(), key=lambda x: -x[1])]
                parts.append(f"近48h团队动态：{', '.join(summary_parts)}")
                last_3 = events[-3:]
                detail = []
                for e in last_3:
                    topic = (e.get("meta") or {}).get("topic", "")
                    detail.append(f"  - [{e.get('bot', '?')}] {e.get('summary', '')}" +
                                  (f"（{topic[:30]}）" if topic else ""))
                parts.append("最近活动：\n" + "\n".join(detail))
        except Exception:
            pass

    return "\n\n".join(parts) if parts else "暂无工作上下文数据。"


def make_user_context_tool(open_id: str) -> ToolDef:
    """工厂函数：为指定用户创建一个绑定了 open_id 的上下文查询工具。"""
    def _fn(scope: str = "all") -> str:
        return _get_user_context(scope, _open_id=open_id)

    return ToolDef(
        name="get_user_context",
        description=(
            "查询当前用户的工作上下文。可获取：待办备忘和工作线程(memos)、正在管理的项目(projects)、"
            "团队近期bot活动(activity)、或全部(all)。回答用户问题前先了解他在做什么，会让回答更有针对性。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "查询范围：memos(待办备忘) / projects(项目) / activity(团队动态) / all(全部)",
                    "enum": ["memos", "projects", "activity", "all"],
                },
            },
        },
        fn=_fn,
    )


# ═══════════════════════════════════════════════════════════════
# 预定义工具集合 — 按场景分组，bot 按需选用
# ═══════════════════════════════════════════════════════════════

CONTENT_TOOLS = [
    TRENDING_TOOL,
    SEARCH_PLATFORM_TOOL,
    BRAND_INFO_TOOL,
    PLATFORM_GUIDE_TOOL,
    COPYWRITING_FRAMEWORK_TOOL,
    TEAM_DECISIONS_TOOL,
    PAST_CONTENT_TOOL,
]

RESEARCH_TOOLS = [WEB_SEARCH_TOOL, NEWS_SEARCH_TOOL, FETCH_URL_TOOL]

ALL_TOOLS = SEARCH_TOOLS + CONTENT_TOOLS
