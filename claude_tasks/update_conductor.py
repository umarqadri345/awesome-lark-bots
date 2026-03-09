# -*- coding: utf-8 -*-
"""
update_conductor.py — 更新 Conductor Bitable 中的记录状态。

用法：
    python -m claude_tasks.update_conductor <record_id> --status published
    python -m claude_tasks.update_conductor <record_id> --status failed --error "登录过期"

参数：
    record_id  — Bitable 记录 ID（如 recXXX）
    --status   — 新状态（published / failed / draft）
    --error    — 发布错误信息（仅 failed 时使用）
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

# ── 设置 Conductor bot 的飞书凭证 ──
_app_id = (os.environ.get("CONDUCTOR_FEISHU_APP_ID")
           or os.environ.get("FEISHU_APP_ID") or "")
_app_secret = (os.environ.get("CONDUCTOR_FEISHU_APP_SECRET")
               or os.environ.get("FEISHU_APP_SECRET") or "")
if _app_id:
    os.environ["FEISHU_APP_ID"] = _app_id
if _app_secret:
    os.environ["FEISHU_APP_SECRET"] = _app_secret


def _load_conductor_config() -> dict:
    cfg_path = os.path.join(_PROJECT_ROOT, "data", "bitable_conductor.json")
    if not os.path.exists(cfg_path):
        return {}
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def update_record(record_id: str, status: str, error: str = "") -> tuple[bool, str]:
    """更新 Conductor Bitable 记录。"""
    cfg = _load_conductor_config()
    app_token = cfg.get("app_token", "")
    table_id = cfg.get("table_id", "")
    if not app_token or not table_id:
        return False, "Bitable 未初始化"

    from core.feishu_client import update_bitable_record

    fields: dict = {"状态": status}
    if error:
        fields["发布错误"] = error

    ok, result = update_bitable_record(app_token, table_id, record_id, fields)
    if ok:
        return True, f"已更新记录 {record_id} → {status}"
    return False, f"更新失败: {result}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法: python -m claude_tasks.update_conductor <record_id> --status <status>",
              file=sys.stderr)
        sys.exit(1)

    record_id = args[0]

    # 解析 --status 和 --error
    status = ""
    error = ""
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--status" and i + 1 < len(argv):
            status = argv[i + 1]
        elif arg == "--error" and i + 1 < len(argv):
            error = argv[i + 1]

    if not status:
        print("缺少 --status 参数", file=sys.stderr)
        sys.exit(1)

    ok, msg = update_record(record_id, status, error)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
