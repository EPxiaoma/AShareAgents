"""Eastmoney-backed market event and cross-sectional signals."""

from __future__ import annotations

import logging
import threading
from datetime import datetime

import pandas as pd

from ..eastMoney import datacenter, get as eastmoney_get
from ..ticker_safety import safe_ticker_component
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS, describe_data_source_error

logger = logging.getLogger(__name__)
_warning_keys: set[str] = set()
_warning_lock = threading.Lock()


def _warning_once(key: str, message: str, *args) -> None:
    with _warning_lock:
        if key in _warning_keys:
            logger.debug(message, *args)
            return
        _warning_keys.add(key)
    logger.warning(message, *args)


def _seat_lines(rows: list[dict]) -> list[str]:
    lines: list[str] = []
    for row in rows[:5]:
        buy = round((row.get("BUY") or 0) / 10000, 1)
        sell = round((row.get("SELL") or 0) / 10000, 1)
        net = round((row.get("NET") or 0) / 10000, 1)
        lines.append(
            f"  {row.get('OPERATEDEPT_NAME', '')} | {buy:.0f} | {sell:.0f} | {net:.0f}"
        )
    return lines


def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
) -> str:
    """返回龙虎榜记录、主要席位和机构动向。"""
    if look_back_days <= 0:
        raise ValueError("look_back_days must be positive")
    code = safe_ticker_component(ticker)
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    start_date = (end_dt - pd.Timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    lines = [f"# 龙虎榜数据 | {code} | {trade_date} (近{look_back_days}日)"]

    records: list[dict] = []
    try:
        records = datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=(
                f"(TRADE_DATE>='{start_date}')"
                f"(TRADE_DATE<='{trade_date}')"
                f'(SECURITY_CODE="{code}")'
            ),
            page_size=50,
            sort_columns="TRADE_DATE",
            sort_types="-1",
        )
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        reason = describe_data_source_error(exc)
        _warning_once(f"billboard:{code}", "龙虎榜：%s 查询失败（%s）", code, reason)
        logger.debug("龙虎榜列表查询 %s 失败", code, exc_info=True)
        lines.append(f"龙虎榜列表查询失败: {reason}")

    if records:
        lines.append(f"\n## 上榜记录 ({len(records)} 次)")
        lines.append("日期 | 原因 | 净买入(万) | 换手率")
        for row in records:
            net_buy = round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1)
            turnover = round(float(row.get("TURNOVERRATE") or 0), 2)
            lines.append(
                f"  {str(row.get('TRADE_DATE', ''))[:10]} "
                f"| {row.get('EXPLANATION', '')} | {net_buy:.0f} | {turnover:.2f}%"
            )
    elif len(lines) == 1:
        lines.append(f"\n近{look_back_days}日未上龙虎榜。")

    buy_rows: list[dict] = []
    sell_rows: list[dict] = []
    if records:
        latest_date = str(records[0].get("TRADE_DATE", ""))[:10]
        try:
            buy_rows = datacenter(
                "RPT_BILLBOARD_DAILYDETAILSBUY",
                filter_str=f'(TRADE_DATE=\'{latest_date}\')(SECURITY_CODE="{code}")',
                page_size=10,
                sort_columns="BUY",
                sort_types="-1",
            )
            sell_rows = datacenter(
                "RPT_BILLBOARD_DAILYDETAILSSELL",
                filter_str=f'(TRADE_DATE=\'{latest_date}\')(SECURITY_CODE="{code}")',
                page_size=10,
                sort_columns="SELL",
                sort_types="-1",
            )
        except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
            reason = describe_data_source_error(exc)
            _warning_once(f"billboard-seats:{code}", "龙虎榜席位：%s 查询失败（%s）", code, reason)
            logger.debug("龙虎榜席位查询 %s 失败", code, exc_info=True)
        else:
            lines.append(f"\n## 最近上榜席位明细 ({latest_date})")
            if buy_rows:
                lines.extend(["\n### 买入席位 TOP5", "营业部 | 买入(万) | 卖出(万) | 净额(万)"])
                lines.extend(_seat_lines(buy_rows))
            if sell_rows:
                lines.extend(["\n### 卖出席位 TOP5", "营业部 | 买入(万) | 卖出(万) | 净额(万)"])
                lines.extend(_seat_lines(sell_rows))

    institution_buy = sum(
        row.get("BUY") or 0
        for row in buy_rows
        if str(row.get("OPERATEDEPT_CODE", "")) == "0"
    )
    institution_sell = sum(
        row.get("SELL") or 0
        for row in sell_rows
        if str(row.get("OPERATEDEPT_CODE", "")) == "0"
    )
    if institution_buy or institution_sell:
        lines.extend(
            [
                "\n## 机构动向",
                f"  机构买入 {institution_buy / 1e4:.0f} 万 "
                f"| 卖出 {institution_sell / 1e4:.0f} 万 "
                f"| 净额 {(institution_buy - institution_sell) / 1e4:.0f} 万",
            ]
        )
    return "\n".join(lines)


