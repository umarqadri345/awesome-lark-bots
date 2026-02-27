# -*- coding: utf-8 -*-
"""
JustOneAPI 客户端 — 统一的 API 请求封装。
"""

import time
import requests
from sentiment.config.settings import JOA_TOKEN, JOA_BASE, REQ_DELAY, log


def joa_request(endpoint: str, params: dict, retries: int = 2, timeout: int = 60):
    """
    请求 JOA；对 504 / code=301 自动重试。

    Returns:
        data 字段内容，失败时返回 None。
    """
    p = {**params, "token": JOA_TOKEN}
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{JOA_BASE}{endpoint}", params=p, timeout=timeout)
            r.raise_for_status()
            body = r.json()
            code = body.get("code")
            if code == 0:
                return body.get("data")
            if code == 301 and attempt < retries:
                log.info("JOA %s 返回 301（采集失败），%ds 后重试（%d/%d）",
                         endpoint, 2, attempt + 1, retries + 1)
                time.sleep(2)
                continue
            log.debug("API %s code=%s: %s", endpoint, body.get("code"), body.get("message"))
            return None
        except requests.exceptions.HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 504 and attempt < retries:
                log.info("JOA %s 504 Gateway Timeout，%ds 后重试（%d/%d）",
                         endpoint, 3, attempt + 1, retries + 1)
                time.sleep(3)
                continue
            if attempt < retries:
                time.sleep(1)
                continue
            log.debug("API %s failed after retries: %s", endpoint, exc)
        except Exception as exc:
            if attempt < retries:
                time.sleep(1)
                continue
            log.debug("API %s failed after retries: %s", endpoint, exc)
    return None
