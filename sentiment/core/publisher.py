# -*- coding: utf-8 -*-
"""
报告生成 & 飞书推送模块。
"""

import re
from datetime import timedelta, datetime

import requests
from sentiment.config.settings import FEISHU_WEBHOOK_URL, BEIJING, log


def _range_for_days(days: int):
    now = datetime.now(BEIJING)
    end_dt = (now - timedelta(days=1)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    start_dt = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start_dt, end_dt


def generate_report(kimi_text: str, stats: dict, profile: dict) -> str:
    start_dt, end_dt = _range_for_days(profile["days"])
    keywords = profile["keywords"]
    title = profile["title"]
    header = (
        f"{title}\n"
        f"📅 {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}\n\n"
        f"📊 数据概况\n"
        f"• 采集帖子：{stats['total']} 条\n"
        f"• 覆盖平台：{', '.join(p for p, _ in stats['platform'].most_common())}\n"
        f"• 监测关键词：{', '.join(keywords)}\n\n"
        f"---\n\n"
    )
    return header + kimi_text


def _format_report_for_feishu(report: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", report)
    text = re.sub(r"\n(## )", r"\n\n\1", text)
    text = re.sub(r"\n(### )", r"\n\n\1", text)
    text = re.sub(r"(\n)(---)(\n)", r"\n\n\2\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_to_feishu(message: str):
    if not FEISHU_WEBHOOK_URL:
        log.warning("FEISHU_WEBHOOK_URL 未设置，跳过飞书推送")
        return
    message = _format_report_for_feishu(message)
    payload = {"msg_type": "text", "content": {"text": message}}
    try:
        resp = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            log.info("飞书推送成功")
        else:
            log.warning("飞书推送返回: %s", result)
    except Exception as exc:
        log.error("飞书推送失败: %s", exc)
