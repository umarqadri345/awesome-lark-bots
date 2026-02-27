# -*- coding: utf-8 -*-
"""
GitHub 数据存储 — 将采集结果推送到 GitHub 仓库。

路径结构: sentiment/{report_type}/{YYYY-MM-DD}/{filename}
推送后返回文件的 GitHub raw URL，方便 Claude Code 直接读取。
"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

from sentiment.config.settings import GITHUB_TOKEN, GITHUB_REPO, BEIJING, log

_gh = None
_repo = None


def _get_repo():
    """懒初始化 GitHub 仓库对象。"""
    global _gh, _repo
    if _repo is not None:
        return _repo
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        from github import Github, Auth
        _gh = Github(auth=Auth.Token(GITHUB_TOKEN))
        _repo = _gh.get_repo(GITHUB_REPO)
        return _repo
    except ImportError:
        log.warning("PyGithub 未安装，GitHub 推送不可用。运行: pip install PyGithub")
        return None
    except Exception as e:
        log.error("GitHub 初始化失败: %s", e)
        return None


def _github_path(profile_id: str, filename: str) -> str:
    """生成 GitHub 仓库内的文件路径。"""
    date = datetime.now(BEIJING).strftime("%Y-%m-%d")
    return f"sentiment/{profile_id}/{date}/{filename}"


def upload_file(local_path: Path, profile_id: str) -> Optional[str]:
    """
    将本地文件推送到 GitHub 仓库。
    返回文件的 GitHub raw URL，未配置或失败时返回 None。
    """
    repo = _get_repo()
    if repo is None:
        log.info("GitHub 未配置，跳过推送: %s", local_path.name)
        return None

    gh_path = _github_path(profile_id, local_path.name)
    try:
        content = local_path.read_bytes()
        message = f"sentiment: {profile_id} {local_path.name}"

        try:
            existing = repo.get_contents(gh_path)
            repo.update_file(gh_path, message, content, existing.sha)
            log.info("GitHub 更新文件: %s", gh_path)
        except Exception:
            repo.create_file(gh_path, message, content)
            log.info("GitHub 创建文件: %s", gh_path)

        default_branch = repo.default_branch
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{default_branch}/{gh_path}"
        return raw_url
    except Exception as e:
        log.error("GitHub 推送失败 %s: %s", local_path.name, e)
        return None


def upload_files(file_paths: dict[str, Path], profile_id: str) -> dict[str, Optional[str]]:
    """批量推送文件，返回 {类型: raw_url} 映射。"""
    urls = {}
    for file_type, path in file_paths.items():
        urls[file_type] = upload_file(path, profile_id)
    return urls


def is_configured() -> bool:
    """检查 GitHub 是否已配置。"""
    return bool(GITHUB_TOKEN and GITHUB_REPO)
