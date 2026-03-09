# -*- coding: utf-8 -*-
"""
query_conductor.py — 查询 Conductor Bitable 中待发布的内容。

用法：
    python -m claude_tasks.query_conductor          # 输出 JSON
    python -m claude_tasks.query_conductor --pretty  # 格式化输出

输出 JSON 格式：
    {
      "ready": [...],      # 状态=ready 的任务
      "scheduled": [...]   # 状态=scheduled 且已到时间的任务
    }

退出码：
    0 — 成功
    1 — 配置缺失或 API 错误
"""
import json
import os
import sys
from datetime import datetime

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


def _query_records(app_token: str, table_id: str, status_filter: str) -> list[dict]:
    """查询指定状态的 Conductor 记录。"""
    from core.feishu_client import list_bitable_records

    filter_expr = f'CurrentValue.[状态]="{status_filter}"'
    ok, records = list_bitable_records(app_token, table_id, filter_expr=filter_expr)
    if not ok:
        print(f"[query_conductor] 查询失败 (status={status_filter}): {records}",
              file=sys.stderr)
        return []
    return records or []


def _record_to_task(rec: dict) -> dict:
    """将 Bitable 记录转为任务字典。"""
    f = rec.get("fields") or {}
    return {
        "record_id": rec.get("record_id", ""),
        "content_id": f.get("content_id", ""),
        "title": f.get("标题", ""),
        "topic": f.get("话题", ""),
        "brand": f.get("品牌", ""),
        "platform_copy": f.get("平台文案", ""),
        "hashtags": f.get("话题标签", ""),
        "target_platform": f.get("目标平台", ""),
        "assets": f.get("素材链接", ""),
        "status": f.get("状态", ""),
        "scheduled_time": f.get("定时发布时间", ""),
        "created": f.get("创建时间", ""),
    }


def query() -> dict:
    """查询 Conductor Bitable，返回 ready 和 scheduled 任务。"""
    cfg = _load_conductor_config()
    app_token = cfg.get("app_token", "")
    table_id = cfg.get("table_id", "")
    if not app_token or not table_id:
        print("[query_conductor] Bitable 未初始化 (data/bitable_conductor.json 缺失)",
              file=sys.stderr)
        return {"ready": [], "scheduled": []}

    # 查询 ready 任务
    ready_records = _query_records(app_token, table_id, "ready")
    ready_tasks = [_record_to_task(r) for r in ready_records]

    # 查询 scheduled 任务，只保留已到时间的
    scheduled_records = _query_records(app_token, table_id, "scheduled")
    now = datetime.now()
    scheduled_tasks = []
    for rec in scheduled_records:
        task = _record_to_task(rec)
        sched_time = task.get("scheduled_time", "")
        if sched_time:
            try:
                dt = datetime.strptime(sched_time, "%Y-%m-%d %H:%M")
                if dt > now:
                    continue  # 还没到时间，跳过
            except ValueError:
                pass  # 格式不对，仍然包含
        scheduled_tasks.append(task)

    return {"ready": ready_tasks, "scheduled": scheduled_tasks}


def main():
    pretty = "--pretty" in sys.argv
    indent = 2 if pretty else None

    try:
        result = query()
        print(json.dumps(result, ensure_ascii=False, indent=indent))
    except Exception as e:
        print(f"[query_conductor] 异常: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
