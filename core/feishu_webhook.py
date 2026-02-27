# -*- coding: utf-8 -*-
"""
飞书群 Webhook 推送 —— 把消息发送到飞书群聊。
==============================================

Webhook 是飞书提供的「群机器人」功能：
  1. 在飞书群里添加一个自定义机器人，获得一个 Webhook URL
  2. 往这个 URL POST 消息，群里所有人就能看到

本模块负责：
  - 发送纯文本消息到群（send_text / send_planner_text）
  - 发送消息卡片到群（send_planner_card）
  - 自动重试失败的请求（最多重试 2 次）
  - 可选的签名校验（防止 URL 泄露后被滥用）

脑暴机器人的讨论过程会通过 Webhook 实时推送到飞书群，
让团队成员无需打开机器人就能看到讨论进展。
"""
import base64
import hashlib
import hmac
import os
import sys
import time

import requests

MAX_RETRIES = 2
RETRY_DELAY = 1.0


def _sign(secret: str):
    """生成 Webhook 签名（飞书安全校验：时间戳 + HMAC-SHA256）。"""
    ts = str(int(time.time()))
    string_to_sign = f"{ts}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return ts, sign


def _send(text: str, webhook_url: str, secret: str = "", strict: bool = False) -> bool:
    if not webhook_url:
        if strict:
            raise ValueError("Webhook URL is not set")
        return False

    body: dict = {"msg_type": "text", "content": {"text": text}}
    if secret:
        ts, sig = _sign(secret)
        body["timestamp"] = ts
        body["sign"] = sig

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(webhook_url, json=body, headers={"Content-Type": "application/json"}, timeout=10)
            if r.ok:
                return True
            last_err = f"{r.status_code} {r.text[:200]}"
            if attempt < MAX_RETRIES and r.status_code in (429, 500, 502, 503):
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            break
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            break

    print(f"[Webhook] 推送失败: {last_err}", file=sys.stderr, flush=True)
    if strict:
        raise RuntimeError(f"Webhook failed: {last_err}")
    return False


def send_text(text: str, *, strict: bool = False) -> bool:
    """通过 FEISHU_WEBHOOK 发送文本到脑暴飞书群。"""
    webhook = (os.environ.get("FEISHU_WEBHOOK") or "").strip()
    secret = (os.environ.get("FEISHU_SECRET") or "").strip()
    if not webhook:
        print("[Webhook] FEISHU_WEBHOOK 未设置，跳过推送", file=sys.stderr, flush=True)
        return not strict
    return _send(text, webhook, secret, strict=strict)


def send_planner_text(text: str, *, strict: bool = False) -> bool:
    """通过 PLANNER_FEISHU_WEBHOOK 发送文本到规划飞书群（未配置则回退到 FEISHU_WEBHOOK）。"""
    webhook = (os.environ.get("PLANNER_FEISHU_WEBHOOK") or "").strip()
    if not webhook:
        webhook = (os.environ.get("FEISHU_WEBHOOK") or "").strip()
    if not webhook:
        print("[Webhook] PLANNER_FEISHU_WEBHOOK 未设置，跳过推送", file=sys.stderr, flush=True)
        return not strict
    return _send(text, webhook, strict=strict)


CARD_COLORS = {
    "blue": "blue", "green": "green", "orange": "orange",
    "red": "red", "purple": "purple", "indigo": "indigo",
}


def _send_card(title: str, content: str, webhook_url: str,
               secret: str = "", color: str = "blue", strict: bool = False) -> bool:
    if not webhook_url:
        if strict:
            raise ValueError("Webhook URL is not set")
        return False

    template = CARD_COLORS.get(color, "blue")
    elements = []
    sections = content.split("\n---\n")
    for section in sections:
        section = section.strip()
        if not section:
            continue
        elements.append({"tag": "markdown", "content": section})
        elements.append({"tag": "hr"})
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()
    if not elements:
        elements = [{"tag": "markdown", "content": content}]

    body: dict = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "elements": elements,
        },
    }
    if secret:
        ts, sig = _sign(secret)
        body["timestamp"] = ts
        body["sign"] = sig

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.post(webhook_url, json=body, headers={"Content-Type": "application/json"}, timeout=10)
            if r.ok:
                return True
            last_err = f"{r.status_code} {r.text[:200]}"
            if attempt < MAX_RETRIES and r.status_code in (429, 500, 502, 503):
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            break
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            break

    print(f"[Webhook] 卡片推送失败: {last_err}", file=sys.stderr, flush=True)
    if strict:
        raise RuntimeError(f"Webhook card failed: {last_err}")
    return False


def send_planner_card(title: str, content: str, *, color: str = "blue", strict: bool = False) -> bool:
    """通过 PLANNER_FEISHU_WEBHOOK 发送消息卡片到规划飞书群。"""
    webhook = (os.environ.get("PLANNER_FEISHU_WEBHOOK") or "").strip()
    if not webhook:
        webhook = (os.environ.get("FEISHU_WEBHOOK") or "").strip()
    if not webhook:
        print("[Webhook] PLANNER_FEISHU_WEBHOOK 未设置，跳过推送", file=sys.stderr, flush=True)
        return not strict
    return _send_card(title, content, webhook, strict=strict, color=color)
