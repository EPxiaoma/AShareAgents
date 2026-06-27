"""A 股题材、资金流和一致预期信号适配器。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
import logging
import math
import os

from ..baiduFinance import get as _baidu_get
from ..eastMoney import get as _em_get
from ..tencentFinance import get_quotes as _tencent_quote
from ..tongHuaShun import get as _ths_get
from ..tongHuaShun import get_eps_forecast as _ths_eps_forecast
from .errors import RECOVERABLE_DATA_SOURCE_ERRORS
from .symbols import _normalize_ticker

logger = logging.getLogger(__name__)

# ---- 10. 获取盈利预测（get_profit_forecast）----


def get_profit_forecast(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "当前日期（未使用，仅为接口兼容保留）"] = None,
) -> str:
    """获取一致预期EPS预测及远期估值（同花顺直连 HTTP）。"""
    code = _normalize_ticker(ticker)

    try:
        df = _ths_eps_forecast(code)

        if df is None or df.empty:
            return f"未找到 A 股 '{code}' 的分析师覆盖数据"

        lines = [
            f"# {code} (A股) 一致预期 EPS 预测",
            f"# 来源: 同花顺分析师一致预期 (直连 HTTP)",
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        eps_by_year = {}
        for _, row in df.iterrows():
            year = str(row.iloc[0]) if len(row) > 0 else ""
            count_val = row.iloc[1] if len(row) > 1 else 0
            mean_eps_val = row.iloc[3] if len(row) > 3 else 0
            min_eps_val = row.iloc[2] if len(row) > 2 else "N/A"
            max_eps_val = row.iloc[4] if len(row) > 4 else "N/A"
            try:
                count = int(count_val)
            except (ValueError, TypeError):
                count = 0
            try:
                mean_eps = float(mean_eps_val)
            except (ValueError, TypeError):
                mean_eps = 0
            lines.append(
                f"FY{year}: EPS={mean_eps} (区间 {min_eps_val}~{max_eps_val}), "
                f"机构数={count}"
            )
            if count < 3:
                lines.append("  警告：覆盖机构数量不足（<3 家）")
            eps_by_year[year] = mean_eps

        # 远期估值
        try:
            tq = _tencent_quote([code])
            if code in tq:
                price = tq[code]["price"]
                pe_ttm = tq[code]["pe_ttm"]
                lines.append(f"\n当前: 价格={price}, PE(TTM)={pe_ttm}")

                years_sorted = sorted(eps_by_year.keys())
                if years_sorted and eps_by_year.get(years_sorted[0], 0) > 0:
                    eps_cur = eps_by_year[years_sorted[0]]
                    fwd_pe = price / eps_cur
                    lines.append(
                        f"远期市盈率 (FY{years_sorted[0]}): {fwd_pe:.1f}x"
                    )
                    if (
                        len(years_sorted) >= 2
                        and eps_by_year.get(years_sorted[1], 0) > 0
                    ):
                        eps_next = eps_by_year[years_sorted[1]]
                        cagr = eps_next / eps_cur - 1
                        if cagr > 0:
                            peg = fwd_pe / (cagr * 100)
                            lines.append(
                                f"PEG: {peg:.2f} (复合增长率={cagr * 100:.0f}%)"
                            )
                            if fwd_pe > 30:
                                digest = math.log(fwd_pe / 30) / math.log(
                                    1 + cagr
                                )
                                lines.append(
                                    f"PE 消化至 30 倍所需年数: {digest:.1f} 年"
                                )
                        else:
                            lines.append(
                                f"EPS 下滑 ({cagr * 100:.0f}%), "
                                f"PEG 不适用"
                            )
        except RECOVERABLE_DATA_SOURCE_ERRORS as e:
            logger.warning("远期 PE 计算 %s 失败: %s", code, e)

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 盈利预测数据时出错：{str(e)}"


# ---- 11. 获取强势股（get_hot_stocks）----


def get_hot_stocks(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD，空字符串表示今天"] = "",
) -> str:
    """从同花顺编辑团队获取强势股及其题材归因。

    返回触及涨停的股票，附带人工精选的涨停原因标签
    （如 '算力租赁+AI政务'），解释其为何大涨。
    """
    if not curr_date or curr_date.strip() == "":
        curr_date = datetime.now().strftime("%Y-%m-%d")

    try:
        url = (
            f"http://zx.10jqka.com.cn/event/api/getharden/"
            f"date/{curr_date}/orderby/date/orderway/desc/charset/GBK/"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/117.0.0.0 Safari/537.36"
            )
        }
        r = _ths_get(url, headers=headers, timeout=10)
        data = r.json()

        if data.get("errocode", 0) != 0:
            return f"同花顺 API 错误: {data.get('errormsg', '未知错误')}"

        rows = data.get("data") or []
        if not rows:
            return (
                f"{curr_date} 无热门股票数据"
                f"（可能为非交易日或数据尚未更新）"
            )

        lines = [
            f"# 热门股票及题材归因 ({curr_date})",
            f"# 来源: 同花顺编辑团队 (人工精选涨停原因标签)",
            f"# 合计: {len(rows)} 只股票",
            "",
        ]

        from collections import Counter

        all_tags: list[str] = []

        for row in rows:
            code = row.get("code", "")
            name = row.get("name", "")
            reason = row.get("reason", "")
            zhangfu = row.get("zhangfu", "")
            huanshou = row.get("huanshou", "")
            chengjiaoe = row.get("chengjiaoe", "")
            dde = row.get("ddejingliang", "")

            lines.append(
                f"{code} {name}: +{zhangfu}% "
                f"换手{huanshou}% 成交额{chengjiaoe} "
                f"大单净量{dde} | {reason}"
            )

            if reason:
                tags = [t.strip() for t in str(reason).split("+") if t.strip()]
                all_tags.extend(tags)

        if all_tags:
            cnt = Counter(all_tags)
            lines.append(f"\n## 题材出现频率 (前15)")
            for tag, n in cnt.most_common(15):
                lines.append(f"  {tag}: {n} 只股票")

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {curr_date} 热门股票数据时出错：{str(e)}"


# ---- 12. 获取北向资金流（get_northbound_flow）----


def _northbound_cache_path() -> str:
    """本地 CSV 缓存路径，存储北向资金每日收盘快照。"""
    from ..config import get_config

    config = get_config()
    cache_dir = config.get(
        "data_cache_dir", os.path.expanduser("~/.ashareagents/cache")
    )
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "northbound_daily.csv")


def _save_northbound_snapshot(date_str: str, hgt: float, sgt: float) -> None:
    """将当日北向资金收盘数据追加到本地 CSV 缓存（按日期去重）。"""
    import csv

    path = _northbound_cache_path()
    existing: dict[str, tuple[str, str]] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    existing[row[0]] = (row[1], row[2])
    existing[date_str] = (f"{hgt:.2f}", f"{sgt:.2f}")
    sorted_dates = sorted(existing.keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "hgt", "sgt"])
        for d in sorted_dates:
            writer.writerow([d, existing[d][0], existing[d][1]])


def _load_northbound_history(n: int = 20) -> list[tuple[str, float, float]]:
    """从本地缓存加载最近 N 天的北向资金收盘数据。"""
    import csv

    path = _northbound_cache_path()
    if not os.path.exists(path):
        return []
    rows: list[tuple[str, float, float]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 3:
                try:
                    rows.append((row[0], float(row[1]), float(row[2])))
                except ValueError:
                    continue
    return rows[-n:]


def get_northbound_flow(
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史日度数据（最近20个交易日）"
    ] = False,
) -> str:
    """从同花顺 hsgtApi 获取北向资金流向（沪深股通）。

    实时数据：分钟级 HGT（沪股通）+ SGT（深股通）累计净买入。
    历史数据：自缓存的每日收盘快照（上游API自2024年8月起停止更新北向历史数据）。
    """
    hsgt_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "Chrome/117.0.0.0 Safari/537.36"
        ),
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }

    lines = [
        f"# 北向资金流向 ({curr_date})",
        "# 来源: 同花顺 hsgtApi (沪深股通) + 本地缓存",
        "",
    ]

    hgt_close = 0.0
    sgt_close = 0.0
    got_realtime = False

    try:
        url_rt = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        r = _ths_get(url_rt, headers=hsgt_headers, timeout=10)
        d = r.json()

        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])

        if times:
            lines.append("## 实时数据 (累计净买入, 亿元)")
            n = len(times)
            start_idx = max(0, n - 10)
            for i in range(start_idx, n):
                t = times[i]
                h = hgt[i] if i < len(hgt) else "N/A"
                s = sgt[i] if i < len(sgt) else "N/A"
                lines.append(f"  {t}: HGT={h} SGT={s}")

            hgt_close = float(hgt[-1]) if hgt else 0
            sgt_close = float(sgt[-1]) if sgt else 0
            total = hgt_close + sgt_close
            lines.append(
                f"\n收盘: HGT(沪股通)={hgt_close:.2f}亿 "
                f"SGT(深股通)={sgt_close:.2f}亿 "
                f"合计={total:.2f}亿"
            )
            if total > 0:
                lines.append("信号: 北向资金净流入 (看涨)")
            elif total < 0:
                lines.append("信号: 北向资金净流出 (看跌)")
            got_realtime = True
        else:
            lines.append("无实时数据 (非交易时段或节假日)")

        if got_realtime:
            today_str = datetime.now().strftime("%Y-%m-%d")
            _save_northbound_snapshot(today_str, hgt_close, sgt_close)

        if include_history:
            history = _load_northbound_history(20)
            if history:
                lines.append("\n## 历史每日收盘数据 (本地缓存, 亿元)")
                lines.append("日期       | HGT(沪股通) | SGT(深股通) | 合计")
                for date, h, s in history:
                    lines.append(f"  {date}: HGT={h:.2f} SGT={s:.2f} 合计={h + s:.2f}")
                avg_total = sum(h + s for _, h, s in history) / len(history)
                lines.append(
                    f"\n{len(history)} 日均净流入: {avg_total:.2f}亿"
                )
                if got_realtime:
                    today_total = hgt_close + sgt_close
                    diff = today_total - avg_total
                    lines.append(
                        f"今日 vs 均值: {'+' if diff >= 0 else ''}{diff:.2f}亿 "
                        f"({'高于' if diff >= 0 else '低于'} 均值)"
                    )
            else:
                lines.append(
                    "\n## 历史数据: 暂无缓存数据。"
                    "历史数据将在每次调用时自动累积。"
                )

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取北向资金流向数据时出错：{str(e)}"


# ---------------------------------------------------------------------------
# 百度股市通 (Baidu PAE) 辅助函数
# ---------------------------------------------------------------------------

_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
        "Gecko/20100101 Firefox/110.0"
    ),
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


# ---- 13. 获取概念板块（get_concept_blocks）----


def get_concept_blocks(
    ticker: Annotated[str, "A股代码（如 688017）"],
) -> str:
    """获取股票所属的概念/行业/地区板块（百度股市通）。

    返回申万行业分类、概念主题和地区板块。
    每个板块包含当日涨跌幅。
    """
    code = _normalize_ticker(ticker)

    try:
        url = (
            "https://finance.pae.baidu.com/api/getrelatedblock"
            f'?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]'
            "&finClientType=pc"
        )
        r = _baidu_get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
        d = r.json()

        if str(d.get("ResultCode", -1)) != "0":
            return (
                f"百度 PAE 错误: ResultCode={d.get('ResultCode')} "
                f"{d.get('ResultMsg', '')}"
            )

        result = d.get("Result", {})
        categories = result.get(code, [])
        if not categories:
            return f"未找到 {code} 的概念板块数据"

        lines = [
            f"# {code} (A股) 概念及行业板块",
            f"# 来源: 百度股市通 (Baidu PAE)",
            f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        concept_names: list[str] = []

        for cat in categories:
            cat_name = cat.get("name", "")
            items = cat.get("list", [])
            if not items:
                continue
            lines.append(f"## {cat_name}")
            for item in items:
                name = item.get("name", "")
                ratio = item.get("ratio", "")
                desc = item.get("describe", "")
                suffix = f" ({desc})" if desc else ""
                lines.append(f"  {name}{suffix}: {ratio}")
                if cat_name == "概念":
                    concept_names.append(name)

        if concept_names:
            lines.append(f"\n概念标签: {' / '.join(concept_names)}")

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 概念板块数据时出错：{str(e)}"


# ---- 14. 获取资金流向（get_fund_flow）----


def get_fund_flow(
    ticker: Annotated[str, "A股代码"],
    curr_date: Annotated[str, "日期，格式 YYYY-MM-DD"],
    include_history: Annotated[
        bool, "是否包含历史日度资金流向（最近20天）"
    ] = True,
) -> str:
    """从东财 push2 获取个股资金流向。

    实时数据：分钟级主力/大单/中单/小单/超大单净流入。
    历史数据：20个交易日的日度净流入（push2his）。

    V0.2.7：用东财 push2 资金流向 API 替代了百度 PAE
    （fundflow/fundsortlist，自2026年5月起下线）。
    """
    code = _normalize_ticker(ticker)
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    lines = [
        f"# {code} (A股) 资金流向",
        f"# 来源: 东财 push2 (Eastmoney)",
        f"# 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    try:
        # 实时分钟级资金流向
        url_rt = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params_rt = {
            "secid": secid, "klt": 1,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        }
        r = _em_get(url_rt, params=params_rt, timeout=10)
        d = r.json()
        klines = d.get("data", {}).get("klines", [])

        if klines:
            lines.append(
                "## 实时分时资金流向 "
                "(主力/小单/中单/大单/超大单 净流入, 元)"
            )
            for line in klines[-10:]:
                parts = line.split(",")
                if len(parts) >= 6:
                    lines.append(
                        f"  {parts[0]}: "
                        f"主力={float(parts[1])/1e4:.0f}万 "
                        f"大单={float(parts[4])/1e4:.0f}万 "
                        f"超大单={float(parts[5])/1e4:.0f}万"
                    )

            last_parts = klines[-1].split(",")
            if len(last_parts) >= 2:
                main_net = float(last_parts[1])
                lines.append(
                    f"\n收盘: 主力净流入={main_net/1e4:.0f}万元"
                )
                if main_net > 0:
                    lines.append(
                        "信号: 主力资金净流入 (看涨)"
                    )
                elif main_net < 0:
                    lines.append(
                        "信号: 主力资金净流出 (看跌)"
                    )
        else:
            lines.append(
                "无实时资金流向数据（非交易时段或节假日）"
            )

        # 历史日度资金流向（push2his）
        if include_history:
            url_hist = (
                "https://push2his.eastmoney.com"
                "/api/qt/stock/fflow/daykline/get"
            )
            params_hist = {
                "secid": secid, "lmt": 20, "klt": 101,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
            }
            rh = _em_get(url_hist, params=params_hist, timeout=10)
            dh = rh.json()
            hist_klines = dh.get("data", {}).get("klines", [])

            if hist_klines:
                lines.append(
                    f"\n## 历史日度资金流向 "
                    f"(最近 {len(hist_klines)} 个交易日)"
                )
                lines.append(
                    "日期 | 主力净流入(万) | 大单(万) "
                    "| 中单(万) | 小单(万) | 超大单(万)"
                )
                for line in hist_klines:
                    parts = line.split(",")
                    if len(parts) >= 6:
                        lines.append(
                            f"  {parts[0]} "
                            f"| 主力={float(parts[1])/1e4:.0f} "
                            f"| 大单={float(parts[4])/1e4:.0f} "
                            f"| 中单={float(parts[3])/1e4:.0f} "
                            f"| 小单={float(parts[2])/1e4:.0f} "
                            f"| 超大={float(parts[5])/1e4:.0f}"
                        )

        return "\n".join(lines)

    except RECOVERABLE_DATA_SOURCE_ERRORS as e:
        return f"获取 {code} 资金流向数据时出错：{str(e)}"