def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """返回历史和未来限售股解禁安排。"""
    if forward_days < 0:
        raise ValueError("forward_days must be non-negative")
    code = safe_ticker_component(ticker)
    trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    end_date = (trade_dt + pd.Timedelta(days=forward_days)).strftime("%Y-%m-%d")
    lines = [f"# 限售解禁日历 | {code} | {trade_date}"]

    try:
        history = datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=15,
            sort_columns="FREE_DATE",
            sort_types="-1",
        )
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        reason = describe_data_source_error(exc)
        _warning_once(f"lockup-history:{code}", "限售解禁：%s 历史数据查询失败（%s）", code, reason)
        logger.debug("历史解禁查询 %s 失败", code, exc_info=True)
        lines.append(f"历史解禁查询失败: {reason}")
    else:
        if history:
            lines.extend([f"\n## 个股解禁记录 (共 {len(history)} 条)", "解禁时间 | 类型 | 解禁数量 | 占比"])
            for row in history:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| {row.get('FREE_SHARES_NUM', '')} | {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append("\n无历史解禁记录。")

    try:
        upcoming = datacenter(
            "RPT_LIFT_STAGE",
            filter_str=(
                f'(SECURITY_CODE="{code}")'
                f"(FREE_DATE>='{trade_date}')"
                f"(FREE_DATE<='{end_date}')"
            ),
            page_size=20,
            sort_columns="FREE_DATE",
            sort_types="1",
        )
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        reason = describe_data_source_error(exc)
        _warning_once(f"lockup-upcoming:{code}", "限售解禁：%s 未来数据查询失败（%s）", code, reason)
        logger.debug("未来解禁查询 %s 失败", code, exc_info=True)
        lines.append(f"未来解禁查询失败: {reason}")
    else:
        if upcoming:
            lines.append(f"\n## 未来 {forward_days} 天待解禁")
            for row in upcoming:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| 数量 {row.get('FREE_SHARES_NUM', '')} "
                    f"| 占比 {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append(f"\n未来 {forward_days} 天无待解禁。")
    return "\n".join(lines)


def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """返回东方财富行业表现排名。"""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    code = safe_ticker_component(ticker)
    lines = [f"# 行业横向对比 | {code} | {trade_date}"]
    try:
        response = eastmoney_get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Eastmoney returned an unexpected payload")
        items = payload.get("data", {}).get("diff", [])
    except RECOVERABLE_DATA_SOURCE_ERRORS as exc:
        reason = describe_data_source_error(exc)
        _warning_once(f"industry:{code}", "行业对比：%s 查询失败（%s）", code, reason)
        logger.debug("行业对比查询 %s 失败", code, exc_info=True)
        lines.append(f"行业对比查询失败: {reason}")
        return "\n".join(lines)

    if not items:
        lines.append("行业数据获取为空。")
        return "\n".join(lines)
    lines.extend(
        [
            f"\n## 全行业表现 (东财 {len(items)} 个行业)",
            "排名 | 行业 | 涨跌幅 | 上涨 | 下跌 | 领涨股",
        ]
    )
    for index, item in enumerate(items[: top_n * 2], start=1):
        lines.append(
            f"  {index}. {item.get('f14', '')} | {item.get('f3', 0)}% "
            f"| {item.get('f104', 0)} | {item.get('f105', 0)} | {item.get('f140', '')}"
        )
    if len(items) > top_n * 2:
        lines.append(f"  ... (仅显示前 {top_n * 2} 名)")
    return "\n".join(lines)
