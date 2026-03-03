# -*- coding: utf-8 -*-
"""
飞书文档读取模块 —— 从用户消息中检测飞书链接并拉取文档内容。

支持：
  - 飞书云文档 (feishu.cn/docx/{id})
  - 飞书知识库 Wiki (feishu.cn/wiki/{token})
  - larkoffice.com 域名

长文档（>15000 字符）自动使用 Kimi 128K 做结构化摘要。
"""
import re
from typing import Optional

_FEISHU_DOC_RE = re.compile(
    r'(?:feishu\.cn|larkoffice\.com)/(?P<type>docx|wiki)/(?P<token>[a-zA-Z0-9_-]{10,})',
)


def extract_feishu_doc_urls(text: str) -> list[dict]:
    """从文本中提取所有飞书文档/Wiki 链接。

    Returns: [{"type": "docx"|"wiki", "token": str}, ...]
    """
    if not text:
        return []
    seen = set()
    results = []
    for m in _FEISHU_DOC_RE.finditer(text):
        token = m.group("token")
        if token in seen:
            continue
        seen.add(token)
        results.append({"type": m.group("type"), "token": token})
    return results


def fetch_feishu_doc(doc_type: str, token: str) -> tuple[bool, str, str]:
    """拉取单个飞书文档内容。

    Returns: (ok, content, title)
    """
    from core.feishu_client import read_document_content, get_wiki_node_info

    if doc_type == "wiki":
        ok, info = get_wiki_node_info(token)
        if not ok:
            return False, info.get("error", "Wiki 节点解析失败"), ""
        obj_token = info.get("obj_token", "")
        obj_type = info.get("obj_type", "")
        title = info.get("title", "")
        if not obj_token:
            return False, "Wiki 节点无 obj_token", title
        if obj_type not in ("docx", "doc", ""):
            return False, f"Wiki 节点类型 {obj_type} 暂不支持读取", title
        ok2, content = read_document_content(obj_token)
        return ok2, content, title
    else:
        ok, content = read_document_content(token)
        return ok, content, ""


def fetch_docs_from_text(text: str, max_total_chars: int = 80000) -> tuple[str, list[str]]:
    """从文本中检测飞书链接，逐个拉取并拼接内容。

    Returns: (combined_content, list_of_titles_or_summaries)
    """
    urls = extract_feishu_doc_urls(text)
    if not urls:
        return "", []

    parts: list[str] = []
    titles: list[str] = []
    total_len = 0

    for i, item in enumerate(urls):
        if total_len >= max_total_chars:
            break
        ok, content, title = fetch_feishu_doc(item["type"], item["token"])
        if not ok:
            print(f"  [文档读取] {item['type']}/{item['token'][:12]}... 失败: {content[:80]}", flush=True)
            titles.append(f"(读取失败) {title or item['token'][:12]}")
            continue
        if not content.strip():
            print(f"  [文档读取] {item['type']}/{item['token'][:12]}... 内容为空", flush=True)
            continue

        label = title or f"文档{i+1}"
        remaining = max_total_chars - total_len
        if len(content) > remaining:
            content = content[:remaining] + f"\n\n[文档内容截断，原文约 {len(content)} 字符]"

        parts.append(f"━━ {label} ━━\n{content}")
        titles.append(f"{label}（{len(content)}字）")
        total_len += len(content)
        print(f"  [文档读取] {label}: {len(content)} 字符", flush=True)

    return "\n\n".join(parts), titles


def summarize_long_doc(content: str, topic: str) -> str:
    """长文档用 Kimi 128K 做结构化摘要，短文档原样返回。"""
    if not content or len(content) <= 15000:
        return content
    try:
        from core.llm import chat_completion
        print(f"  [文档摘要] 文档 {len(content)} 字符，使用 Kimi 压缩...", flush=True)
        system = (
            "你是文档摘要专家。你的任务是为一场即将开始的讨论提取文档中最有价值的信息。\n"
            "保留：核心结论、关键数据/数字、重要论据、具体案例、趋势判断、关键对比。\n"
            "去掉：格式废话、重复内容、套话铺垫、冗长的方法论描述。\n"
            "输出中文纯文本，用清晰的段落和小标题组织，控制在 8000-10000 字以内。\n"
            "宁可多保留一些有信息量的细节，也不要过度压缩导致讨论时缺少素材。"
        )
        user = (
            f"以下文档将用于关于「{topic}」的深度讨论/脑暴。"
            f"请提取与此话题最相关的信息，保留具体数据和关键洞察。\n\n"
            f"{content[:120000]}"
        )
        result = chat_completion(provider="kimi", system=system, user=user)
        if result and len(result.strip()) > 100:
            print(f"  [文档摘要] 压缩完成：{len(content)} → {len(result)} 字符", flush=True)
            return result.strip()
        return content[:15000] + f"\n\n[原文约 {len(content)} 字符，摘要失败，已截断]"
    except Exception as e:
        print(f"  [文档摘要] Kimi 摘要失败: {e}，回退截断", flush=True)
        return content[:15000] + f"\n\n[原文约 {len(content)} 字符，已截断]"
