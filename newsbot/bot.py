# -*- coding: utf-8 -*-
"""
早知天下事飞书机器人 — 定时推送 + 手动触发。

功能：
  1. 每天早上 8:00（北京时间）自动生成日报并推送到飞书群
  2. 在飞书聊天中发消息手动触发

推送方式（按优先级）：
  - Webhook 消息卡片 → 推送到飞书群（支持 Markdown，推荐）
  - 直接消息 → 推送给指定用户

运行：python3 -m newsbot
"""

import json
import os
import random
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests as _requests
import lark_oapi as lark
from lark_oapi import EventDispatcherHandler, LogLevel

from newsbot.config import (
    NEWSBOT_FEISHU_APP_ID, NEWSBOT_FEISHU_APP_SECRET,
    NEWSBOT_FEISHU_WEBHOOK, BEIJING, log,
)
from newsbot.run import generate_report

# ── 配置 ────────────────────────────────────────────────────

SCHEDULE_HOUR = int(os.getenv("NEWSBOT_SCHEDULE_HOUR", "8"))
SCHEDULE_MINUTE = int(os.getenv("NEWSBOT_SCHEDULE_MINUTE", "0"))
NEWSBOT_PUSH_OPEN_ID = os.getenv("NEWSBOT_PUSH_OPEN_ID", "").strip()

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
_token_cache: Optional[str] = None
_token_expire_at: float = 0.0


# ── 飞书 API ────────────────────────────────────────────────

