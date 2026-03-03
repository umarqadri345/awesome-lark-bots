# -*- coding: utf-8 -*-
"""
自媒体助手飞书机器人 — 通过飞书消息驱动内容全流程。

使用方式（在飞书上给机器人发消息）：

  基本用法：
    发送选题          → 会询问「脑暴」或「快速」，回复对应词后执行（可关掉：CONDUCTOR_ASK_MODE_FOR_TOPIC=0）
    脑暴：选题        → 直接走脑暴模式（5–15 分钟）
    快速：选题        → 直接快速模式（1–3 分钟）

  内容管理：
    草稿 / 草稿箱     → 查看所有草稿
    发布 <id>         → 审批通过并标记为待发布
    定时 <id> 10:00   → 设置定时发布
    删除 <id>         → 删除内容
    详情 <id>         → 查看内容详情
    状态              → 查看内容仓库统计

  配置：
    品牌 sky          → 切换品牌
    平台 小红书 抖音   → 设置目标平台
    人设 治愈系博主    → 发帖人设/口吻
    目标受众 18-30岁   → 目标受众描述
    内容目标 涨粉种草  → 内容目标
    帮助              → 查看帮助

运行：python3 -m conductor
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import threading
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import lark_oapi as lark
from lark_oapi import EventDispatcherHandler, LogLevel

from core.feishu_client import (
    reply_message, reply_card,
    send_message_to_user, send_card_to_user,
)
from conductor.config import Platform, log, load_persona_defaults
from conductor.store import store, ContentStatus
from conductor.pipeline import run_pipeline, PipelineRun
from conductor.scheduler import Scheduler


_VERIFY_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
_ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")

# ── 日志 ──────────────────────────────────────────────────────

_log_lock = threading.Lock()
_bot_log_path: Optional[str] = None


def _log(msg: str) -> None:
    line = f"[ConductorBot] {msg}"
    print(line, file=sys.stderr, flush=True)
    global _bot_log_path
    with _log_lock:
        if _bot_log_path is None:
            _bot_log_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "bot_conductor.log"
            )
        try:
            with open(_bot_log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except Exception:
            pass


# ── 飞书卡片 ──────────────────────────────────────────────────

def _card(title: str, sections: list, color: str = "blue") -> dict:
    elements = []
    for s in sections:
        if s.get("divider"):
            elements.append({"tag": "hr"})
        elif s.get("text"):
            elements.append({"tag": "markdown", "content": s["text"]})
        elif s.get("note"):
            elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": s["note"]}]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"content": title, "tag": "plain_text"}, "template": color},
        "elements": elements,
    }


# ── 会话状态 ──────────────────────────────────────────────────

_MAX_SESSIONS = 200
_sessions: OrderedDict[str, dict] = OrderedDict()
_sessions_lock = threading.Lock()
_running: dict[str, bool] = {}
_running_lock = threading.Lock()


def _get_session(user_key: str) -> dict:
    with _sessions_lock:
        if user_key in _sessions:
            _sessions.move_to_end(user_key)
            return _sessions[user_key]
        persona_def, audience_def, goals_def = load_persona_defaults()
        # 不设默认品牌：脑暴/创意阶段根据具体话题自动判断是否有对应品牌，用户可用「品牌 xxx」主动指定
        session = {
            "brand": "",
            "platforms": ["xiaohongshu"],
            "content_type": "short_video",
            "persona": persona_def,
            "target_audience": audience_def,
            "content_goals": goals_def,
            "last_run_id": None,
            "pending_topic": "",  # 提选题后等待用户选择模式（脑暴/快速）
        }
        _sessions[user_key] = session
        while len(_sessions) > _MAX_SESSIONS:
            _sessions.popitem(last=False)
        return session


def _record_team_decision(category: str, decision: str, *, source: str = "conductor"):
    """安全地记录一条团队决策（失败静默）。"""
    try:
        from skills.team_decisions import record_decision
        record_decision(category, decision, source=source)
    except Exception:
        pass


# ── 消息处理 ──────────────────────────────────────────────────

def _extract_text(content: str) -> str:
    if not content or not content.strip():
        return ""
    try:
        data = json.loads(content)
        return (data.get("text") or "").strip() if isinstance(data, dict) else content.strip()
    except (json.JSONDecodeError, TypeError):
        return content.strip()


def _handle_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    _log("收到消息事件")
    try:
        if not data.event or not data.event.message:
            return
        msg = data.event.message
        message_id = msg.message_id
        user_text = _extract_text(msg.content or "{}")
        open_id = None
        if data.event.sender and data.event.sender.sender_id:
            open_id = getattr(data.event.sender.sender_id, "open_id", None)
        _log(f"message_id={message_id!r} open_id={open_id!r} 文本={user_text[:80]!r}")
        if not user_text:
            threading.Thread(target=lambda: reply_card(message_id, _welcome_card()), daemon=True).start()
            return
    except Exception as e:
        _log(f"解析消息异常: {e}")
        return

    def _process(mid: str, text: str, uid: Optional[str]):
        user_key = uid or mid
        try:
            _dispatch(mid, text, uid, user_key)
        except Exception as e:
            _log(f"处理异常: {e}\n{traceback.format_exc()}")
            try:
                reply_message(mid, "处理出错，内部错误，请稍后重试")
            except Exception:
                pass

    threading.Thread(target=_process, args=(message_id, user_text, open_id), daemon=True).start()


def _dispatch(mid: str, text: str, uid: Optional[str], user_key: str):
    """路由消息到对应的处理函数。"""
    t = text.strip()
    lower = t.lower()
    session = _get_session(user_key)

    # ── 帮助 / 打招呼
    if lower in ("帮助", "help", "?", "？"):
        reply_card(mid, _help_card())
        return
    if lower in ("hi", "hello", "你好", "嗨", "在吗"):
        reply_card(mid, _welcome_card())
        return

    # ── 内容管理指令
    if lower in ("草稿", "草稿箱", "drafts"):
        _cmd_list_drafts(mid)
        return
    if lower in ("状态", "统计", "status"):
        _cmd_status(mid)
        return
    if lower in ("已发布", "published"):
        _cmd_list_published(mid)
        return
    if lower.startswith("详情") or lower.startswith("查看"):
        content_id = t.split(maxsplit=1)[-1].strip()
        _cmd_detail(mid, content_id)
        return
    if lower.startswith("自动发布"):
        parts = t.split()
        if len(parts) >= 3:
            _cmd_auto_publish(mid, parts[1], parts[2])
        else:
            reply_message(mid, "格式：自动发布 <内容ID> <平台>\n例：自动发布 abc123 小红书")
        return
    if lower.startswith("发布") or lower.startswith("审批"):
        content_id = t.split(maxsplit=1)[-1].strip()
        _cmd_approve(mid, content_id)
        return
    if lower.startswith("删除"):
        content_id = t.split(maxsplit=1)[-1].strip()
        _cmd_delete(mid, content_id)
        return
    if lower.startswith("定时"):
        _cmd_schedule(mid, t)
        return

    # ── 配置指令
    if lower.startswith("品牌"):
        brand = t.split(maxsplit=1)[-1].strip() if len(t.split()) > 1 else ""
        _cmd_brand(mid, user_key, brand)
        return
    if lower.startswith("平台"):
        parts = t.split()[1:] if len(t.split()) > 1 else []
        _cmd_platforms(mid, user_key, parts)
        return
    if lower.startswith("人设"):
        persona = t.split(maxsplit=1)[-1].strip() if len(t.split()) > 1 else ""
        _cmd_persona(mid, user_key, persona)
        return
    if lower.startswith("目标受众") or lower.startswith("受众"):
        audience = t.split(maxsplit=1)[-1].strip() if len(t.split()) > 1 else ""
        _cmd_target_audience(mid, user_key, audience)
        return
    if lower.startswith("内容目标") or (lower.startswith("目标") and "受众" not in t[:4]):
        goals = t.split(maxsplit=1)[-1].strip() if len(t.split()) > 1 else ""
        _cmd_content_goals(mid, user_key, goals)
        return

    # ── 已有待选选题时，用「脑暴/深度/快速/开始」确认模式
    ask_mode = os.getenv("CONDUCTOR_ASK_MODE_FOR_TOPIC", "1").strip().lower() in ("1", "true", "yes")
    pending = (session.get("pending_topic") or "").strip()
    if ask_mode and pending and lower in ("脑暴", "深度", "快速", "开始", "执行"):
        session["pending_topic"] = ""
        topic = pending
        deep_mode = lower in ("脑暴", "深度")
    elif ask_mode and pending and lower not in ("脑暴", "深度", "快速", "开始", "执行") and len(t) < 100:
        # 用户在选模式阶段补充了信息，合并到选题中重新确认
        merged = f"{pending}（{t}）"
        session["pending_topic"] = merged
        refine_text = _refine_topic_preview(merged, session)
        reply_card(mid, _card("选题已更新", [
            {"text": refine_text},
            {"divider": True},
            {"text": "回复 **脑暴** / **快速** 选择模式，或继续补充信息"},
        ], color="indigo"))
        return
    else:
        topic = None
        deep_mode = None

    # ── 内容生产（核心功能）：无待选选题时解析本条消息为选题或指令
    topic_from_pending = topic is not None
    if topic is None:
        with _running_lock:
            if _running.get(user_key):
                reply_message(mid, "上一个任务还在处理中，请稍等...")
                return
            _running[user_key] = True

        # 一步到位：脑暴/深度/快速 + 选题
        if lower.startswith("脑暴") or lower.startswith("脑暴：") or lower.startswith("深度") or lower.startswith("深度：") or lower.startswith("deep:"):
            deep_mode = True
            topic = re.sub(r'^(脑暴|深度|deep)\s*[：:]\s*', '', t, flags=re.IGNORECASE).strip()
        elif lower.startswith("快速") or lower.startswith("快速："):
            deep_mode = False
            topic = re.sub(r'^快速\s*[：:]\s*', '', t, flags=re.IGNORECASE).strip()
        else:
            # 纯选题：先帮用户结构化理解，再选模式
            if ask_mode:
                session["pending_topic"] = t
                refine_text = _refine_topic_preview(t, session)
                reply_card(mid, _card("选题确认", [
                    {"text": refine_text},
                    {"divider": True},
                    {"text": "回复 **脑暴** 或 **深度** → 脑暴讨论后生成内容（约 5–15 分钟）\n回复 **快速** 或 **开始** → 直接创意+创作（约 1–3 分钟）"},
                    {"note": "也可补充信息（如「偏休闲风」），我会更新理解后再问你"},
                ], color="indigo"))
                with _running_lock:
                    _running.pop(user_key, None)
                return
            deep_mode = os.getenv("CONDUCTOR_ALWAYS_USE_BRAINSTORM", "").lower() in ("1", "true", "yes")
            topic = t

    if topic is None:
        return

    if topic_from_pending:
        with _running_lock:
            if _running.get(user_key):
                reply_message(mid, "上一个任务还在处理中，请稍等...")
                return
            _running[user_key] = True

    mode_label = "深度模式（脑暴→creative prompt→创作）" if deep_mode else "快速模式（创意+创作）"
    # 默认直接发布；设 CONDUCTOR_AUTO_PUBLISH=false 则只存草稿
    auto_publish = os.getenv("CONDUCTOR_AUTO_PUBLISH", "true").lower() in ("1", "true", "yes")
    lines = [
        {"text": f"**主题：**{topic[:200]}"},
        {"text": f"**模式：**{mode_label}"},
        {"text": f"**品牌：**{session['brand']}  |  **平台：**{', '.join(session['platforms'])}"},
    ]
    if session.get("persona"):
        lines.append({"text": f"**人设：**{session['persona'][:80]}"})
    if session.get("target_audience"):
        lines.append({"text": f"**目标受众：**{session['target_audience'][:80]}"})
    if session.get("content_goals"):
        lines.append({"text": f"**内容目标：**{session['content_goals'][:80]}"})
    if auto_publish:
        lines.append({"text": "**自动发布：**已开启，完成后将自动发到目标平台（需已登录小红书等）"})
    lines.append({"note": f"{'深度模式预计 5-15 分钟' if deep_mode else '快速模式预计 1-3 分钟'}"})
    reply_card(mid, _card("正在启动...", lines, color="indigo"))

    def _run_pipeline():
        try:
            def on_stage(run: PipelineRun, stage):
                stage_names = {
                    "scan": "扫描热点", "ideate": "产出创意",
                    "create": "生成内容", "publish": "存储内容",
                }
                name = stage_names.get(stage.value, stage.value)
                _log(f"阶段完成: {name}")

            auto_publish = os.getenv("CONDUCTOR_AUTO_PUBLISH", "true").lower() in ("1", "true", "yes")
            run = run_pipeline(
                topic=topic,
                brand=session["brand"],
                platforms=session["platforms"],
                content_type=session["content_type"],
                deep_mode=deep_mode,
                auto_publish=auto_publish,
                persona=session.get("persona", ""),
                target_audience=session.get("target_audience", ""),
                content_goals=session.get("content_goals", ""),
                on_stage_complete=on_stage,
            )

            session["last_run_id"] = run.run_id
            card = _format_result_card(run)
            if uid:
                send_card_to_user(uid, card)
            else:
                reply_card(mid, card)
            # 生成交给最强AI的 handoff prompt
            if run.status == "completed" and run.draft:
                handoff = _build_handoff_prompt(run, topic)
                if handoff:
                    handoff_card = _card("📋 下一步：问对问题", [
                        {"text": handoff},
                        {"divider": True},
                        {"note": "🧑 人的部分 → 找对应的人确认  ·  🤖 AI的部分 → 复制给 Claude/Opus"},
                    ], color="indigo")
                    if uid:
                        send_card_to_user(uid, handoff_card)
                    else:
                        reply_card(mid, handoff_card)

            try:
                from core.events import emit as _emit_event
                _title = run.selected_idea.title[:40] if run.selected_idea else topic[:40]
                _emit_event("conductor", "pipeline_completed",
                            f"内容已生成: {_title}",
                            user_id=uid or "",
                            meta={"run_id": run.run_id, "topic": topic[:100]})
            except Exception:
                pass

        except Exception as e:
            _log(f"Pipeline 异常: {e}\n{traceback.format_exc()}")
            reply_message(mid, "Pipeline 执行出错，内部错误，请稍后重试")
        finally:
            with _running_lock:
                _running.pop(user_key, None)

    threading.Thread(target=_run_pipeline, daemon=True).start()


# ── 指令处理函数 ──────────────────────────────────────────────

def _cmd_list_drafts(mid: str):
    items = store.list_all()
    if not items:
        reply_card(mid, _card("内容仓库为空", [{"text": "还没有生成任何内容。发送一个主题开始吧！"}], color="blue"))
        return

    lines = []
    for item in items[:20]:
        status_emoji = {"draft": "📝", "ready": "✅", "scheduled": "⏰", "published": "🎉", "failed": "❌"}.get(item.status, "❓")
        time_str = time.strftime("%m/%d %H:%M", time.localtime(item.created_at))
        lines.append(f"{status_emoji} `{item.content_id}` {item.title[:30]} ({time_str})")

    reply_card(mid, _card(f"内容仓库 ({len(items)} 条)", [
        {"text": "\n".join(lines)},
        {"divider": True},
        {"note": "发送「详情 <id>」查看内容  |  发送「发布 <id>」审批通过"},
    ], color="blue"))


def _cmd_status(mid: str):
    stats = store.stats()
    total = sum(stats.values())
    lines = [f"共 **{total}** 条内容"]
    for status, count in sorted(stats.items()):
        emoji = {"draft": "📝", "ready": "✅", "scheduled": "⏰", "published": "🎉", "failed": "❌"}.get(status, "❓")
        lines.append(f"  {emoji} {status}: {count}")
    reply_card(mid, _card("内容仓库状态", [{"text": "\n".join(lines)}], color="blue"))


def _cmd_list_published(mid: str):
    items = store.list_published()
    if not items:
        reply_card(mid, _card("暂无已发布内容", [{"text": "还没有发布过内容。"}], color="blue"))
        return
    lines = [f"🎉 `{i.content_id}` {i.title[:30]}" for i in items[:20]]
    reply_card(mid, _card(f"已发布内容 ({len(items)})", [{"text": "\n".join(lines)}], color="green"))


def _cmd_detail(mid: str, content_id: str):
    item = store.get(content_id)
    if not item:
        reply_message(mid, f"未找到内容: {content_id}")
        return

    sections = [
        {"text": f"**标题：**{item.title}\n**状态：**{item.status}\n**质量分：**{item.quality_score:.2f}"},
    ]

    if item.platform_copy:
        for plat, copy in list(item.platform_copy.items())[:3]:
            sections.append({"divider": True})
            sections.append({"text": f"**{plat} 文案：**\n{copy[:500]}"})

    if item.visual_prompt:
        sections.append({"divider": True})
        sections.append({"text": f"**视觉 Prompt：**\n{item.visual_prompt[:800]}"})

    if item.visual_prompt_en:
        sections.append({"divider": True})
        sections.append({"text": f"**Seedance 英文版：**\n{item.visual_prompt_en[:500]}"})

    if item.generated_assets:
        sections.append({"divider": True})
        asset_text = f"**已生成素材：**{len(item.generated_assets)} 个\n"
        for i, asset in enumerate(item.generated_assets[:4]):
            if asset.startswith("http"):
                asset_text += f"- [素材{i+1}]({asset})\n"
            else:
                asset_text += f"- 本地文件: {asset}\n"
        sections.append({"text": asset_text})

    sections.append({"divider": True})
    cmds = (
        f"ID: {item.content_id}\n"
        f"「发布 {item.content_id}」审批通过\n"
        f"「自动发布 {item.content_id} 小红书」浏览器自动发\n"
        f"「定时 {item.content_id} 10:00」定时发布"
    )
    sections.append({"note": cmds})

    reply_card(mid, _card(f"内容详情: {item.title[:30]}", sections, color="blue"))


def _cmd_approve(mid: str, content_id: str):
    if store.approve(content_id):
        reply_card(mid, _card("审批通过", [{"text": f"内容 `{content_id}` 已标记为待发布 ✅"}], color="green"))
    else:
        reply_message(mid, f"审批失败：内容 {content_id} 不存在或状态不是草稿")


def _cmd_delete(mid: str, content_id: str):
    if store.delete(content_id):
        reply_card(mid, _card("已删除", [{"text": f"内容 `{content_id}` 已删除 🗑"}], color="orange"))
    else:
        reply_message(mid, f"删除失败：内容 {content_id} 不存在")


def _cmd_schedule(mid: str, text: str):
    parts = text.split()
    if len(parts) < 3:
        reply_message(mid, "格式：定时 <内容ID> <时间>\n例：定时 abc123 10:00\n例：定时 abc123 2026-03-01 10:00")
        return

    content_id = parts[1]
    time_str = " ".join(parts[2:])

    try:
        now = datetime.now()
        if re.match(r'^\d{1,2}:\d{2}$', time_str):
            h, m = map(int, time_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
        elif re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}$', time_str):
            target = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        else:
            reply_message(mid, f"时间格式不对：{time_str}\n支持格式：10:00 或 2026-03-01 10:00")
            return

        ts = target.timestamp()
        if store.schedule(content_id, ts):
            reply_card(mid, _card("定时发布已设置", [
                {"text": f"内容 `{content_id}` 将在 **{target.strftime('%Y-%m-%d %H:%M')}** 发布 ⏰"},
            ], color="green"))
        else:
            reply_message(mid, f"设置失败：内容 {content_id} 不存在或状态不允许")
    except Exception as e:
        _log(f"定时发布时间解析失败: {e}\n{traceback.format_exc()}")
        reply_message(mid, "时间解析失败，请检查格式。\n支持格式：10:00 或 2026-03-01 10:00")


def _cmd_auto_publish(mid: str, content_id: str, platform: str):
    """通过浏览器自动化发布到社交媒体。"""
    reply_card(mid, _card("正在发布...", [
        {"text": f"内容 `{content_id}` → **{platform}**"},
        {"note": "通过浏览器自动化发布，请确保已登录目标平台"},
    ], color="indigo"))

    def _do_publish():
        try:
            from conductor.stages.publisher import publish_content
            result = publish_content(content_id, platform)
            if result.success:
                reply_card(mid, _card("发布成功", [
                    {"text": f"内容 `{content_id}` 已发布到 **{platform}**"},
                    {"text": f"链接：{result.post_url}" if result.post_url else ""},
                ], color="green"))
            else:
                reply_card(mid, _card("发布失败", [
                    {"text": f"错误：{result.error}"},
                ], color="red"))
        except Exception as e:
            reply_message(mid, "发布出错，内部错误，请稍后重试")

    threading.Thread(target=_do_publish, daemon=True).start()


def _cmd_brand(mid: str, user_key: str, brand: str):
    session = _get_session(user_key)
    if not brand:
        current = session["brand"] or "（未设置）"
        reply_card(mid, _card("当前品牌", [{"text": f"当前品牌：**{current}**\n\n切换：发送「品牌 品牌名」"}], color="purple"))
        return
    session["brand"] = brand
    _record_team_decision("brand_tone", f"当前使用品牌：{brand}", source="conductor")
    reply_card(mid, _card("品牌已切换", [{"text": f"当前品牌：**{brand}**"}], color="green"))


def _cmd_platforms(mid: str, user_key: str, parts: list[str]):
    session = _get_session(user_key)
    if not parts:
        plats = ", ".join(session["platforms"])
        reply_card(mid, _card("当前目标平台", [
            {"text": f"当前平台：**{plats}**\n\n切换：发送「平台 小红书 抖音」"},
            {"text": "支持：小红书、抖音、B站、微博、快手、知乎"},
        ], color="purple"))
        return

    new_plats = []
    for p in parts:
        parsed = Platform.from_str(p)
        if parsed:
            new_plats.append(parsed.value)
    if new_plats:
        session["platforms"] = new_plats
        reply_card(mid, _card("平台已切换", [{"text": f"目标平台：**{', '.join(new_plats)}**"}], color="green"))
    else:
        reply_message(mid, f"未识别的平台名。支持：小红书、抖音、B站、微博、快手、知乎")


def _cmd_persona(mid: str, user_key: str, persona: str):
    session = _get_session(user_key)
    if not persona:
        current = session.get("persona") or "（未设置，使用默认）"
        reply_card(mid, _card("发帖人设", [
            {"text": f"当前人设：**{current}**"},
            {"note": "示例：人设 治愈系旅行博主，语气温暖、爱用 emoji"},
        ], color="purple"))
        return
    session["persona"] = persona
    _record_team_decision("brand_tone", f"发帖人设：{persona}", source="conductor")
    reply_card(mid, _card("人设已设置", [{"text": f"**{persona[:80]}**"}], color="green"))


def _cmd_target_audience(mid: str, user_key: str, audience: str):
    session = _get_session(user_key)
    if not audience:
        current = session.get("target_audience") or "（未设置）"
        reply_card(mid, _card("目标受众", [
            {"text": f"当前目标受众：**{current}**"},
            {"note": "示例：目标受众 18-30岁一二线女性，喜欢生活方式与美妆"},
        ], color="purple"))
        return
    session["target_audience"] = audience
    _record_team_decision("audience", f"目标受众：{audience}", source="conductor")
    reply_card(mid, _card("目标受众已设置", [{"text": f"**{audience[:80]}**"}], color="green"))


def _cmd_content_goals(mid: str, user_key: str, goals: str):
    session = _get_session(user_key)
    if not goals:
        current = session.get("content_goals") or "（未设置）"
        reply_card(mid, _card("内容目标", [
            {"text": f"当前内容目标：**{current}**"},
            {"note": "示例：内容目标 涨粉、种草、品牌曝光"},
        ], color="purple"))
        return
    session["content_goals"] = goals
    _record_team_decision("strategy", f"内容目标：{goals}", source="conductor")
    reply_card(mid, _card("内容目标已设置", [{"text": f"**{goals[:80]}**"}], color="green"))


# ── 结果格式化 ────────────────────────────────────────────────

def _refine_topic_preview(topic: str, session: dict) -> str:
    """快速结构化用户的选题输入，帮用户确认理解是否正确。"""
    brand = session.get("brand") or "（未指定）"
    platforms = ", ".join(session.get("platforms", ["xiaohongshu"]))
    persona = session.get("persona", "")
    audience = session.get("target_audience", "")

    try:
        from core.llm import chat_completion
        result = chat_completion(
            provider="deepseek",
            system=(
                "用户给了一个自媒体内容选题，请用 3-4 行帮他确认你的理解。格式：\n"
                "**选题：**一句话总结\n"
                "**内容方向：**你理解的内容切入点\n"
                "**建议补充：**如果有模糊的地方，列 1-2 个简短问题（如「偏哪种风格？」）\n"
                "不要写长文，控制在 100 字以内。只输出结构化内容，不要解释。"
            ),
            user=f"选题：{topic[:200]}\n平台：{platforms}\n品牌：{brand}",
            temperature=0.3,
        ).strip()
        if result and len(result) > 10:
            return result
    except Exception:
        pass
    return (
        f"**选题：**{topic[:200]}\n"
        f"**平台：**{platforms}  |  **品牌：**{brand}\n"
        + (f"**人设：**{persona[:60]}\n" if persona else "")
        + (f"**受众：**{audience[:60]}\n" if audience else "")
    )


def _build_handoff_prompt(run: PipelineRun, topic: str) -> str:
    """从内容生成结果中提炼：需要人判断的问题 + 可交给AI优化的 prompt。"""
    if not run.draft:
        return ""
    idea = run.selected_idea
    draft = run.draft
    first_copy = ""
    if draft.platform_copy:
        first_plat = list(draft.platform_copy.keys())[0]
        first_copy = draft.platform_copy[first_plat][:600]

    title = idea.title if idea else topic[:60]
    angle = idea.angle if idea else "—"
    hook = idea.hook if idea else "—"
    score = f"{draft.quality_score:.0%}"
    feedback = draft.quality_feedback

    return (
        f"**🧑 需要人来判断：**\n"
        f"1. [审批人] 这条内容的调性对吗？标题「{title[:30]}」和品牌形象一致吗？\n"
        f"2. [了解受众的人] 钩子「{hook[:40]}」能让目标受众停下来吗？有没有更贴近他们痛点的说法？\n"
        f"3. [发布负责人] 发布时间定什么时候？要配什么话题标签蹭热度？\n"
        f"\n**🤖 交给AI优化（可直接复制）：**\n"
        f"我们为「{topic[:80]}」生成了一条自媒体内容，请帮优化。\n"
        f"创意：{title} / 角度：{angle} / 钩子：{hook}\n"
        f"文案：{first_copy[:400]}\n"
        f"AI自评：{score}，{feedback}\n"
        f"请从受众视角评估吸引力，指出文案最弱部分并改写，给3个替代钩子。"
    )


def _format_result_card(run: PipelineRun) -> dict:
    if run.status == "failed":
        _log(f"Pipeline 执行失败: {run.error}")
        return _card("Pipeline 执行失败", [
            {"text": "内部错误，请稍后重试。"},
            {"note": "检查 API 配置后重试"},
        ], color="red")

    sections = []

    if run.selected_idea:
        idea = run.selected_idea
        sections.append({"text": (
            f"**选中创意：**{idea.title}\n"
            f"**切入角度：**{idea.angle}\n"
            f"**开头钩子：**{idea.hook}\n"
            f"**预估吸引力：**{idea.estimated_appeal:.0%}"
        )})

    if run.ideas and len(run.ideas) > 1:
        sections.append({"divider": True})
        others = "\n".join(f"- {i.title} ({i.estimated_appeal:.0%})" for i in run.ideas[:5] if i != run.selected_idea)
        if others:
            sections.append({"text": f"**其他候选创意：**\n{others}"})

    if run.draft:
        sections.append({"divider": True})
        quality = f"{'🟢' if run.draft.quality_score >= 0.7 else '🟡' if run.draft.quality_score >= 0.5 else '🔴'} {run.draft.quality_score:.0%}"
        sections.append({"text": f"**内容质量：**{quality}\n{run.draft.quality_feedback}"})

        if run.draft.platform_copy:
            first_plat = list(run.draft.platform_copy.keys())[0]
            first_copy = run.draft.platform_copy[first_plat]
            sections.append({"divider": True})
            sections.append({"text": f"**{first_plat} 文案预览：**\n{first_copy[:300]}{'...' if len(first_copy) > 300 else ''}"})

        if run.draft.visual_prompt_en:
            sections.append({"divider": True})
            sections.append({"text": f"**Seedance 英文 Prompt：**\n{run.draft.visual_prompt_en[:300]}"})

    content_id = ""
    if run.publish_results:
        for r in run.publish_results:
            if r.post_id:
                content_id = r.post_id
                break

    sections.append({"divider": True})
    next_steps = "**接下来你可以：**\n"
    if content_id:
        next_steps += f"- 发送「详情 {content_id}」查看完整内容\n"
        next_steps += f"- 发送「发布 {content_id}」审批通过\n"
        next_steps += f"- 发送「自动发布 {content_id} 小红书」浏览器自动发\n"
        next_steps += f"- 发送「定时 {content_id} 10:00」定时发布\n"
    next_steps += "- 发送新主题继续生产\n"
    next_steps += "- 发送「草稿」查看所有内容\n"
    topic_short = run.selected_idea.title[:40] if run.selected_idea else ""
    if topic_short:
        next_steps += f"\n**💡 跨 Bot 联动：**\n"
        next_steps += f"- 去「助理bot」发「备忘 跟进{topic_short}发布效果」→ 设提醒\n"
        next_steps += f"- 去「舆情监控」发「{topic_short}」→ 追踪传播效果"
    sections.append({"text": next_steps})

    sections.append({"note": f"run_id: {run.run_id}  |  耗时: {run.elapsed_sec():.0f}s  |  状态: {run.status}"})

    status_color = {"completed": "green", "paused": "orange", "failed": "red"}.get(run.status, "blue")
    return _card(f"内容已生成: {run.selected_idea.title[:30] if run.selected_idea else '完成'}", sections, color=status_color)


# ── 欢迎/帮助卡片 ─────────────────────────────────────────────

def _welcome_card() -> dict:
    return _card("Hi! 我是自媒体助手", [
        {"text": (
            "发一个**选题**，我会先让你选是否走脑暴，再执行：\n"
            "**扫描热点** → **创意/脑暴** → **生成文案+视觉** → **存到内容仓库**"
        )},
        {"text": (
            "**提选题后可选模式：**\n"
            "> 春天穿搭分享\n"
            "> 机器人会问：脑暴 or 快速？回复「脑暴」或「快速」即可\n\n"
            "**一步到位：**\n"
            "> 脑暴：咖啡品牌 × 音乐节联动  → 直接走脑暴\n"
            "> 快速：春天穿搭分享  → 直接快速执行"
        )},
        {"divider": True},
        {"text": (
            "**内容管理：**草稿 / 详情 / 发布 / 定时 / 删除\n"
            "**配置：**品牌 / 平台 / 人设 / 目标受众 / 内容目标\n"
            "**查看帮助：**发送「帮助」"
        )},
    ], color="turquoise")


def _help_card() -> dict:
    return _card("使用帮助", [
        {"text": (
            "**内容生产（提选题时可选是否脑暴）：**\n"
            "- 发选题（如「春天穿搭」）→ 会问选**脑暴**还是**快速**，回复对应词即可\n"
            "- 一步到位：发「**脑暴：**选题」或「**快速：**选题」直接执行\n"
            "- 脑暴模式约 5–15 分钟，快速模式约 1–3 分钟\n"
        )},
        {"text": (
            "**内容管理：**\n"
            "- 「**草稿**」→ 查看所有内容\n"
            "- 「**详情** <id>」→ 查看完整内容（文案+Prompt+素材）\n"
            "- 「**发布** <id>」→ 审批通过\n"
            "- 「**自动发布** <id> 小红书」→ 通过浏览器自动发布\n"
            "- 「**定时** <id> 10:00」→ 设置定时发布\n"
            "- 「**删除** <id>」→ 删除内容\n"
            "- 「**状态**」→ 仓库统计\n"
        )},
        {"text": (
            "**配置：**\n"
            "- 「**品牌** sky」→ 切换品牌\n"
            "- 「**平台** 小红书 抖音」→ 设置目标平台\n"
            "- 「**人设** 治愈系旅行博主」→ 发帖口吻/风格\n"
            "- 「**目标受众** 18-30岁女性」→ 目标受众\n"
            "- 「**内容目标** 涨粉种草」→ 内容目标\n"
        )},
        {"divider": True},
        {"note": "LLM: DeepSeek  |  品牌/平台可在对话中设置"},
    ], color="blue")


# ── 长连接启动 ────────────────────────────────────────────────

RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300
RECONNECT_MULTIPLIER = 2


def _handle_bot_entered(data) -> None:
    _log("用户打开了与自媒体助手的单聊")
    try:
        open_id = None
        if hasattr(data, "event") and data.event:
            op = getattr(data.event, "operator", None) or getattr(data.event, "user_id", None)
            if op:
                open_id = getattr(op, "open_id", None)
            if not open_id:
                op_id = getattr(data.event, "operator_id", None)
                if op_id:
                    open_id = getattr(op_id, "open_id", None)
        if open_id:
            send_card_to_user(open_id, _welcome_card())
    except Exception as e:
        _log(f"发送欢迎消息异常: {e}")


def _handle_message_read(_data) -> None:
    pass


def _run_client(app_id: str, app_secret: str) -> None:
    event_handler = (
        EventDispatcherHandler.builder(_VERIFY_TOKEN, _ENCRYPT_KEY)
        .register_p2_im_message_receive_v1(_handle_message)
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(_handle_bot_entered)
        .register_p2_im_message_message_read_v1(_handle_message_read)
        .build()
    )
    cli = lark.ws.Client(
        app_id, app_secret,
        event_handler=event_handler,
        log_level=LogLevel.DEBUG,
        domain="https://open.feishu.cn",
    )
    cli.start()


def main():
    # 只用自媒体助手专用凭证，禁止回退到 FEISHU_APP_ID，否则会和脑暴机器人共用同一 app 导致「打开脑暴单聊时收到两个欢迎卡片」
    app_id = (os.environ.get("CONDUCTOR_FEISHU_APP_ID") or "").strip()
    app_secret = (os.environ.get("CONDUCTOR_FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        print(file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("  自媒体助手需要飞书应用凭证才能连接飞书", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("  请在 .env 中配置（必须使用自媒体助手自己的应用）：", file=sys.stderr)
        print("    CONDUCTOR_FEISHU_APP_ID=你的AppID", file=sys.stderr)
        print("    CONDUCTOR_FEISHU_APP_SECRET=你的AppSecret", file=sys.stderr)
        print("  不要复用 FEISHU_APP_ID（那是脑暴用的），否则会和脑暴共用一个 app 导致双欢迎卡片。", file=sys.stderr)
        print("  获取方式：飞书开放平台 https://open.feishu.cn/app → 创建应用 → 凭证与基础信息", file=sys.stderr)
        print("  详细步骤见：conductor/FEISHU_SETUP.md", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        raise SystemExit(1)

    # TODO: 传递凭证应通过配置对象而非修改全局环境变量，同进程多机器人时会冲突
    os.environ["FEISHU_APP_ID"] = app_id
    os.environ["FEISHU_APP_SECRET"] = app_secret

    _log("自媒体助手启动")
    print("=" * 60)
    print("AIlarkteams 自媒体助手（长连接模式）")
    print()
    print("使用方式：在飞书上给机器人发消息，输入主题即可。")
    print("  例：春天穿搭分享")
    print("  例：深度：咖啡品牌 × 音乐节联动")
    print()
    print("机器人会自动：扫描热点 → 产出创意 → 生成内容 → 存储到仓库")
    print("你可以随时查看草稿、审批发布、设置定时发布。")
    print("=" * 60)

    # 启动定时调度器
    scheduler = Scheduler()
    scheduler.start()

    delay = RECONNECT_INITIAL_DELAY
    attempt = 0
    while True:
        attempt += 1
        _log(f"正在连接飞书… (第 {attempt} 次)")
        try:
            _run_client(app_id, app_secret)
            _log("飞书长连接已断开，将自动重连")
        except Exception as e:
            _log(f"连接失败: {e}")
            if attempt == 1:
                print("\n若持续失败，请检查：", file=sys.stderr)
                print("  1. FEISHU_APP_ID / FEISHU_APP_SECRET 是否正确", file=sys.stderr)
                print("  2. 应用是否已发布并启用", file=sys.stderr)
        wait = min(delay, RECONNECT_MAX_DELAY) + random.uniform(0, 5)
        _log(f"{wait:.1f} 秒后重连…")
        time.sleep(wait)
        delay = min(delay * RECONNECT_MULTIPLIER, RECONNECT_MAX_DELAY)


if __name__ == "__main__":
    main()
