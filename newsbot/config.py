# -*- coding: utf-8 -*-
"""
早知天下事 — 全局配置。
RSS 源、API 端点、区域定义、请求参数。
"""

import logging
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEWSBOT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "newsbot"
REPORTS_DIR = DATA_DIR / "reports"
for _d in (DATA_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
JOA_TOKEN = os.getenv("JOA_TOKEN", "")
JOA_BASE = os.getenv("JOA_BASE_URL", "https://api.justoneapi.com")

# ---------------------------------------------------------------------------
# 飞书
# ---------------------------------------------------------------------------
NEWSBOT_FEISHU_APP_ID = (
    os.getenv("NEWSBOT_FEISHU_APP_ID")
    or os.getenv("FEISHU_APP_ID", "")
)
NEWSBOT_FEISHU_APP_SECRET = (
    os.getenv("NEWSBOT_FEISHU_APP_SECRET")
    or os.getenv("FEISHU_APP_SECRET", "")
)
NEWSBOT_FEISHU_WEBHOOK = (
    os.getenv("NEWSBOT_FEISHU_WEBHOOK")
    or os.getenv("FEISHU_WEBHOOK", "")
)

# ---------------------------------------------------------------------------
# 时区
# ---------------------------------------------------------------------------
BEIJING = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# HTTP 请求
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ---------------------------------------------------------------------------
# 采集上限
# ---------------------------------------------------------------------------
MAX_ITEMS_PER_PLATFORM = 15
COLLECTOR_WORKERS = 8

# ---------------------------------------------------------------------------
# RSS 源配置 — 按区域和国家组织
# ---------------------------------------------------------------------------

RSS_FEEDS = {
    # ── 越南 ──
    "vn": [
        {"name": "VnExpress",  "url": "https://vnexpress.net/rss/tin-moi-nhat.rss",  "lang": "vi"},
        {"name": "Tuổi Trẻ",  "url": "https://tuoitre.vn/rss/tin-moi-nhat.rss",     "lang": "vi"},
        {"name": "Dân Trí",   "url": "https://dantri.com.vn/rss/home.rss",           "lang": "vi"},
        {"name": "Kenh14",    "url": "https://kenh14.vn/home.rss",                    "lang": "vi"},
    ],
    # ── 日本 ──
    "jp": [
        {"name": "NHK",          "url": "https://www3.nhk.or.jp/rss/news/cat0.xml",             "lang": "ja"},
        {"name": "Japan Times",  "url": "https://www.japantimes.co.jp/feed/",                    "lang": "en"},
        {"name": "Mainichi",     "url": "https://mainichi.jp/rss/etc/mainichi-flash.rss",        "lang": "ja"},
    ],
    # ── 韩国 ──
    "kr": [
        {"name": "Korea Herald", "url": "https://www.koreaherald.com/common/rss_xml.php?ct=102", "lang": "en"},
        {"name": "Yonhap",      "url": "https://en.yna.co.kr/RSS/news.xml",                     "lang": "en"},
    ],
    # ── 印度 ──
    "in": [
        {"name": "TOI",  "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",  "lang": "en"},
        {"name": "NDTV", "url": "https://feeds.feedburner.com/ndtvnews-latest",                "lang": "en"},
    ],
    # ── 印尼 ──
    "id": [
        {"name": "Detik",          "url": "https://rss.detik.com/index.php/detikcom",                        "lang": "id"},
        {"name": "Kompas",         "url": "https://www.kompas.com/rss",                                      "lang": "id"},
        {"name": "Google News ID", "url": "https://news.google.com/rss?hl=id&gl=ID&ceid=ID:id",              "lang": "id"},
    ],
    # ── 美国 ──
    "us": [
        {"name": "CNN",      "url": "http://rss.cnn.com/rss/edition.rss",      "lang": "en"},
        {"name": "NPR",      "url": "https://feeds.npr.org/1001/rss.xml",      "lang": "en"},
    ],
    # ── 英国 ──
    "uk": [
        {"name": "BBC",      "url": "https://feeds.bbci.co.uk/news/rss.xml",          "lang": "en"},
        {"name": "Guardian",  "url": "https://www.theguardian.com/world/rss",          "lang": "en"},
    ],
    # ── 德国 ──
    "de": [
        {"name": "Spiegel", "url": "https://www.spiegel.de/schlagzeilen/tops/index.rss",  "lang": "de"},
        {"name": "Zeit",    "url": "https://newsfeed.zeit.de/index",                       "lang": "de"},
    ],
    # ── 法国 ──
    "fr": [
        {"name": "Le Monde",  "url": "https://www.lemonde.fr/rss/une.xml",                  "lang": "fr"},
        {"name": "Le Figaro", "url": "https://www.lefigaro.fr/rss/figaro_actualites.xml",   "lang": "fr"},
    ],
}

# Google News RSS — 每个区域/语言的补充源
GOOGLE_NEWS_FEEDS = {
    "cn":  {"name": "Google News 中国", "url": "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "lang": "zh"},
    "tw":  {"name": "Google News 台湾", "url": "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "lang": "zh"},
    "hk":  {"name": "Google News 香港", "url": "https://news.google.com/rss?hl=zh-HK&gl=HK&ceid=HK:zh-Hant", "lang": "zh"},
    "vn":  {"name": "Google News 越南", "url": "https://news.google.com/rss?hl=vi&gl=VN&ceid=VN:vi",           "lang": "vi"},
    "jp":  {"name": "Google News 日本", "url": "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja",           "lang": "ja"},
    "kr":  {"name": "Google News 韩国", "url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",           "lang": "ko"},
    "us":  {"name": "Google News 美国", "url": "https://news.google.com/rss?hl=en&gl=US&ceid=US:en",           "lang": "en"},
    "global": {"name": "Google News Global", "url": "https://news.google.com/rss?hl=en&gl=US&ceid=US:en&topic=h", "lang": "en"},
}

# Hacker News（科技圈补充）
HACKERNEWS_FEED = {"name": "Hacker News", "url": "https://hnrss.org/frontpage?count=15", "lang": "en"}

# 区域分组（用于报告结构）
REGIONS = {
    "cn": {
        "name": "华人圈热点日报",
        "emoji": "🌏",
        "sub_regions": ["内地", "台湾", "香港", "海外华人"],
    },
    "vn": {
        "name": "越南热点日报",
        "emoji": "🇻🇳",
    },
    "asia": {
        "name": "亚太热点日报",
        "emoji": "🌏",
        "countries": ["in", "id", "kr", "jp"],
        "country_names": {"in": "印度", "id": "印尼", "kr": "韩国", "jp": "日本"},
    },
    "west": {
        "name": "欧美热点日报",
        "emoji": "🌍",
        "countries": ["us", "uk", "de", "fr"],
        "country_names": {"us": "美国", "uk": "英国", "de": "德国", "fr": "法国"},
    },
}

# Reddit 子版块
REDDIT_SUBS = {
    "cn": ["China_irl", "China", "worldnews"],
    "vn": ["Vietnam"],
    "asia": ["india", "indonesia", "korea", "japan"],
    "west": ["news", "worldnews", "europe"],
}

# 数据来源标注
DATA_SOURCES_LINE = (
    "数据来源：微博 · 百度 · 知乎 · B站 · 小红书 · 抖音 · "
    "今日头条 · 微信热文 · 澎湃 · "
    "PTT · LIHKG · Reddit · Hacker News · "
    "Google News · VnExpress · Tuoi Tre · Dan Tri · Kenh14 · "
    "Detik · Kompas · TOI · NDTV · "
    "NHK · Yonhap · CNN · NPR · BBC · Guardian · "
    "Spiegel · Zeit · Le Monde · Le Figaro"
)

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
_log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format=_log_fmt,
)
log = logging.getLogger("newsbot")