def _get_token() -> str:
    global _token_cache, _token_expire_at
    now = time.time()
    if _token_cache and _token_expire_at > now + 60:
        return _token_cache
    resp = _requests.post(
        f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": NEWSBOT_FEISHU_APP_ID, "app_secret": NEWSBOT_FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    _token_cache = data["tenant_access_token"]
    _token_expire_at = now + data.get("expire", 7200)
    return _token_cache


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def _reply_text(message_id: str, text: str) -> None:
    url = f"{FEISHU_API_BASE}/im/v1/messages/{message_id}/reply"
    body = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
    try:
        r = _requests.post(url, json=body, headers=_headers(), timeout=10)
        d = r.json()
        if d.get("code") != 0:
            log.warning("回复失败: %s", d.get("msg"))
    except Exception as e:
        log.warning("回复异常: %s", e)


def _send_text(open_id: str, text: str) -> None:
    url = f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type=open_id"
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    try:
        r = _requests.post(url, json=body, headers=_headers(), timeout=10)
        d = r.json()
        if d.get("code") != 0:
            log.warning("发送失败: %s", d.get("msg"))
    except Exception as e:
        log.warning("发送异常: %s", e)


# ── Webhook 推送（支持长文消息卡片） ─────────────────────────

MAX_CARD_SECTION_LEN = 3500
MAX_WEBHOOK_RETRIES = 2


def _webhook_send_card(title: str, markdown_body: str, color: str = "blue") -> bool:
    """
    通过 Webhook 发送消息卡片到飞书群。
    自动把长文拆分成多个 card element。
    """
    webhook_url = NEWSBOT_FEISHU_WEBHOOK
    if not webhook_url:
        log.warning("NEWSBOT_FEISHU_WEBHOOK 未设置，跳过 Webhook 推送")
        return False

    elements = _build_card_elements(markdown_body)
    card_body = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        },
    }

    for attempt in range(MAX_WEBHOOK_RETRIES + 1):
        try:
            r = _requests.post(
                webhook_url,
                json=card_body,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if r.ok:
                resp = r.json()
                if resp.get("code") == 0 or resp.get("StatusCode") == 0:
                    log.info("Webhook 推送成功: %s", title)
                    return True
                log.warning("Webhook 返回异常: %s", resp)
            else:
                log.warning("Webhook HTTP %d: %s", r.status_code, r.text[:200])
            if attempt < MAX_WEBHOOK_RETRIES and r.status_code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            break
        except Exception as e:
            log.warning("Webhook 异常: %s", e)
            if attempt < MAX_WEBHOOK_RETRIES:
                time.sleep(2)
                continue
            break
    return False


def _build_card_elements(markdown_body: str) -> list[dict]:
    """把长 Markdown 拆分成多个 card element（每段不超过限长）。"""
    sections = markdown_body.split("\n---\n")
    elements: list[dict] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= MAX_CARD_SECTION_LEN:
            elements.append({"tag": "markdown", "content": section})
            elements.append({"tag": "hr"})
        else:
            chunks = _split_markdown(section, MAX_CARD_SECTION_LEN)
            for chunk in chunks:
                elements.append({"tag": "markdown", "content": chunk})
            elements.append({"tag": "hr"})
    if elements and elements[-1].get("tag") == "hr":
        elements.pop()
    if not elements:
        elements = [{"tag": "markdown", "content": markdown_body[:MAX_CARD_SECTION_LEN]}]
    return elements


def _split_markdown(text: str, max_len: int) -> list[str]:
    """按段落边界拆分长文本。"""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_len and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _webhook_send_text(text: str) -> bool:
    """Webhook 发送纯文本（卡片放不下时的回退方案）。"""
    webhook_url = NEWSBOT_FEISHU_WEBHOOK
    if not webhook_url:
        return False
    body = {"msg_type": "text", "content": {"text": text}}
    try:
        r = _requests.post(webhook_url, json=body, headers={"Content-Type": "application/json"}, timeout=10)
        return r.ok
    except Exception:
        return False


# ── 推送日报 ────────────────────────────────────────────────

def push_report(report: str, date_str: str) -> None:
    """
    推送日报到所有配置的渠道。
    优先 Webhook 卡片 → 回退纯文本 → 直接消息。
    """
    title = f"📰 早知天下事 · {date_str}"

    if NEWSBOT_FEISHU_WEBHOOK:
        if len(report) > 30000:
            parts = _split_report_into_parts(report)
            for i, part in enumerate(parts, 1):
                part_title = f"{title} ({i}/{len(parts)})"
                ok = _webhook_send_card(part_title, part, color="blue")
                if not ok:
                    _webhook_send_text(f"{part_title}\n\n{part[:3000]}")
                time.sleep(1)
        else:
            ok = _webhook_send_card(title, report, color="blue")
            if not ok:
                _webhook_send_text(f"{title}\n\n{report[:3500]}")

    if NEWSBOT_PUSH_OPEN_ID:
        preview = report[:3500] if len(report) > 4000 else report
        _send_text(NEWSBOT_PUSH_OPEN_ID, f"{title}\n\n{preview}")


def _split_report_into_parts(report: str) -> list[str]:
    """按 --- 分隔符把日报拆成多个独立部分（华人圈/越南/亚太/欧美）。"""
    major_sections = report.split("\n---\n")
    parts: list[str] = []
    current_part: list[str] = []
    current_len = 0

    for section in major_sections:
        if current_len + len(section) > 25000 and current_part:
            parts.append("\n---\n".join(current_part))
            current_part = []
            current_len = 0
        current_part.append(section)
        current_len += len(section)

    if current_part:
        parts.append("\n---\n".join(current_part))
    return parts if parts else [report]


# ── 定时调度 ────────────────────────────────────────────────

_schedule_running = False


def _daily_job():
    """每日定时任务：生成日报并推送。"""
    log.info("=" * 60)
    log.info("定时任务启动: 早知天下事日报")
    log.info("=" * 60)
    try:
        report, path = generate_report(regions=None, with_ai=True)
        now = datetime.now(BEIJING)
        date_str = now.strftime("%Y年%m月%d日")
        push_report(report, date_str)
        log.info("定时推送完成: %s (%d 字)", path.name, len(report))
    except Exception as e:
        log.error("定时任务失败: %s\n%s", e, traceback.format_exc())
        if NEWSBOT_FEISHU_WEBHOOK:
            _webhook_send_text(f"❌ 早知天下事日报生成失败\n\n{str(e)[:500]}")


def _scheduler_loop():
    """
    简单的定时器循环：每分钟检查一次，到达目标时间时执行任务。
    避免引入额外依赖（不依赖 schedule / APScheduler）。
    """
    global _schedule_running
    _schedule_running = True
    last_run_date: Optional[str] = None

    log.info("定时调度已启动: 每天 %02d:%02d (北京时间) 自动生成日报",
             SCHEDULE_HOUR, SCHEDULE_MINUTE)

    while _schedule_running:
        try:
            now = datetime.now(BEIJING)
            today_str = now.strftime("%Y-%m-%d")
            if (now.hour == SCHEDULE_HOUR
                    and now.minute == SCHEDULE_MINUTE
                    and today_str != last_run_date):
                last_run_date = today_str
                log.info("到达推送时间 %02d:%02d，启动日报生成...", SCHEDULE_HOUR, SCHEDULE_MINUTE)
                threading.Thread(target=_daily_job, daemon=True, name="daily-digest").start()
        except Exception as e:
            log.error("调度器异常: %s", e)
        time.sleep(30)


def start_scheduler():
    """在后台线程启动定时调度。"""
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="scheduler")
    t.start()
    return t


