# -*- coding: utf-8 -*-
"""
complete_task.py — 将 Claude 处理结果回写到飞书 Bitable 看板。

用法：
    python -m claude_tasks.complete_task <record_id> <备注内容>
    python -m claude_tasks.complete_task <record_id> <备注内容> --done

参数：
    record_id  — Bitable 记录 ID（如 recXXX）
    备注内容    — Claude 的处理结果摘要
    --done     — 同时将状态标记为「已完成」

示例：
    python -m claude_tasks.complete_task recAbC123 "已完成竞品定价分析，报告见 /docs/pricing.md"
    python -m claude_tasks.complete_task recAbC123 "需要搭档确认：有两个方案待选"
    python -m claude_tasks.complete_task recAbC123 "已生成周报草稿" --done
"""
import json
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


def _load_board_config() -> dict:
    cfg_path = os.path.join(_PROJECT_ROOT, "data", "bitable_board.json")
    if not os.path.exists(cfg_path):
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def update_task(
    record_id: str,
    note: str,
    mark_done: bool = False,
    clear_feedback: bool = False,
) -> tuple[bool, str]:
    """更新看板记录的 Claude备注 字段。

    Args:
        record_id: Bitable 记录 ID
        note: Claude 处理结果摘要
        mark_done: 是否同时将状态设为「已完成」
        clear_feedback: 是否清空搭档反馈字段（处理完反馈后）

    Returns: (ok, message)
    """
    cfg = _load_board_config()
    app_token = cfg.get("app_token", "")
    table_id = cfg.get("table_id", "")
    if not app_token or not table_id:
        return False, "看板未初始化"

    from core.feishu_client import update_bitable_record

    fields: dict = {"Claude备注": note}
    if mark_done:
        fields["状态"] = "已完成"
        fields["分区"] = "已完成"
    if clear_feedback:
        fields["搭档反馈"] = ""

    ok, result = update_bitable_record(app_token, table_id, record_id, fields)
    if ok:
        return True, f"已更新记录 {record_id}"
    return False, f"更新失败: {result}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if len(args) < 2:
        print("用法: python -m claude_tasks.complete_task <record_id> <备注> [--done]",
              file=sys.stderr)
        sys.exit(1)

    record_id = args[0]
    note = args[1]
    mark_done = "--done" in flags
    clear_feedback = "--clear-feedback" in flags

    ok, msg = update_task(record_id, note, mark_done=mark_done, clear_feedback=clear_feedback)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
