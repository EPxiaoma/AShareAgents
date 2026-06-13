"""Alpha Vantage API 通用模块。

提供API请求封装、日期格式化、CSV过滤和限流错误处理等功能。
"""

import os
import requests
import pandas as pd
import json
import logging
from datetime import datetime
from io import StringIO

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.alphavantage.co/query"

def get_api_key() -> str:
    """从环境变量获取 Alpha Vantage API 密钥。"""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("环境变量 ALPHA_VANTAGE_API_KEY 未设置。")
    return api_key

def format_datetime_for_api(date_input) -> str:
    """将多种日期格式转换为Alpha Vantage API要求的YYYYMMDDTHHMM格式。"""
    if isinstance(date_input, str):
        if len(date_input) == 13 and 'T' in date_input:
            return date_input
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"不支持的日期格式: {date_input}")
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"日期必须是字符串或 datetime 对象，实际为 {type(date_input)}")

class AlphaVantageRateLimitError(Exception):
    """Alpha Vantage API 请求频率超限时抛出的异常。"""
    pass

def _make_api_request(function_name: str, params: dict) -> dict | str:
    """发送API请求并处理响应。

    Args:
        function_name: Alpha Vantage API 函数名
        params: 请求参数

    Returns:
        API响应内容（JSON字典或字符串）

    Raises:
        AlphaVantageRateLimitError: API请求频率超限时抛出
    """
    # 复制参数，避免调用方的配置被原地修改。
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "ashare_agents",
    })

    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement

    if entitlement:
        api_params["entitlement"] = entitlement
    elif "entitlement" in api_params:
        api_params.pop("entitlement", None)

    response = requests.get(API_BASE_URL, params=api_params)
    response.raise_for_status()

    response_text = response.text

    # Alpha Vantage 的错误与限流响应通常为 JSON，数据响应通常为 CSV。
    try:
        response_json = json.loads(response_text)
        if "Information" in response_json:
            info_message = response_json["Information"]
            if "rate limit" in info_message.lower() or "api key" in info_message.lower():
                raise AlphaVantageRateLimitError(f"Alpha Vantage API 请求频率超限: {info_message}")
    except json.JSONDecodeError:
        pass

    return response_text



def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    """过滤CSV数据，仅保留指定日期范围内的行。

    Args:
        csv_data: Alpha Vantage API返回的CSV字符串
        start_date: 开始日期，格式YYYY-MM-DD
        end_date: 结束日期，格式YYYY-MM-DD

    Returns:
        过滤后的CSV字符串
    """
    if not csv_data or csv_data.strip() == "":
        return csv_data

    try:
        df = pd.read_csv(StringIO(csv_data))

        # Alpha Vantage CSV 的首列为时间戳。
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]

        return filtered_df.to_csv(index=False)

    except Exception as e:
        # 过滤异常不应丢失已获取的数据，因此记录警告并返回原始响应。
        logger.warning("按日期范围过滤 CSV 数据失败: %s", e)
        return csv_data
