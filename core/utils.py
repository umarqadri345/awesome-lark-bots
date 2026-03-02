# -*- coding: utf-8 -*-
"""
通用工具函数 —— 各模块共用的辅助功能。
=====================================

提供以下功能：
  - truncate_for_display(): 文本截断，防止飞书消息过长
  - run_timestamp() / runs_dir() / save_session(): 运行记录管理
  - load_context(): 读取背景材料文件（支持文件/目录/纯文本）
"""
import time
from pathlib import Path

MAX_CHARS = 2000       # 中文内容最大字符数（飞书消息推荐上限）
MAX_EN_WORDS = 300     # 英文内容最大单词数


def is_mainly_chinese(text: str) -> bool:
    """判断文本是否以中文为主（中文字符占比 ≥ 50%）。"""
    ch = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total = len(text.strip()) or 1
    return ch / total >= 0.5


def truncate_for_display(text: str) -> str:
    """
    截断过长文本，防止飞书消息超出限制。

    中文按字符数截断（2000 字），英文按单词数截断（300 词）。
    超出部分用 [TRUNCATED] 标记，完整内容可在 session 文件中查看。
    """
    if not text or not text.strip():
        return text
    text = text.strip()
    if is_mainly_chinese(text):
        return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n\n[TRUNCATED]"
    words = text.split()
    return text if len(words) <= MAX_EN_WORDS else " ".join(words[:MAX_EN_WORDS]) + "\n\n[TRUNCATED]"


def run_timestamp() -> str:
    """生成当前时间戳字符串，格式如 20260227_143000，用于文件命名。"""
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def runs_dir() -> Path:
    """获取 runs/ 目录路径（不存在则自动创建）。所有运行记录保存在这里。"""
    d = Path(__file__).resolve().parent.parent / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(content: str, timestamp: str) -> Path:
    """将一次完整的运行记录保存为 Markdown 文件。返回文件路径。"""
    d = runs_dir()
    path = d / f"{timestamp}_session.md"
    path.write_text(content, encoding="utf-8")
    return path


def _read_file_safe(p: Path) -> str:
    """安全读取文件内容，失败时返回空字符串而非报错。"""
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def load_context(value: str) -> str:
    """
    加载背景材料 —— 支持三种输入方式：

    1. 文件路径 → 读取文件内容（支持 .md / .txt）
    2. 目录路径 → 读取目录下所有 .md 和 .txt 文件并拼接
    3. 纯文本   → 直接返回

    多个路径/文本可用逗号或空格分隔，例如：
      --context "briefs/topic1.md,briefs/topic2.md"
      --context "这是直接输入的背景文本"
    """
    if not value or not value.strip():
        return ""
    raw = value.strip()
    cwd = Path.cwd()
    base_dir = cwd.resolve()
    chunks = []
    for token in (_p.strip() for _s in raw.split(",") for _p in _s.split()):
        if not token:
            continue
        path = Path(token)
        if not path.is_absolute():
            path = cwd / path
        resolved = path.resolve()
        if not str(resolved).startswith(str(base_dir)):
            continue
        if path.exists():
            if path.is_file():
                chunks.append(f"--- {path.name} ---\n{_read_file_safe(path)}")
            elif path.is_dir():
                files = list(path.rglob("*.md")) + list(path.rglob("*.txt"))
                for f in sorted(files, key=lambda p: str(p)):
                    if f.is_file():
                        chunks.append(f"--- {f.relative_to(path)} ---\n{_read_file_safe(f)}")
        else:
            chunks.append(token)
    return "\n\n".join(chunks) if chunks else raw
