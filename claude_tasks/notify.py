# -*- coding: utf-8 -*-
"""
notify.py — 通过飞书消息通知搭档。

用法：
    python3 -m claude_tasks.notify "消息内容"

消息会直接发到搭档的飞书私聊（通过助理 bot）。
"""
import os
import sys

# ── 确保项目根在 sys.path 中 ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── 加载 .env ──
_env_path = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if key and not os.environ.get(key):
                    os.environ[key] = val

# ── 设置助理 bot 的飞书凭证 ──
_app_id = (os.environ.get("ASSISTANT_FEISHU_APP_ID")
           or os.environ.get("FEISHU_APP_ID") or "")
_app_secret = (os.environ.get("ASSISTANT_FEISHU_APP_SECRET")
               or os.environ.get("FEISHU_APP_SECRET") or "")
if _app_id:
    os.environ["FEISHU_APP_ID"] = _app_id
if _app_secret:
    os.environ["FEISHU_APP_SECRET"] = _app_secret


def notify(message: str) -> tuple[bool, str]:
    """发送飞书消息通知搭档。"""
    from cal.push_target import get_push_target_open_id
    from core.feishu_client import send_message_to_user

    open_id = get_push_target_open_id()
    if not open_id:
        return False, "未找到推送目标 (data/push_target_open_id.txt 为空)"

    try:
        send_message_to_user(open_id, message)
        return True, f"已发送通知到飞书"
    except Exception as e:
        return False, f"发送失败: {e}"


def main():
    if len(sys.argv) < 2:
        print("用法: python3 -m claude_tasks.notify \"消息内容\"", file=sys.stderr)
        sys.exit(1)

    message = sys.argv[1]
    ok, msg = notify(message)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
