# -*- coding: utf-8 -*-
"""
create_doc.py — 创建飞书云文档并（可选）归档到指定文件夹。

用法：
    python -m claude_tasks.create_doc "文档标题" "Markdown内容"
    python -m claude_tasks.create_doc "文档标题" "内容" --folder <folder_token>
    python -m claude_tasks.create_doc "文档标题" --file content.md

参数：
    标题      — 文档标题
    内容      — Markdown 格式的文档内容（直接传或用 --file 从文件读取）
    --folder  — 创建后移动到此文件夹 token
    --file    — 从文件读取内容（代替第二个位置参数）

输出：
    成功时输出文档 URL
"""
import os
import re
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


def create_doc(
    title: str,
    content: str,
    folder_token: str = "",
) -> tuple[bool, str]:
    """创建飞书云文档。

    Args:
        title: 文档标题
        content: Markdown 格式内容
        folder_token: 创建后移动到此文件夹（可选）

    Returns: (ok, url_or_error)
    """
    from cal.push_target import get_push_target_open_id
    from core.feishu_client import create_document_with_content, move_drive_file

    open_id = get_push_target_open_id()

    ok, url = create_document_with_content(title, content, open_id)
    if not ok:
        return False, f"创建文档失败: {url}"

    # 如果指定了目标文件夹，移动过去
    if folder_token:
        doc_match = re.search(r'/docx/([A-Za-z0-9]+)', url)
        if doc_match:
            doc_token = doc_match.group(1)
            move_ok, move_msg = move_drive_file(doc_token, folder_token, file_type="docx")
            if not move_ok:
                # 移动失败不影响文档创建，只是没归档
                print(f"[create_doc] 文档已创建但移动失败: {move_msg}", file=sys.stderr)

    return True, url


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]

    # Parse --folder
    folder_token = ""
    for i, f in enumerate(flags):
        if f == "--folder" and i + 1 < len(flags):
            folder_token = flags[i + 1]

    # Parse --file
    content_file = ""
    for i, f in enumerate(flags):
        if f == "--file" and i + 1 < len(flags):
            content_file = flags[i + 1]

    if len(args) < 1:
        print("用法: python -m claude_tasks.create_doc <标题> [<内容>] [--file path] [--folder token]",
              file=sys.stderr)
        sys.exit(1)

    title = args[0]

    if content_file:
        with open(content_file, encoding="utf-8") as f:
            content = f.read()
    elif len(args) >= 2:
        content = args[1]
    else:
        print("错误: 需要提供内容（第二个参数或 --file）", file=sys.stderr)
        sys.exit(1)

    ok, result = create_doc(title, content, folder_token=folder_token)
    print(result)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