# ── 消息处理 ────────────────────────────────────────────────

WELCOME_TEXT = """👋 你好！我是「早知天下事」热点日报机器人。

覆盖 30+ 数据源，每天早上 8:00 自动推送。

📋 可用指令：
  ➡️「日报」— 立即生成完整热点日报
  ➡️「快报」— 只采集原始热榜（更快，不含 AI 分析）
  ➡️「华人圈」— 只生成华人圈部分
  ➡️「国际」— 只生成国际部分
  ➡️「帮助」— 查看详细说明

⏰ 每天 8:00 自动推送，也可随时手动触发。"""

HELP_TEXT = """📖 早知天下事 — 使用说明

━━━ 日报生成 ━━━
  日报 / 今日热点 / 新闻    完整全球热点日报（~3-5分钟）
  快报                      只采集原始热榜（~1分钟）
  华人圈                    只生成华人圈部分
  国际                      只生成国际部分

━━━ 覆盖 30+ 数据源 ━━━
  🇨🇳 微博 · 百度 · 知乎 · B站 · 小红书 · 抖音 · 快手
  🇹🇼 PTT · Dcard
  🇭🇰 LIHKG
  🌐 Reddit · Twitter/X
  🇻🇳 VnExpress · Tuổi Trẻ · Dân Trí · Kenh14
  🇯🇵 NHK · Japan Times · Mainichi
  🇰🇷 Korea Herald · Yonhap
  🇮🇳 TOI · NDTV
  🇮🇩 Detik · Kompas
  🇺🇸 CNN · NPR · AP News
  🇬🇧 BBC · Guardian
  🇩🇪 Spiegel · Zeit
  🇫🇷 Le Monde · Le Figaro

⏰ 每天 8:00（北京时间）自动推送到群

━━━ CLI 运行 ━━━
  python3 -m newsbot.run
  python3 -m newsbot.run --region cn
  python3 -m newsbot.run --no-ai"""

_running_lock = threading.Lock()
_running_users: dict = {}


def _parse_command(text: str):
    t = text.strip().lower()
    if t in ("帮助", "help", "?", "？"):
        return "help", {}
    if t in ("hi", "hello", "你好", "开始", "start", ""):
        return "welcome", {}
    if t in ("日报", "今日热点", "新闻", "热点", "生成日报", "/日报"):
        return "full", {"regions": None, "with_ai": True}
    if t in ("快报", "原始数据", "/快报"):
        return "full", {"regions": None, "with_ai": False}
    if t in ("华人圈", "中国", "国内", "/华人圈"):
        return "full", {"regions": ["cn"], "with_ai": True}
    if t in ("国际", "海外", "世界", "/国际"):
        return "full", {"regions": ["vn", "asia", "west"], "with_ai": True}
    return None, {}


def _extract_text(content: str) -> str:
    if not content or not content.strip():
        return ""
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "text" in data:
            return (data["text"] or "").strip()
        return content.strip()
    except (json.JSONDecodeError, TypeError):
        return content.strip()


