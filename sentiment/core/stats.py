# -*- coding: utf-8 -*-
"""
统计计算模块 — 平台分布、词频、情绪分类。
"""

import re
from collections import Counter
from sentiment.config.settings import POS_KW, NEG_KW, STOP_WORDS


def compute_stats(posts: list[dict]) -> dict:
    plat_counts = Counter(p["platform"] for p in posts)

    all_text = " ".join(p["content"] for p in posts)
    try:
        import jieba
        words = [w for w in jieba.cut(all_text) if len(w) >= 2]
    except ImportError:
        words = re.findall(r"[\u4e00-\u9fff]{2,4}", all_text)

    word_freq = Counter(
        w for w in words if w.lower() not in STOP_WORDS and len(w) >= 2
    )

    pos = neg = 0
    for p in posts:
        t = p["content"]
        hit_pos = any(w in t for w in POS_KW)
        hit_neg = any(w in t for w in NEG_KW)
        if hit_pos and not hit_neg:
            pos += 1
        elif hit_neg and not hit_pos:
            neg += 1
    neu = len(posts) - pos - neg

    game_kw = "版本 更新 活动 赛季 季节 任务 地图 玩法 礼包 复刻 剧情 先祖 光之翼 新"
    game_words = set(game_kw.split())
    game_related = sum(1 for p in posts if any(w in p.get("content", "") for w in game_words))

    return {
        "platform": plat_counts,
        "top_words": word_freq.most_common(30),
        "sentiment": {"正面": pos, "中性": neu, "负面": neg},
        "total": len(posts),
        "game_related": game_related,
    }


def stats_text(stats: dict) -> str:
    lines = ["- 平台分布："]
    for plat, cnt in stats["platform"].most_common():
        lines.append(f"  {plat}：{cnt}")

    lines.append("")
    lines.append("- 高频词（Top 30，用于识别热议话题）：")
    for i, (word, cnt) in enumerate(stats["top_words"], 1):
        lines.append(f"  {i}. {word}（{cnt}）")
    total = stats["total"] or 1
    gr = stats.get("game_related", 0)
    lines.append("")
    lines.append(f"- 与游戏内容相关的讨论条数（含版本/活动/赛季/任务等）：{gr} 条（{gr/total*100:.1f}%）")

    lines.append("")
    s = stats["sentiment"]
    lines.append("- 情绪粗分布：")
    for label in ("正面", "中性", "负面"):
        cnt = s[label]
        pct = cnt / total * 100
        lines.append(f"  {label}：{cnt} 条（{pct:.1f}%）")

    return "\n".join(lines)
