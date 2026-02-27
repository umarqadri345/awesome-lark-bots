# -*- coding: utf-8 -*-
"""
报告配置（profiles）和账号配置（accounts）。
集中管理各种报告类型的参数和月度统计需要的账号信息。
"""

# ---------------------------------------------------------------------------
# 舆情报告配置
# ---------------------------------------------------------------------------
REPORT_PROFILES = {
    "sky-weekly": {
        "id": "sky-weekly",
        "title": "光遇舆情周报",
        "subject": "《光·遇》",
        "keywords": ["光遇", "光遇手游", "sky光遇", "jenova陈星汉"],
        "days": 7,
        "max_posts": 5000,
        "kimi_sample": 2000,
        "web_supplement": True,
    },
    "thatskyshop-biweek": {
        "id": "thatskyshop-biweek",
        "title": "thatskyshop 双周报",
        "subject": "thatskyshop",
        "keywords": ["thatskyshop"],
        "days": 14,
        "max_posts": 2500,
        "kimi_sample": 2000,
        "web_supplement": False,
    },
    "guangzhizi-biweek": {
        "id": "guangzhizi-biweek",
        "title": "光之子友友会 双周报",
        "subject": "光之子友友会",
        "keywords": ["光之子友友会"],
        "days": 14,
        "max_posts": 2500,
        "kimi_sample": 2000,
        "web_supplement": False,
    },
    "jenova-month": {
        "id": "jenova-month",
        "title": "jenova陈星汉 月报",
        "subject": "陈星汉/jenova",
        "keywords": ["jenova陈星汉", "陈星汉"],
        "days": 30,
        "max_posts": 2500,
        "kimi_sample": 2000,
        "web_supplement": False,
    },
}

# ---------------------------------------------------------------------------
# 月度统计账号配置
# ---------------------------------------------------------------------------
ACCOUNTS = [
    {
        "key": "TGC",
        "name": "TGC（那家游戏公司/那家游戏有限公司/thatgamecompany那游）",
        "keywords": ["那家游戏公司", "那家游戏有限公司", "thatgamecompany那游"],
        "platform_ids": {},
    },
    {
        "key": "jenova",
        "name": "陈星汉（jenova陈星汉）",
        "keywords": ["jenova陈星汉"],
        "platform_ids": {},
    },
    {
        "key": "guangzhizi",
        "name": "光之子友友会",
        "keywords": ["光之子友友会"],
        "platform_ids": {},
    },
]

TOPIC_EXPOSURE_KEYWORDS = ["光之子友友会"]


def get_profile(profile_id: str) -> dict:
    """获取报告配置，不存在则返回 sky-weekly。"""
    return REPORT_PROFILES.get(profile_id, REPORT_PROFILES["sky-weekly"])