def _handle_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    log.info("收到消息事件")
    try:
        if not data.event or not data.event.message:
            return
        msg = data.event.message
        message_id = msg.message_id
        user_text = _extract_text(msg.content or "{}")
        open_id = None
        if data.event.sender and data.event.sender.sender_id:
            open_id = getattr(data.event.sender.sender_id, "open_id", None)
    except Exception as e:
        log.error("解析消息异常: %s", e)
        return

    def _respond(text_to_send: str):
        if open_id:
            _send_text(open_id, text_to_send)
        else:
            _reply_text(message_id, text_to_send)

    def _process():
        try:
            cmd, params = _parse_command(user_text)

            if cmd == "help":
                _respond(HELP_TEXT)
                return
            if cmd == "welcome" or cmd is None:
                _respond(WELCOME_TEXT)
                return

            user_key = open_id or message_id
            with _running_lock:
                if user_key in _running_users:
                    _respond(f"⏳ 正在生成中（{_running_users[user_key]}），请等待完成。")
                    return
                _running_users[user_key] = "日报生成中"

            try:
                regions = params.get("regions")
                with_ai = params.get("with_ai", True)
                ai_hint = "" if with_ai else "（快报模式，不含 AI 分析）"
                region_hint = "完整版" if not regions else "/".join(regions)

                _respond(
                    f"🚀 开始生成 {region_hint} 热点日报{ai_hint}\n\n"
                    f"⏳ 预计 {'3-5 分钟' if with_ai else '1 分钟'}，完成后发送给你。"
                )

                report, path = generate_report(regions=regions, with_ai=with_ai)
                now = datetime.now(BEIJING)
                date_str = now.strftime("%Y年%m月%d日")

                if NEWSBOT_FEISHU_WEBHOOK:
                    push_report(report, date_str)
                    _respond(f"✅ 日报已生成并推送到群！\n📄 文件: {path.name}\n📊 共 {len(report)} 字")
                else:
                    if len(report) > 4000:
                        preview = report[:3500] + f"\n\n... 全文共 {len(report)} 字，已保存到 {path.name}"
                    else:
                        preview = report
                    _respond(f"✅ 日报已生成！\n\n{preview}")
            finally:
                with _running_lock:
                    _running_users.pop(user_key, None)

        except Exception as e:
            log.error("处理异常: %s\n%s", e, traceback.format_exc())
            try:
                _respond(f"❌ 生成失败: {str(e)[:200]}\n\n发送「帮助」查看说明")
            except Exception:
                pass

    threading.Thread(target=_process, daemon=True).start()


def _handle_chat_entered(data) -> None:
    try:
        open_id = None
        if data.event and hasattr(data.event, "operator"):
            op = data.event.operator
            if op and hasattr(op, "open_id"):
                open_id = op.open_id
        if open_id:
            _send_text(open_id, WELCOME_TEXT)
    except Exception as e:
        log.warning("欢迎消息发送失败: %s", e)


# ── 启动 ────────────────────────────────────────────────────

RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300


def main():
    app_id = NEWSBOT_FEISHU_APP_ID.strip()
    app_secret = NEWSBOT_FEISHU_APP_SECRET.strip()
    if not app_id or not app_secret:
        raise SystemExit(
            "请设置环境变量 NEWSBOT_FEISHU_APP_ID 和 NEWSBOT_FEISHU_APP_SECRET\n"
            "（或复用 FEISHU_APP_ID / FEISHU_APP_SECRET）"
        )

    print("=" * 60)
    print("  早知天下事 — 全球热点日报机器人")
    print("=" * 60)
    print(f"  飞书应用: {app_id}")
    print(f"  Webhook:  {'✅ 已配置' if NEWSBOT_FEISHU_WEBHOOK else '❌ 未配置'}")
    print(f"  定时推送: 每天 {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} (北京时间)")
    print(f"  推送用户: {NEWSBOT_PUSH_OPEN_ID or '未配置（通过 Webhook 推群）'}")
    print("=" * 60)

    # 启动定时调度
    start_scheduler()

    # 启动飞书长连接
    delay = RECONNECT_INITIAL_DELAY
    attempt = 0
    while True:
        attempt += 1
        log.info("连接飞书… (第 %d 次)", attempt)
        try:
            event_handler = (
                EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(_handle_message)
                .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(_handle_chat_entered)
                .build()
            )
            cli = lark.ws.Client(
                app_id, app_secret,
                event_handler=event_handler,
                log_level=LogLevel.DEBUG,
                domain="https://open.feishu.cn",
            )
            delay = RECONNECT_INITIAL_DELAY
            cli.start()
        except Exception as e:
            log.error("连接失败: %s", e)
        wait = min(delay, RECONNECT_MAX_DELAY) + random.uniform(0, 3)
        log.info("%.1fs 后重连…", wait)
        time.sleep(wait)
        delay = min(delay * 2, RECONNECT_MAX_DELAY)


if __name__ == "__main__":
    main()
