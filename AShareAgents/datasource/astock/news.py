"""A-share company and market-news aggregation."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Callable

from dateutil.relativedelta import relativedelta
from requests import exceptions as requests_exceptions

from ..clsFinance import get as cls_get
from ..eastMoney import get as eastmoney_get
from ..sinaFinance import get as sina_get
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS, describe_data_source_error

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_disabled_sources: set[str] = set()


def fetch_eastmoney_company_news(code: str, page_size: int = 20) -> list[dict]:
    """Fetch company news from Eastmoney's search endpoint."""
    inner_param = {
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    response = eastmoney_get(
        "https://search-api-web.eastmoney.com/search/jsonp",
        params={
            "cb": "callback",
            "param": json.dumps(inner_param, ensure_ascii=False),
            "_": "1",
        },
        headers={"Referer": "https://so.eastmoney.com/", "User-Agent": _USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    text = response.text
    start = text.find("(")
    end = text.rfind(")")
    if start < 0 or end <= start:
        raise ValueError("Eastmoney returned invalid JSONP")
    data = json.loads(text[start + 1 : end])
    if not isinstance(data, dict):
        raise ValueError("Eastmoney returned an unexpected payload")
    return [
        {
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "time": item.get("date", ""),
            "source": item.get("mediaName", "东方财富"),
            "url": item.get("url", ""),
        }
        for item in data.get("result", {}).get("cmsArticleWebOld", [])
    ]


def fetch_sina_company_news(code: str, page_size: int = 20) -> list[dict]:
    """Fetch company news from Sina as a fallback source."""
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    response = sina_get(
        "https://vip.stock.finance.sina.com.cn/corp/view/"
        f"vCB_AllNewsStock.php?symbol={prefix}{code}&Page=1",
        headers={"User-Agent": _USER_AGENT, "Referer": "https://finance.sina.com.cn/"},
        timeout=15,
    )
    response.raise_for_status()
    response.encoding = "gb2312"
    rows = re.findall(
        r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
        r"<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>",
        response.text,
    )
    return [
        {
            "title": title.strip(),
            "content": "",
            "time": f"{date_str} {time_str}",
            "source": "新浪财经",
            "url": link,
        }
        for date_str, time_str, link, title in rows[:page_size]
    ]


def get_company_news(code: str, start_date: str, end_date: str) -> str:
    """返回公司新闻，东方财富不可用时回退到新浪。"""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    if start_dt > end_dt:
        raise ValueError("start_date must not be later than end_date")

    articles: list[dict] = []
    source_label = ""
    try:
        articles = fetch_eastmoney_company_news(code)
        source_label = "东方财富"
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        logger.warning("东方财富新闻获取 %s 失败: %s", code, exc)

    if not articles:
        try:
            articles = fetch_sina_company_news(code)
            source_label = "新浪财经"
        except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
            logger.warning("新浪财经新闻获取 %s 失败: %s", code, exc)

    if not articles:
        return f"未找到 A 股 '{code}' 的新闻"

    sections: list[str] = []
    for article in articles:
        published = str(article.get("time", ""))
        try:
            published_dt = datetime.strptime(published[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            published_dt = None
        if published_dt is not None and not start_dt <= published_dt <= end_dt:
            continue

        title = str(article.get("title", "")).strip()
        if not title:
            continue
        content = str(article.get("content", ""))
        source = article.get("source", source_label)
        link = article.get("url", "")
        lines = [f"### {title} (来源: {source})"]
        if content:
            lines.append(content[:300] + ("..." if len(content) > 300 else ""))
        if link and link != "nan":
            lines.append(f"链接: {link}")
        sections.append("\n".join(lines))

    if not sections:
        return f"在 {start_date} 至 {end_date} 期间未找到 A 股 '{code}' 的新闻"
    return f"## {code} (A股) 新闻，{start_date} 至 {end_date}:\n\n" + "\n\n".join(sections)


def get_global_news(
    curr_date: str,
    look_back_days: int,
    limit: int,
    *,
    warning_once: Callable[..., None],
) -> str:
    """Aggregate global financial news from CLS and Eastmoney."""
    if look_back_days < 0:
        raise ValueError("look_back_days must be non-negative")
    if limit <= 0:
        raise ValueError("limit must be positive")

    current_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (current_dt - relativedelta(days=look_back_days)).strftime("%Y-%m-%d")
    all_news: list[dict] = []

    if "cls" not in _disabled_sources:
        try:
            response = cls_get(
                "https://www.cls.cn/nodeapi/telegraphList",
                params={"rn": str(limit), "page": "1"},
                headers={"User-Agent": _USER_AGENT, "Referer": "https://www.cls.cn/"},
                timeout=10,
            )
            response.raise_for_status()
            if not response.content.strip():
                raise ValueError("CLS returned an empty response")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("CLS returned an unexpected payload")
            for item in payload.get("data", {}).get("roll_data", []):
                ctime = item.get("ctime", "")
                try:
                    published = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M") if ctime else ""
                except (ValueError, TypeError, OSError):
                    published = str(ctime)
                all_news.append(
                    {
                        "title": item.get("title", "") or item.get("brief", ""),
                        "content": item.get("content", "") or item.get("brief", ""),
                        "time": published,
                        "source": "CLS Wire",
                    }
                )
        except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
            if isinstance(exc, requests_exceptions.HTTPError) and getattr(exc.response, "status_code", None) == 404:
                _disabled_sources.add("cls")
                logger.info("全球新闻：财联社接口已失效（HTTP 404），本进程改用东方财富")
            else:
                warning_once(
                    "cls-news",
                    "全球新闻：财联社暂不可用（%s），已继续使用东方财富",
                    describe_data_source_error(exc),
                )
            logger.debug("财联社新闻获取失败", exc_info=True)

    try:
        response = eastmoney_get(
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
            params={
                "client": "web",
                "biz": "web_724",
                "fastColumn": "102",
                "sortEnd": "",
                "pageSize": str(limit),
                "req_trace": str(uuid.uuid4()),
            },
            headers={"User-Agent": _USER_AGENT, "Referer": "https://kuaixun.eastmoney.com/"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Eastmoney returned an unexpected payload")
        for item in payload.get("data", {}).get("fastNewsList", []):
            all_news.append(
                {
                    "title": item.get("title", ""),
                    "content": item.get("summary", "")[:200],
                    "time": item.get("showTime", ""),
                    "source": "Eastmoney Global",
                }
            )
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        warning_once(
            "eastmoney-global-news",
            "全球新闻：东方财富暂不可用（%s）",
            describe_data_source_error(exc),
        )
        logger.debug("东方财富全球新闻获取失败", exc_info=True)

    unique: list[dict] = []
    seen: set[str] = set()
    for article in all_news:
        title = str(article.get("title", "")).strip()
        if title and title not in seen:
            seen.add(title)
            unique.append(article)

    if not unique:
        return f"未找到 {curr_date} 的全球财经新闻"

    sections: list[str] = []
    for article in unique[:limit]:
        lines = [f"### {article['title']} (来源: {article['source']})"]
        content = str(article.get("content", ""))
        if content:
            lines.append(content[:300] + ("..." if len(content) > 300 else ""))
        sections.append("\n".join(lines))
    return f"## 中国及全球财经新闻，{start_date} 至 {curr_date}:\n\n" + "\n\n".join(sections)
